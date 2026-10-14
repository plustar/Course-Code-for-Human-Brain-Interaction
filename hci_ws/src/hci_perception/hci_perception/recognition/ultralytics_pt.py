"""
Ultralytics 后端：直接加载训练得到的 best.pt。

需要 PyTorch 和 Ultralytics，所以只能在训练环境（conda activate hci-train）里用，
练习 3 的 predict.py、export_onnx.py 用它和 ONNX 的结果对比。ROS 节点请加载导出的 best.onnx。
"""
from typing import List

from hci_perception.recognition.base import Detection, require
import numpy as np


class UltralyticsPt:
    """用 Ultralytics 运行 .pt 模型（与类别无关的 NMS，同 yolo_onnx）。"""

    backend = 'ultralytics_pt'

    def __init__(self, model_path: str, min_confidence: float = 0.5, imgsz: int = 640,
                 iou: float = 0.5, device: str = 'cpu') -> None:
        self.model = require('ultralytics').YOLO(model_path)
        self.names = self.model.names
        self.min_confidence, self.imgsz, self.iou, self.device = min_confidence, imgsz, iou, device

    def detect(self, bgr: np.ndarray) -> List[Detection]:
        """检测一张 BGR 图像。"""
        r = self.model.predict(bgr, conf=self.min_confidence, iou=self.iou, imgsz=self.imgsz,
                               device=self.device, agnostic_nms=True, verbose=False)[0]
        out = []
        for (x1, y1, x2, y2), score, k in zip(r.boxes.xyxy.cpu().numpy(),
                                              r.boxes.conf.cpu().numpy(),
                                              r.boxes.cls.cpu().numpy().astype(int)):
            out.append(Detection(self.names[int(k)], float(score), int(round(x1)),
                                 int(round(y1)), int(round(x2)), int(round(y2))))
        return out
