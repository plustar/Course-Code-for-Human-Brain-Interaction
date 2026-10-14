"""
识别后端的统一接口：输入一张 BGR 图像，输出一组 Detection。

识别节点只认这个接口，不关心模型来自哪里（策略模式）。四种后端各占一个文件：
  yolo_onnx       练习 3 导出的 best.onnx（ROS 节点的常规用法）
  yunet           OpenCV 自带的人脸检测，没有自己的模型时先把管线跑通
  sface           YuNet 检测 + SFace 比对的两步法，能拒识陌生人
  ultralytics_pt  训练得到的 best.pt，只能在训练环境（conda）里用
factory.create_recognizer() 按参数选择其中一种。
"""
from dataclasses import dataclass
import importlib
import sys
from types import ModuleType
from typing import List, Protocol

import numpy as np


@dataclass(frozen=True)
class Detection:
    """一个检测结果：类别名、置信度、边界框（原图像素坐标，左上 x1,y1 到右下 x2,y2）。"""

    class_name: str
    confidence: float
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def center_x(self) -> float:
        """框中心的横坐标。"""
        return (self.x1 + self.x2) / 2.0

    @property
    def height(self) -> int:
        """框的高度（像素）。"""
        return self.y2 - self.y1


class Recognizer(Protocol):
    """识别后端：detect() 返回一张图里的全部检测结果。"""

    backend: str  # 后端名称，用于日志

    def detect(self, bgr: np.ndarray) -> List[Detection]:
        """检测一张 BGR 图像。"""
        ...


_HINTS = {
    'onnxruntime': 'ROS 环境请执行 sudo apt install python3-onnxruntime；'
                   '训练环境请先 conda activate hci-train',
    'ultralytics': '.pt 模型只能在训练环境（conda activate hci-train）里使用；'
                   'ROS 节点请加载 export_onnx.py 导出的 .onnx 模型',
}


def require(module: str) -> ModuleType:
    """导入可选依赖；失败时用中文说明该怎么装、该在哪个环境里用。"""
    try:
        return importlib.import_module(module)
    except ImportError as e:
        raise RuntimeError(f'无法导入 {module}（当前 Python：{sys.executable}）。'
                           f'{_HINTS.get(module, "")}') from e
