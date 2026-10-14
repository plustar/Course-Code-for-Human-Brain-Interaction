"""
快速试用模型（不需要 ROS）：摄像头、视频或图片文件夹，显示"姓名 学号 置信度"。

用法：
  python predict.py --model runs/me/weights/best.onnx --source 0 --name 张三
  python predict.py --model runs/me/weights/best.pt --source me.mp4 --name 张三
  python predict.py --model runs/me/weights/best.onnx --source data/test/others --save out/
.onnx 与 ROS 识别节点用同一套代码推理；.pt 只能在训练环境里用。
"""
import argparse
from collections import Counter
from pathlib import Path
import sys
from typing import List, Optional

from common import frames, show_or_save
import cv2
from hci_common.identity import display_name, is_target
from hci_perception.overlay import Label, Painter
from hci_perception.recognition.factory import create_recognizer


def predict(model: str, source: str, name: str = '', conf: float = 0.5, imgsz: int = 416,
            save: Optional[Path] = None, show: bool = True) -> Counter:
    """逐帧识别并画框；save 不为空时把结果图保存到那里。返回画面数与本人、他人的检出次数。"""
    recognizer = create_recognizer(model, conf, imgsz)
    print(f'后端：{recognizer.backend}')
    painter = Painter()
    counts: Counter = Counter()
    for fname, img in frames(source):
        if img is None:
            continue
        dets = recognizer.detect(img)
        counts['images'] += 1
        counts['me'] += sum(is_target(d.class_name) for d in dets)
        counts['other'] += sum(not is_target(d.class_name) for d in dets)
        id_map = {d.class_name: name for d in dets if is_target(d.class_name)}
        labels = [Label((d.x1, d.y1, d.x2, d.y2),
                        f'{display_name(d.class_name, id_map)} {d.confidence:.2f}',
                        is_target(d.class_name)) for d in dets]
        if not show_or_save(painter.draw(img, labels), fname, save, show, 'predict (q to quit)'):
            break
    if save is None and show:
        cv2.destroyAllWindows()
    return counts


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description='快速试用模型')
    ap.add_argument('--model', required=True, help='.onnx 或 .pt')
    ap.add_argument('--source', default='0', help='摄像头编号、视频文件或图片文件夹')
    ap.add_argument('--name', default='', help='你的姓名，用于显示')
    ap.add_argument('--conf', type=float, default=0.5)
    ap.add_argument('--imgsz', type=int, default=416)
    ap.add_argument('--save', default='', help='保存带框图片的文件夹（不显示窗口）')
    a = ap.parse_args(argv)

    save = Path(a.save) if a.save else None
    c = predict(a.model, a.source, a.name, a.conf, a.imgsz, save)
    print(f'共 {c["images"]} 张画面：检出本人 {c["me"]} 次、他人 {c["other"]} 次'
          f'（置信度阈值 {a.conf}）' + (f'；带框图片保存在 {save}' if save else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
