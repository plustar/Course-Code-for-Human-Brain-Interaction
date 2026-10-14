"""
第 4 步：逐张检查预标注结果（轻量的替代方案；需要手动画框时用 X-AnyLabeling）。

用法：python review_labels.py --images data/self
按键：空格或回车 = 通过并看下一张；x = 删除这张（图片和标签移到 data/rejected）；
      b = 上一张；q = 退出（进度自动保存，下次从这里继续）
想从头再检查一遍：删除 <images>/.review_progress.json
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
from typing import Callable, List, Optional, Set, Tuple

from common import DATA, ensure_dir, from_yolo_line, label_path, list_images, read_labels
import cv2
import numpy as np

COLORS = {0: (96, 174, 39), 1: (28, 159, 255)}  # BGR：本人绿色，他人橙色
NAMES = {0: 'stu (self)', 1: 'face (other)'}
OK_KEYS = (ord(' '), 13)  # 空格、回车


def draw(img: np.ndarray, label: Path) -> np.ndarray:
    """在图片上画出标注框。"""
    h, w = img.shape[:2]
    out = img.copy()
    for line in read_labels(label):
        cls_id, (x1, y1, x2, y2) = from_yolo_line(line, w, h)
        color = COLORS.get(cls_id, (0, 0, 255))
        cv2.rectangle(out, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
        cv2.putText(out, NAMES.get(cls_id, str(cls_id)), (int(x1), max(int(y1) - 6, 14)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return out


def rel_key(img: Path, root: Path) -> str:
    """图片相对 --images 目录的路径，作为进度记录的键（与命令里写相对路径还是绝对路径无关）。"""
    return img.resolve().relative_to(root.resolve()).as_posix()


def load_reviewed(state_file: Path) -> Set[str]:
    """已经检查过（通过或删除）的图片。按集合记录：之后新增了场次、删过图片都不会漏看。"""
    if not state_file.exists():
        return set()
    return set(json.loads(state_file.read_text()).get('reviewed', []))


def save_reviewed(state_file: Path, reviewed: Set[str]) -> None:
    state_file.write_text(json.dumps({'reviewed': sorted(reviewed)}, ensure_ascii=False))


def next_unreviewed(imgs: List[Path], reviewed: Set[str], root: Path, start: int = 0) -> int:
    """从 start 开始找下一张还没检查过、也没被删除的图片；找不到时返回 len(imgs)。"""
    for i in range(start, len(imgs)):
        if imgs[i].exists() and rel_key(imgs[i], root) not in reviewed:
            return i
    return len(imgs)


def ask(img: np.ndarray) -> int:
    """显示一张图，等待按键。"""
    cv2.imshow('review', img)
    return cv2.waitKey(0) & 0xFF


def review(root: Path, data: Path = DATA,
           key: Callable[[np.ndarray], int] = ask) -> Tuple[int, int]:
    """
    逐张显示 root 下还没检查过的图片，按键决定通过或删除。返回 (已检查张数, 剩余张数)。

    key：显示一张图并返回按键的函数；测试时换成按预定顺序"按键"的替身。
    """
    imgs = list_images(root)
    state_file = root / '.review_progress.json'
    reviewed = load_reviewed(state_file)
    rejected = ensure_dir(Path(data) / 'rejected')
    i = next_unreviewed(imgs, reviewed, root)
    while 0 <= i < len(imgs):
        path = imgs[i]
        img = cv2.imread(str(path))
        if img is None:  # 读不出来的图片（例如复制时中断）训练时也会出错：直接移到 rejected
            print(f'无法读取 {path.name}（文件已损坏？），已移到 {rejected}')
            k = ord('x')
        else:
            show = draw(img, label_path(path, data))
            cv2.putText(show, f'{i + 1}/{len(imgs)}  [space]ok [x]delete [b]back [q]quit',
                        (10, show.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        (255, 255, 255), 2)
            k = key(show)
        if k in OK_KEYS:
            reviewed.add(rel_key(path, root))
            i = next_unreviewed(imgs, reviewed, root, i + 1)
        elif k == ord('x'):
            reviewed.add(rel_key(path, root))
            label = label_path(path, data)
            shutil.move(str(path), str(rejected / path.name))
            if label.exists():
                shutil.move(str(label), str(rejected / label.name))
            i = next_unreviewed(imgs, reviewed, root, i + 1)
        elif k == ord('b'):  # 回到上一张还在的图片（可以重新检查）
            j = i - 1
            while j >= 0 and not imgs[j].exists():
                j -= 1
            i = j if j >= 0 else i
        elif k == ord('q'):
            break
        save_reviewed(state_file, reviewed)
    save_reviewed(state_file, reviewed)
    left = sum(1 for p in imgs if p.exists() and rel_key(p, root) not in reviewed)
    return len(reviewed), left


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description='逐张检查预标注结果')
    ap.add_argument('--images', required=True)
    ap.add_argument('--data', default=str(DATA), help='数据文件夹（默认 exercises/face_recognition/data）')
    a = ap.parse_args(argv)
    try:
        done, left = review(Path(a.images), Path(a.data))
    finally:
        cv2.destroyAllWindows()
    print(f'已检查 {done} 张，还剩 {left} 张未检查；删除的文件在 {Path(a.data) / "rejected"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
