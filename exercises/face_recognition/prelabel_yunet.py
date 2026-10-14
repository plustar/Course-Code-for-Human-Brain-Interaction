"""
第 3 步：用 YuNet 自动预标注人脸，生成 YOLO 格式的标签（之后只需人工检查）。

用法：python prelabel_yunet.py --images data/self --class-id 0 --largest-only
      python prelabel_yunet.py --images data/others/images --class-id 1
标签位置：data/labels/<与 data 下图片相同的相对路径>.txt
  例：data/self/s1/s1_000012.jpg -> data/labels/self/s1/s1_000012.txt
类别约定：0 = stu_<学号>（本人），1 = face（他人）
--largest-only：自己的照片里只标最大的一张脸（画面里偶尔出现的别人不会被误标成本人）
"""
import argparse
from dataclasses import dataclass, field
from pathlib import Path
import sys
from typing import List, Optional

from common import (DATA, detect_faces, ensure_dir, label_path, list_images, print_list,
                    to_yolo_line, YuNet)
import cv2
from hci_common.identity import OTHERS, TARGET_PREFIX


@dataclass
class PrelabelResult:
    """预标注的统计。"""

    images: int = 0
    boxes: int = 0
    no_face: List[str] = field(default_factory=list)  # 没检测到人脸的图片
    many_faces: List[str] = field(default_factory=list)  # 检测到多张人脸的图片


def prelabel(images: Path, class_id: int, data: Path = DATA, largest_only: bool = False,
             conf: float = 0.7, min_size: float = 0.04) -> PrelabelResult:
    """给 images 下的每张图片写一个 YOLO 标签文件；min_size：框高度不足图像高度这个比例的忽略。"""
    detector = YuNet(min_confidence=conf)
    result = PrelabelResult()
    for path in list_images(images):
        img = cv2.imread(str(path))
        if img is None:
            continue
        h, w = img.shape[:2]
        faces = detect_faces(detector, img, min_size)
        if largest_only:
            faces = faces[:1]
        label = label_path(path, data)
        ensure_dir(label.parent)
        label.write_text(''.join(to_yolo_line(class_id, box, w, h) + '\n' for box, _, _ in faces))
        result.images += 1
        result.boxes += len(faces)
        if not faces:
            result.no_face.append(str(path))
        elif len(faces) > 1:
            result.many_faces.append(str(path))
    (Path(data) / 'classes.txt').write_text(f'{TARGET_PREFIX}self\n{OTHERS}\n')  # 给标注工具看的类别表
    return result


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description='用 YuNet 自动预标注人脸')
    ap.add_argument('--images', required=True, help='图片文件夹，必须在数据文件夹里')
    ap.add_argument('--class-id', type=int, required=True, choices=[0, 1])
    ap.add_argument('--largest-only', action='store_true')
    ap.add_argument('--conf', type=float, default=0.7)
    ap.add_argument('--min-size', type=float, default=0.04, help='框高度小于图像高度该比例的忽略')
    ap.add_argument('--data', default=str(DATA), help='数据文件夹（默认 exercises/face_recognition/data）')
    a = ap.parse_args(argv)

    r = prelabel(Path(a.images), a.class_id, Path(a.data), a.largest_only, a.conf, a.min_size)
    print(f'处理 {r.images} 张，共 {r.boxes} 个框。没检测到人脸 {len(r.no_face)} 张，'
          f'多张人脸 {len(r.many_faces)} 张')
    print_list('没检测到人脸（建议检查或删除）', r.no_face)
    print_list('多张人脸（请检查）', r.many_faces)
    print('下一步：python review_labels.py --images', a.images)
    return 0


if __name__ == '__main__':
    sys.exit(main())
