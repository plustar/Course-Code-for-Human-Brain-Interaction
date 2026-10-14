"""
YOLO 的 ONNX 后端：加载练习 3 导出的 best.onnx，用 ONNX Runtime 推理（不需要 PyTorch）。

一次推理分四步：letterbox 缩放填充 -> 模型前向 -> 解码输出（置信度过滤 + NMS）-> 坐标还原到原图。
解码同时支持 Ultralytics 的两种导出格式，结果已与 Ultralytics 官方推理逐框核对一致。
"""
import ast
import contextlib
import os
import sys
from typing import Iterator, List, Optional, Sequence, Tuple

from hci_perception.recognition.base import Detection, require
import numpy as np


def letterbox(img: np.ndarray, size: int = 640,
              color: Tuple[int, int, int] = (114, 114, 114)
              ) -> Tuple[np.ndarray, float, Tuple[int, int]]:
    """等比缩放并用灰边填充到 size×size。返回 (图像, 缩放比, (左边填充, 上边填充))。"""
    import cv2

    h, w = img.shape[:2]
    r = min(size / h, size / w)  # 取较小的缩放比：长边正好放进 size，短边留空待填充
    nw, nh = int(round(w * r)), int(round(h * r))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    pad_w, pad_h = size - nw, size - nh
    left, top = pad_w // 2, pad_h // 2  # 填充平均分到上下 / 左右，让图像居中
    out = cv2.copyMakeBorder(resized, top, pad_h - top, left, pad_w - left,
                             cv2.BORDER_CONSTANT, value=color)
    return out, r, (left, top)


def unletterbox(boxes: np.ndarray, r: float, pad: Tuple[int, int], w: int, h: int) -> np.ndarray:
    """把 letterbox 坐标系下的 xyxy 框还原到原图坐标，并裁剪到图像范围内。"""
    b = boxes.astype(np.float32).copy()
    b[:, [0, 2]] = (b[:, [0, 2]] - pad[0]) / r
    b[:, [1, 3]] = (b[:, [1, 3]] - pad[1]) / r
    b[:, [0, 2]] = b[:, [0, 2]].clip(0, w - 1)
    b[:, [1, 3]] = b[:, [1, 3]].clip(0, h - 1)
    return b


def nms_agnostic(boxes: np.ndarray, scores: np.ndarray, iou_thr: float = 0.5) -> List[int]:
    """
    与类别无关的非极大值抑制：同一张脸只保留得分最高的一个框。

    为什么与类别无关？同一张脸可能同时被预测成 stu_xxx 和 face，按类别分别做 NMS
    会留下两个重叠的框；这里只保留分数更高的那个。返回保留下来的下标。
    """
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes.T
    areas = (x2 - x1).clip(0) * (y2 - y1).clip(0)
    order = scores.argsort()[::-1]  # 下标按分数从高到低排序
    keep = []
    while order.size > 0:
        i = int(order[0])  # 剩下里分数最高的框，必定保留
        keep.append(i)
        # 算它与其余每个框的交并比 (IoU = 交集面积 / 并集面积)：重叠太多就当作同一张脸
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = (xx2 - xx1).clip(0) * (yy2 - yy1).clip(0)
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
        order = order[1:][iou <= iou_thr]  # 丢掉与它重叠过多的，其余进入下一轮
    return keep


