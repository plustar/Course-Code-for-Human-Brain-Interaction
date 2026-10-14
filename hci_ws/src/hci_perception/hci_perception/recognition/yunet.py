"""
YuNet 后端：OpenCV 自带的轻量人脸检测器（只输出类别 face）。

还没有训练自己的模型时，用它先把"摄像头 -> 识别 -> 显示 -> 机器人"整条管线跑通。
模型文件随包提供（models/face_detection_yunet_2023mar.onnx，MIT 许可，来自 OpenCV Zoo）。
"""
import os
from pathlib import Path
import sys
from typing import List, Tuple

from hci_common.identity import OTHERS
from hci_perception.recognition.base import Detection
import numpy as np

MODELS_DIR = Path(__file__).resolve().parents[1] / 'models'
# 比这大的画面先缩小再检测：YuNet 的耗时与像素数成正比，1920×1080 一帧约 160 ms（例如 Gazebo 里
# waffle 的相机），缩到 640×360 连同缩小约 17 ms。640 也是摄像头和仿真画面的宽度，人脸的像素足够
MAX_SIDE = 640
INPUT_SIZE = (320, 320)  # 创建检测器时的输入尺寸（宽, 高）；之后按每一帧的实际大小重设
NMS_THRESHOLD = 0.3  # 非极大值抑制：重叠超过它的框只留分数最高的一个
TOP_K = 50  # 最多保留这么多个候选框


def default_model() -> str:
    """包内自带的 YuNet 模型路径。"""
    return str(MODELS_DIR / 'face_detection_yunet_2023mar.onnx')


class YuNet:
    """
    YuNet 人脸检测。

    detect() 返回统一的 Detection；detect_rows() 返回 OpenCV 的原始结果（每行 15 个数：
    框 x, y, w, h，5 个关键点的坐标，分数），两步法要用关键点对齐人脸。长边超过 MAX_SIDE 的
    画面先缩小再检测，结果换算回原图的坐标。
    """

    backend = 'yunet'

    def __init__(self, model_path: str = '', min_confidence: float = 0.6) -> None:
        import cv2

        path = model_path or default_model()
        if not os.path.isfile(path):
            raise FileNotFoundError(f'找不到 YuNet 模型：{path}')
        try:  # 先用一张空白图试运行：OpenCV 太旧时在这里就给出明确提示
            self.detector = cv2.FaceDetectorYN.create(path, '', INPUT_SIZE, min_confidence,
                                                      NMS_THRESHOLD, TOP_K)
            self.detector.detect(np.zeros((INPUT_SIZE[1], INPUT_SIZE[0], 3), np.uint8))
        except cv2.error as e:
            raise RuntimeError(
                f'YuNet 无法运行（当前 OpenCV {cv2.__version__}，Python：{sys.executable}）。'
                'OpenCV 太旧（已确认 4.6 不行、4.10 可以）：ROS 环境请用 apt 安装的 '
                'python3-opencv（Ubuntu 26.04 为 4.10）') from e
        self.size: Tuple[int, int] = INPUT_SIZE

    def detect_rows(self, bgr: np.ndarray) -> np.ndarray:
        """返回 OpenCV 的原始检测结果（原图坐标），形状 (N, 15)；没有人脸时 N 为 0。"""
        import cv2

        h, w = bgr.shape[:2]
        scale = min(1.0, MAX_SIDE / max(w, h))
        if scale < 1.0:
            w, h = max(1, round(w * scale)), max(1, round(h * scale))
            bgr = cv2.resize(bgr, (w, h), interpolation=cv2.INTER_AREA)
        if (w, h) != self.size:
            self.detector.setInputSize((w, h))
            self.size = (w, h)
        _, faces = self.detector.detect(bgr)
        if faces is None:
            return np.zeros((0, 15), np.float32)
        if scale < 1.0:
            faces = faces.copy()
            faces[:, :14] /= scale  # 框与 5 个关键点换算回原图；最后一列是分数
        return faces

    def detect(self, bgr: np.ndarray) -> List[Detection]:
        """检测一张 BGR 图像，所有人脸的类别都是 face。"""
        h, w = bgr.shape[:2]
        return [Detection(OTHERS, float(row[14]), *clip_box(row, w, h))
                for row in self.detect_rows(bgr)]


def clip_box(row: np.ndarray, w: int, h: int) -> Tuple[int, int, int, int]:
    """YuNet 的 (x, y, 宽, 高) -> 裁剪到画面内的 (x1, y1, x2, y2)。"""
    x, y, fw, fh = (float(v) for v in row[:4])
    return (int(max(x, 0.0)), int(max(y, 0.0)),
            int(min(x + fw, w - 1.0)), int(min(y + fh, h - 1.0)))
