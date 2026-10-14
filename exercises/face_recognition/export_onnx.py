"""
第 9 步：导出 ONNX，并用 ONNX Runtime 验证（与 ROS 节点里用的是同一套代码）。

用法（训练环境）：conda activate hci-train
                  python export_onnx.py --model runs/me/weights/best.pt
输出：runs/me/weights/best.onnx
ONNX 是训练环境和 ROS 环境之间的桥梁：训练用 conda 里的 PyTorch，ROS 节点只需要系统里
apt 安装的 onnxruntime（几十 MB），不需要 PyTorch（上 GB）。
"""
import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
import time
from typing import List, Optional

from common import HERE, list_images, need
import cv2
from hci_perception.recognition.base import Detection
from hci_perception.recognition.ultralytics_pt import UltralyticsPt
from hci_perception.recognition.yolo_onnx import OnnxYolo


def export(model: str, imgsz: int = 416, opset: int = 18) -> Path:
    """导出 ONNX。opset 18：Ubuntu 26.04 用 apt 安装的 onnxruntime（1.23）可以直接加载。"""
    return Path(need('ultralytics').YOLO(model).export(format='onnx', imgsz=imgsz, opset=opset))


def iou(a: Detection, b: Detection) -> float:
    """两个检测框的交并比。"""
    w = max(0, min(a.x2, b.x2) - max(a.x1, b.x1))
    h = max(0, min(a.y2, b.y2) - max(a.y1, b.y1))
    union = (a.x2 - a.x1) * (a.y2 - a.y1) + (b.x2 - b.x1) * (b.y2 - b.y1) - w * h
    return w * h / union if union > 0 else 0.0


@dataclass
class Comparison:
    """PyTorch 与 ONNX Runtime 在同一批图片上的结果对比。"""

    images: int
    pt_boxes: int
    onnx_boxes: int
    matched: int  # 类别相同且位置重合（IoU > 0.5）的框
    pt_ms: float  # 平均每张的耗时（毫秒）
    onnx_ms: float


def compare(pt_model: str, onnx_model: str, images: List[Path], imgsz: int = 416,
            conf: float = 0.25) -> Comparison:
    """
    同一批图片分别用 .pt 和 .onnx 检测，比较框是否一致与耗时。

    一致性检查用 Ultralytics 的默认阈值 0.25：训练轮数少、分数偏低的模型也有框可比。
    """
    pt = UltralyticsPt(pt_model, conf, imgsz)
    ox = OnnxYolo(onnx_model, conf, imgsz)
    first = cv2.imread(str(images[0]))
    pt.detect(first)  # 预热：第一次推理较慢，不计时
    ox.detect(first)
    n_pt = n_ox = matched = 0
    t_pt = t_ox = 0.0
    for path in images:
        img = cv2.imread(str(path))
        t0 = time.perf_counter()
        d1 = pt.detect(img)
        t1 = time.perf_counter()
        d2 = ox.detect(img)
        t_pt, t_ox = t_pt + t1 - t0, t_ox + time.perf_counter() - t1
        n_pt, n_ox = n_pt + len(d1), n_ox + len(d2)
        matched += sum(any(b.class_name == d.class_name and iou(d, b) > 0.5 for b in d2)
                       for d in d1)
    n = len(images)
    return Comparison(n, n_pt, n_ox, matched, 1000 * t_pt / n, 1000 * t_ox / n)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description='导出 ONNX 并与 PyTorch 的结果对比')
    ap.add_argument('--model', required=True)
    ap.add_argument('--imgsz', type=int, default=416)
    ap.add_argument('--images', default=str(HERE / 'dataset' / 'images' / 'val'))
    ap.add_argument('--opset', type=int, default=18)
    a = ap.parse_args(argv)

    onnx_path = export(a.model, a.imgsz, a.opset)
    print(f'已导出：{onnx_path}（{onnx_path.stat().st_size / 1e6:.1f} MB）')
    exported = OnnxYolo(str(onnx_path))
    print(f'ONNX 输入尺寸 {exported.imgsz}，类别名：{exported.names}')
    images = list_images(a.images)[:20]
    if images:
        c = compare(a.model, str(onnx_path), images, a.imgsz)
        print(f'{c.images} 张验证图（置信度阈值 0.25）：PyTorch 检出 {c.pt_boxes} 个框，'
              f'ONNX 检出 {c.onnx_boxes} 个，其中 {c.matched} 个类别相同且位置重合（IoU>0.5）')
        if c.pt_boxes == 0 and c.onnx_boxes == 0:
            print('两种推理都没有检出人脸：模型可能训练不足（轮数或数据太少），先用 evaluate.py 看召回率')
        print(f'平均耗时：PyTorch {c.pt_ms:.1f} ms，ONNX Runtime {c.onnx_ms:.1f} ms')
        print('说明：PyTorch 推理时按长边缩放、尽量少填充，ONNX 用固定的正方形输入，个别低分框不同属正常')
    else:
        print(f'没有找到验证图片（{a.images}），跳过一致性检查')
    print('下一步（练习 4）：另开一个终端（不要激活 conda），运行')
    print(f'  ros2 launch hci_bringup perception.launch.py model:={onnx_path.resolve()}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
