"""
第 8 步：评估模型——验证集指标，加上分条件测试（本人、他人、暗光、戴眼镜……）。

用法：
  python evaluate.py --model runs/me/weights/best.pt
  python evaluate.py --model runs/me/weights/best.pt --test-dirs data/test/dark data/test/others
测试文件夹：自己另外拍几张（不同光照、戴口罩或眼镜、侧脸），以及几张他人的照片
（经过同意的，或公开数据）。放在 data/ 下面，和其他个人数据一样只留在本机。
输出：验证集 mAP、每类的精确率与召回率；每个测试文件夹里"认出本人"的比例；
带框的图片保存在 runs/eval/
"""
import argparse
from collections import Counter
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

from common import HERE, list_images, need
from hci_common.identity import is_target


def validate(model: Any, data: str, imgsz: int = 416, device: str = 'cpu',
             project: Path = HERE / 'runs', plots: bool = True) -> Dict[str, Any]:
    """在验证集（没参与训练的场次）上算 mAP 和每个类别的精确率、召回率。"""
    m = model.val(data=data, imgsz=imgsz, device=device, plots=plots, project=str(project),
                  name='val', exist_ok=True, verbose=False)
    per_class = {model.names[int(c)]: (float(m.box.p[i]), float(m.box.r[i]), float(m.box.ap50[i]))
                 for i, c in enumerate(m.box.ap_class_index)}
    return {'map50': float(m.box.map50), 'map': float(m.box.map), 'per_class': per_class}


def check_folder(model: Any, folder: Path, imgsz: int = 416, conf: float = 0.5,
                 device: str = 'cpu', out: Optional[Path] = None) -> Counter:
    """
    统计一个文件夹里每张图片的结果：认出本人（self）、只认出他人（face）、没检测到人脸（none）。

    out 不为空时把带框的图片保存到那里。
    """
    counts: Counter = Counter()
    imgs = [str(p) for p in list_images(folder)]
    if not imgs:
        return counts
    save = {'save': True, 'project': str(out.parent), 'name': out.name} if out else {}
    for r in model.predict(imgs, imgsz=imgsz, conf=conf, iou=0.5, device=device,
                           agnostic_nms=True, exist_ok=True, verbose=False, stream=True, **save):
        names = [model.names[int(k)] for k in r.boxes.cls.tolist()]
        if any(is_target(n) for n in names):
            counts['self'] += 1
        elif names:
            counts['face'] += 1
        else:
            counts['none'] += 1
    return counts


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description='评估"认出我"的模型')
    ap.add_argument('--model', required=True)
    ap.add_argument('--data', default=str(HERE / 'dataset' / 'data.yaml'))
    ap.add_argument('--imgsz', type=int, default=416)
    ap.add_argument('--conf', type=float, default=0.5)
    ap.add_argument('--test-dirs', nargs='*', default=[])
    ap.add_argument('--device', default='cpu')
    a = ap.parse_args(argv)

    model = need('ultralytics').YOLO(a.model)
    if Path(a.data).exists():
        m = validate(model, a.data, a.imgsz, a.device)
        print('\n== 验证集（未参与训练的场次）==')
        print(f'mAP50 = {m["map50"]:.3f}    mAP50-95 = {m["map"]:.3f}')
        for name, (p, r, ap50) in m['per_class'].items():
            print(f'  {name:>18s}：精确率 P={p:.3f}  召回率 R={r:.3f}  AP50={ap50:.3f}')
    for d in a.test_dirs:
        out = HERE / 'runs' / 'eval' / Path(d).name
        c = check_folder(model, Path(d), a.imgsz, a.conf, a.device, out)
        n = sum(c.values())
        if not n:
            print(f'{d}：没有图片')
            continue
        print(f'\n== {d}（{n} 张）==')
        print(f'  识别为本人 {c["self"]}（{c["self"] / n:.0%}）| 只识别为他人 {c["face"]}'
              f'（{c["face"] / n:.0%}）| 没检测到人脸 {c["none"]}（{c["none"] / n:.0%}）'
              f'  带框图片：{out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
