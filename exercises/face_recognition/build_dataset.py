"""
第 6 步：组装 YOLO 数据集，按"录制场次"划分训练集和验证集，并生成 data.yaml。

为什么按场次划分？同一段视频里相邻的帧几乎一样。如果随机划分，验证集里的图片在训练集里
都有"近似副本"，验证指标会虚高（数据泄漏）。按场次划分，才能检验模型在新的光照、
新的背景下还灵不灵。

用法：python build_dataset.py --student-id 2023123456                     # Track A（他人类=face）
      python build_dataset.py --student-id 2023123456 --other-class other  # Track B（标志物）
      python build_dataset.py --student-id 2023123456 --val-sessions s5 s6
输出：dataset/images/{train,val}、dataset/labels/{train,val}、dataset/data.yaml

两条 Track 共用本脚本：核心按类别下标（0=本人、1=他人）工作，不关心第 1 类叫什么；
--other-class 只决定写进 data.yaml 的第 1 类名字（Track A=face，Track B=other）。
"""
import argparse
from collections import Counter
from pathlib import Path
import random
import re
import shutil
import sys
from typing import Dict, List, Optional, Sequence, Tuple

from common import (DATA, ensure_dir, HERE, label_path, list_images, OTHERS_ID, read_labels,
                    SELF_ID)
from hci_common.identity import DEFAULT_OTHER_CLASS, TARGET_PREFIX

Item = Tuple[Path, Path]  # (图片, 标注)
MARKER = '# 由 build_dataset.py 生成'  # data.yaml 的第一行：重新生成时，只删除带这个标记的文件夹


def count_instances(label: Path) -> Counter:
    """标注文件里每个类别各有几个框。"""
    return Counter(int(line.split()[0]) for line in read_labels(label))


def split(data: Path, val_sessions: Optional[Sequence[str]] = None,
          others_val_ratio: float = 0.2, seed: int = 0) -> Tuple[Dict[str, List[Item]], int]:
    """
    把有标注的本人照片按场次分到 train 或 val，他人照片随机取 others_val_ratio 做验证。

    val_sessions 为空时用最后一个场次做验证。没有标注的本人照片不参加训练。
    返回 ({'train': [...], 'val': [...]}, 跳过的本人照片张数)。
    """
    sessions = sorted(p.name for p in (data / 'self').iterdir() if p.is_dir()) \
        if (data / 'self').is_dir() else []
    if len(sessions) < 2:
        raise SystemExit('至少需要 2 个场次（一个训练、一个验证）。请再录制一个场次。')
    val = set(val_sessions or sessions[-1:])
    unknown = val - set(sessions)
    if unknown:
        raise SystemExit(f'没有这些场次：{sorted(unknown)}（现有 {sessions}）')
    out: Dict[str, List[Item]] = {'train': [], 'val': []}
    skipped = 0
    for session in sessions:
        for img in list_images(data / 'self' / session):
            label = label_path(img, data)
            if read_labels(label):
                out['val' if session in val else 'train'].append((img, label))
            else:
                skipped += 1
    others = [(p, label_path(p, data)) for p in list_images(data / 'others' / 'images')]
    random.Random(seed).shuffle(others)
    n_val = int(len(others) * others_val_ratio)
    out['val'] += others[:n_val]
    out['train'] += others[n_val:]
    return out, skipped


def clear_output(out: Path, sources: Sequence[Path]) -> None:
    """
    删掉上一次生成的数据集，以便重新生成。

    只删除本脚本生成的文件夹（data.yaml 的第一行是 MARKER），并且原始照片不能在里面：
    --out 写错成 data 之类的文件夹时，拒绝执行，而不是把照片一起删掉。
    """
    if not out.exists():
        return
    config = out / 'data.yaml'
    generated = config.is_file() and config.read_text(encoding='utf-8').startswith(MARKER)
    root = out.resolve()
    if not generated or any(root in src.resolve().parents for src in sources):
        raise SystemExit(f'{out} 已经存在，但不是 build_dataset.py 生成的数据集（或者原始照片就在'
                         '里面）。为了不误删你的文件，请换一个 --out，或者确认无用后自己删掉它')
    shutil.rmtree(out)


def write(items: Dict[str, List[Item]], out: Path, student_id: str,
          other_class: str = DEFAULT_OTHER_CLASS) -> Dict[str, Counter]:
    """
    复制图片与标注，写 data.yaml；返回每个部分的框数（本人、他人）。

    other_class 是第 1 类（他人）的名字：Track A=face，Track B=other。
    """
    clear_output(out, [img for pairs in items.values() for img, _ in pairs])
    # 先写下标记：中途中断（Ctrl+C、磁盘满）时，下次运行仍然认得这个文件夹，可以删掉重来。
    # 没写完的 data.yaml 里没有 train、val，拿它训练会直接报错，不会用残缺的数据集训练
    config = ensure_dir(out) / 'data.yaml'
    config.write_text(f'{MARKER}\n# 还没有生成完：请重新运行 build_dataset.py\n', encoding='utf-8')
    counts: Dict[str, Counter] = {}
    for part, pairs in items.items():
        images, labels = ensure_dir(out / 'images' / part), ensure_dir(out / 'labels' / part)
        counts[part] = Counter()
        for img, label in pairs:
            shutil.copy2(img, images / img.name)
            if label.exists():
                shutil.copy2(label, labels / f'{img.stem}.txt')
                counts[part] += count_instances(label)
    config.write_text(
        f'{MARKER}\n'
        f'path: {out.resolve()}\n'
        'train: images/train\n'
        'val: images/val\n'
        'names:\n'
        f'  {SELF_ID}: {TARGET_PREFIX}{student_id}\n'
        f'  {OTHERS_ID}: {other_class}\n', encoding='utf-8')
    return counts


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description='按场次划分，组装 YOLO 数据集')
    ap.add_argument('--student-id', required=True, help='学号，类别名将是 stu_<学号>')
    ap.add_argument('--other-class', default=DEFAULT_OTHER_CLASS,
                    help='第 1 类（他人）的名字：Track A 用 face，Track B 用 other')
    ap.add_argument('--val-sessions', nargs='*', default=None, help='用作验证集的场次，默认最后一个')
    ap.add_argument('--others-val-ratio', type=float, default=0.2)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--data', default=str(DATA), help='数据文件夹（默认 exercises/face_recognition/data）')
    ap.add_argument('--out', default=str(HERE / 'dataset'))
    a = ap.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9]+', a.student_id):
        raise SystemExit(f'学号只能由字母和数字组成，收到 {a.student_id!r}')

    data, out = Path(a.data), Path(a.out)
    items, skipped = split(data, a.val_sessions, a.others_val_ratio, a.seed)
    counts = write(items, out, a.student_id, a.other_class)
    for part in ('train', 'val'):
        print(f'{part:5s}：{len(items[part]):4d} 张图片 | 本人框 {counts[part][SELF_ID]:4d} | '
              f'他人框 {counts[part][OTHERS_ID]:4d}')
    if skipped:
        print(f'注意：{skipped} 张本人照片没有标注（或标注为空），已跳过')
    print(f'已生成 {out / "data.yaml"}\n下一步：python train.py --data {out / "data.yaml"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
