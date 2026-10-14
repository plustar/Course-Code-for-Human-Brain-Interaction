"""
第 7 步：在笔记本上微调 YOLO，训练"认出我"的模型。

用法（CPU 笔记本推荐的参数）：
  python train.py --data dataset/data.yaml
  python train.py --data dataset/data.yaml --model yolo11n.pt --imgsz 416 --epochs 30
有 NVIDIA 显卡（双系统，或 WSL2 装好驱动）：--device 0 --imgsz 640 --epochs 60
结果：runs/<name>/weights/best.pt，以及训练曲线 results.png、混淆矩阵等
说明：
  - 预训练权重（yolo26n.pt、yolo11n.pt）第一次会自动从 GitHub 下载；下载失败可以手动下载后
    放到本目录
  - 不建议上传到云端 GPU 训练：那相当于把你的人脸照片传到网上
"""
import argparse
from pathlib import Path
import sys
from typing import List, Optional

from common import HERE, need


def train(data: str, model: str = 'yolo26n.pt', epochs: int = 30, imgsz: int = 416,
          batch: int = 16, device: str = 'cpu', patience: int = 10, workers: int = 2,
          project: Path = HERE / 'runs', name: str = 'me', plots: bool = True) -> Path:
    """训练并返回最佳模型 best.pt 的路径。model 写成 yolo26n.yaml 时从零训练（不下载权重）。"""
    yolo = need('ultralytics').YOLO(model)
    yolo.train(data=data, epochs=epochs, imgsz=imgsz, batch=batch, device=device,
               patience=patience, workers=workers, project=str(project), name=name,
               exist_ok=True, seed=0, plots=plots)
    return Path(yolo.trainer.best)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description='微调 YOLO，训练"认出我"的模型')
    ap.add_argument('--data', default=str(HERE / 'dataset' / 'data.yaml'))
    ap.add_argument('--model', default='yolo26n.pt', help='yolo26n.pt 或 yolo11n.pt（预训练权重）')
    ap.add_argument('--epochs', type=int, default=30)
    ap.add_argument('--imgsz', type=int, default=416)
    ap.add_argument('--batch', type=int, default=16)
    ap.add_argument('--device', default='cpu', help='cpu、0（第一块 NVIDIA 显卡）或 mps（苹果）')
    ap.add_argument('--patience', type=int, default=10, help='验证指标连续多少轮不提升就提前停止')
    ap.add_argument('--workers', type=int, default=2)
    ap.add_argument('--name', default='me')
    a = ap.parse_args(argv)

    best = train(a.data, a.model, a.epochs, a.imgsz, a.batch, a.device, a.patience, a.workers,
                 name=a.name)
    print(f'\n训练完成。最佳模型：{best}\n下一步：python evaluate.py --model {best}')
    return 0


if __name__ == '__main__':  # 多进程加载数据时必须有这一行
    sys.exit(main())