def decode_yolo_output(out: np.ndarray, conf_thr: float, iou_thr: float = 0.5
                       ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    解析 YOLO 的 ONNX 输出，返回 (xyxy 框, 分数, 类别号)，坐标在 letterbox 坐标系里。

    支持两种格式：
    1. 传统格式（Ultralytics 默认导出，YOLO11 和 YOLO26 都是）：形状 (1, 4+类别数, 锚点数)，
       前 4 行是 cx, cy, w, h，后面每行是一个类别的分数；需要自己做置信度过滤和 NMS。
    2. 端到端格式（导出时 nms=False 用 YOLO26 的免 NMS 头，或 nms=True 把 NMS 嵌进模型）：
       形状 (1, N, 6)，每行 x1, y1, x2, y2, score, cls，只需按分数过滤。
    """
    out = np.asarray(out)
    # 端到端格式 (1, N, 6)：每行已经是 [x1, y1, x2, y2, score, cls]，按分数过滤即可
    if out.ndim == 3 and out.shape[2] == 6:
        rows = out[0]
        rows = rows[rows[:, 4] >= conf_thr]
        return rows[:, :4], rows[:, 4], rows[:, 5].astype(int)
    # 传统格式 (1, 4+类别数, 锚点数)：转置成每行一个锚点，前 4 列是框、其余列是各类别分数
    pred = out[0].T
    cls_scores = pred[:, 4:]             # 每个锚点在各类别上的分数
    cls_ids = cls_scores.argmax(axis=1)  # 每个锚点取分数最高的类别
    scores = cls_scores.max(axis=1)      # 对应的最高分即该框置信度
    mask = scores >= conf_thr            # 丢掉低于阈值的锚点（绝大多数会被丢掉）
    pred, scores, cls_ids = pred[mask], scores[mask], cls_ids[mask]
    # YOLO 框是中心点+宽高 (cx, cy, w, h)，换成左上 / 右下角 (x1, y1, x2, y2)
    cx, cy, bw, bh = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3]
    boxes = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], axis=1)
    keep = nms_agnostic(boxes, scores, iou_thr)  # 去掉重叠的重复框
    return boxes[keep], scores[keep], cls_ids[keep]


@contextlib.contextmanager
def quiet_stderr() -> Iterator[None]:
    """
    暂时屏蔽 C/C++ 库直接写到终端（文件描述符 2）的输出。

    Ubuntu 26.04 用 apt 安装的 onnxruntime 在第一次创建会话时会打印几百行无害的
    "Schema error: Trying to register schema ... already registered"，把真正的日志淹没。
    出错时 onnxruntime 仍会抛出 Python 异常，不受影响。
    """
    try:
        sys.stderr.flush()
        saved: Optional[int] = os.dup(2)
    except (AttributeError, OSError, ValueError):  # 没有可用的标准错误输出（极少见）
        saved = None
    if saved is None:
        yield
        return
    try:
        with open(os.devnull, 'w') as devnull:
            os.dup2(devnull.fileno(), 2)
            yield
    finally:
        os.dup2(saved, 2)
        os.close(saved)


class OnnxYolo:
    """用 ONNX Runtime 运行 YOLO 模型。"""

    backend = 'yolo_onnx'

    def __init__(self, model_path: str, min_confidence: float = 0.5, imgsz: int = 640,
                 iou: float = 0.5, names: Optional[Sequence[str]] = None) -> None:
        ort = require('onnxruntime')
        with quiet_stderr():
            self.session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        # 固定输入尺寸的模型以模型为准，动态尺寸的模型用参数 imgsz
        self.imgsz = inp.shape[2] if isinstance(inp.shape[2], int) else imgsz
        self.min_confidence, self.iou = min_confidence, iou
        self.names = list(names) if names else self._names_from_metadata()

    def _names_from_metadata(self) -> List[str]:
        """Ultralytics 导出的 ONNX 在元数据里保存了类别名，如 "{0: 'stu_2023123456', 1: 'face'}"。"""
        meta = self.session.get_modelmeta().custom_metadata_map
        if 'names' in meta:
            table = ast.literal_eval(meta['names'])
            return [table[i] for i in sorted(table)]
        return []

    def detect(self, bgr: np.ndarray) -> List[Detection]:
        """检测一张 BGR 图像。"""
        h, w = bgr.shape[:2]
        img, r, pad = letterbox(bgr, self.imgsz)
        # 预处理成模型输入：BGR→RGB、HWC→CHW、加 batch 维、像素值归一化到 0–1
        x = img[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0  # BGR->RGB, NCHW
        out = self.session.run(None, {self.input_name: np.ascontiguousarray(x)})[0]
        boxes, scores, cls_ids = decode_yolo_output(out, self.min_confidence, self.iou)
        boxes = unletterbox(boxes, r, pad, w, h)
        dets = []
        for (x1, y1, x2, y2), score, k in zip(boxes, scores, cls_ids):
            name = self.names[k] if k < len(self.names) else str(k)
            dets.append(Detection(name, float(score), int(round(x1)), int(round(y1)),
                                  int(round(x2)), int(round(y2))))
        return dets
