"""
第 5 步：准备"他人人脸"负样本（类别 1 = face）。

方式 A（推荐）：从 Open Images V7 下载带"Human face"标注的公开图片
  python get_openimages_faces.py --num 300
  - 标注许可 CC BY 4.0，图片许可 CC BY 2.0（Open Images 官方说明），可用于课程练习
  - 数据来源：验证集的框标注 CSV（Google Cloud Storage）与图片（AWS S3 公开存储）
方式 B：使用已获同意的他人照片（如同学互换），用 YuNet 自动标注为 face
  python get_openimages_faces.py --from-folder /路径/他人照片
输出：data/others/images/*.jpg 与 data/labels/others/images/*.txt
数量：与本人图片数量相当即可（例如本人 300 张 -> 他人 300 张）
"""
import argparse
from collections import defaultdict
import csv
import hashlib
from pathlib import Path
import random
import sys
from typing import Dict, List, Optional, Set, Tuple
import urllib.request

from common import (Box, DATA, detect_faces, ensure_dir, list_images, OTHERS_ID, to_yolo_line,
                    YuNet)
import cv2
import numpy as np

BOX_CSV = 'https://storage.googleapis.com/openimages/v5/validation-annotations-bbox.csv'
IMG_URL = 'https://open-images-dataset.s3.amazonaws.com/validation/{}.jpg'
FACE_MID = '/m/0dzct'  # Open Images 中 "Human face" 类别的编号


def fetch(url: str, timeout: float = 60) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def load_face_boxes(csv_path: Path) -> Tuple[Dict[str, List[Box]], Set[str]]:
    """
    读框标注 CSV，只留下人脸。

    返回 ({图片编号: [归一化的 (x1, y1, x2, y2)]}, {含"一群脸"大框的图片编号})。
    """
    boxes: Dict[str, List[Box]] = defaultdict(list)
    group: Set[str] = set()
    with open(csv_path, newline='') as f:
        for row in csv.DictReader(f):
            if row['LabelName'] != FACE_MID:
                continue
            if row['IsGroupOf'] == '1':  # "一群脸"用一个大框标注，不适合：整张图不用
                group.add(row['ImageID'])
            boxes[row['ImageID']].append(
                tuple(float(row[k]) for k in ('XMin', 'YMin', 'XMax', 'YMax')))  # type: ignore
    return dict(boxes), group


def candidates(boxes: Dict[str, List[Box]], group: Set[str], min_face: float = 0.12,
               max_faces: int = 4, seed: int = 0) -> List[str]:
    """挑出合适的图片：人脸不超过 max_faces 张、最大的脸至少占图像高度的 min_face，顺序随机。"""
    chosen = [img_id for img_id, b in boxes.items()
              if img_id not in group and 1 <= len(b) <= max_faces
              and max(y2 - y1 for _, y1, _, y2 in b) >= min_face]
    chosen.sort()
    random.Random(seed).shuffle(chosen)
    return chosen


def yolo_lines(boxes: List[Box]) -> str:
    """归一化的框 -> 他人类别的 YOLO 标注。"""
    return ''.join(f'{OTHERS_ID} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} '
                   f'{x2 - x1:.6f} {y2 - y1:.6f}\n' for x1, y1, x2, y2 in boxes)


def from_open_images(num: int, out_img: Path, out_lab: Path, data: Path = DATA,
                     min_face: float = 0.12, max_faces: int = 4, seed: int = 0) -> int:
    """下载 num 张带人脸框的公开图片（需要联网），返回实际下载的张数。"""
    cache = data / 'cache' / 'validation-annotations-bbox.csv'
    if not cache.exists():
        print('下载框标注 CSV（约 20–30 MB）……')
        ensure_dir(cache.parent)
        cache.write_bytes(fetch(BOX_CSV, timeout=600))
    boxes, group = load_face_boxes(cache)
    chosen = candidates(boxes, group, min_face, max_faces, seed)
    print(f'符合条件的图片 {len(chosen)} 张，下载其中 {num} 张……')
    got = 0
    for img_id in chosen:
        if got >= num:
            break
        try:
            raw = fetch(IMG_URL.format(img_id))
        except OSError as e:
            print(f'  跳过 {img_id}：{e}')
            continue
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            continue
        scale = 1024 / max(img.shape[:2])  # 缩小到最长边 1024，节省空间；框是归一化坐标，不受影响
        if scale < 1:
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(out_img / f'oi_{img_id}.jpg'), img)
        (out_lab / f'oi_{img_id}.txt').write_text(yolo_lines(boxes[img_id]))
        got += 1
        if got % 20 == 0:
            print(f'  已下载 {got}/{num}')
    return got


def from_folder(folder: Path, out_img: Path, out_lab: Path, conf: float = 0.7) -> int:
    """
    把文件夹里有人脸的照片复制过来，用 YuNet 标注为他人；返回这次新加入的张数。

    文件名由照片的内容决定（ext_ 加 12 位十六进制的指纹）：分几次从不同的文件夹导入，不会覆盖
    前一批；同一张照片导入两次也只留一份，否则它可能同时出现在训练集和验证集里。
    """
    detector = YuNet(min_confidence=conf)
    n = 0
    for path in list_images(folder):
        name = 'ext_' + hashlib.sha1(path.read_bytes()).hexdigest()[:12]
        if (out_img / f'{name}.jpg').exists():
            continue  # 以前导入过
        img = cv2.imread(str(path))
        if img is None:
            continue
        faces = detect_faces(detector, img)
        if not faces:
            continue
        h, w = img.shape[:2]
        cv2.imwrite(str(out_img / f'{name}.jpg'), img)
        (out_lab / f'{name}.txt').write_text(
            ''.join(to_yolo_line(OTHERS_ID, box, w, h) + '\n' for box, _, _ in faces))
        n += 1
    return n


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description='准备他人人脸的负样本')
    ap.add_argument('--num', type=int, default=300)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--min-face', type=float, default=0.12, help='最大那张脸至少占图像高度的比例')
    ap.add_argument('--max-faces', type=int, default=4)
    ap.add_argument('--from-folder', default='', help='改用这个文件夹里已获同意的照片')
    ap.add_argument('--conf', type=float, default=0.7)
    ap.add_argument('--data', default=str(DATA), help='数据文件夹（默认 exercises/face_recognition/data）')
    a = ap.parse_args(argv)

    data = Path(a.data)
    out_img = ensure_dir(data / 'others' / 'images')
    out_lab = ensure_dir(data / 'labels' / 'others' / 'images')
    if a.from_folder:
        n = from_folder(Path(a.from_folder), out_img, out_lab, a.conf)
    else:
        n = from_open_images(a.num, out_img, out_lab, data, a.min_face, a.max_faces, a.seed)
    print(f'完成：{n} 张 -> {out_img}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
