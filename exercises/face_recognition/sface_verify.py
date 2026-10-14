"""
拓展：两步法人脸识别——YuNet 检测，再用 SFace 比对特征（不需要训练）。

与"两类 YOLO"对比：
  - 两类 YOLO 只会在"本人 / face"之间二选一，没有"陌生人"的概念；
  - 两步法把人脸变成 128 维特征，和登记的本人特征比较余弦相似度，低于阈值就判为陌生人，
    天然能拒识从没见过的人。OpenCV 给出的阈值是 0.363（不低于它视为同一人）。
登记文件 data/me_sface.npy 属于生物识别信息，只留在本机。ROS 识别节点也能直接用它：
  ros2 launch hci_bringup perception.launch.py gallery:=/绝对路径/me_sface.npy identity:=stu_学号

用法：
  bash ../tools/download_models.sh                           # 第一次使用：下载 SFace 模型
  python sface_verify.py enroll --images data/self/s1        # 登记本人（最多取 30 张）
  python sface_verify.py run --source 0                      # 摄像头实时比对
  python sface_verify.py run --source data/test/others --save out/   # 批量测试
"""
import argparse
from collections import Counter
from pathlib import Path
import sys
from typing import List, Optional, Tuple

from common import (clip_box, DATA, detect_faces, ensure_dir, frames, list_images, show_or_save,
                    YuNet)
import cv2
from hci_perception.overlay import Label, Painter
from hci_perception.recognition import sface
from hci_perception.recognition.sface import SFaceTwoStep
import numpy as np

GALLERY = DATA / 'me_sface.npy'  # 你的人脸特征（生物识别信息），只留在本机


def enroll_from(images: Path, max_images: int = 30,
                conf: float = 0.7) -> Tuple[np.ndarray, np.ndarray]:
    """从照片里每张取最大的一张脸，提取特征并登记。返回 (登记特征, 各张照片的特征)。"""
    detector, recognizer = YuNet(min_confidence=conf), sface.load_sface()
    features = []
    for path in list_images(images)[:max_images]:
        img = cv2.imread(str(path))
        faces = detect_faces(detector, img) if img is not None else []
        if faces:
            features.append(sface.embed(recognizer, img, faces[0][2]))
    if not features:
        raise SystemExit('没有检测到人脸，请换一批照片')
    return sface.enroll(features), np.array(features)


def verify(source: str, gallery: np.ndarray, threshold: float = sface.THRESHOLD,
           min_confidence: float = 0.5, save: Optional[Path] = None,
           show: bool = True) -> Counter:
    """
    逐帧比对每张人脸与登记特征；返回画面数与判为本人、陌生人的次数。

    用的就是识别节点的两步法后端（检测阈值也与节点的默认值 0.5 相同），只是多显示相似度。
    """
    two_step, painter = SFaceTwoStep(gallery, '本人', min_confidence=min_confidence,
                                     threshold=threshold), Painter()
    counts: Counter = Counter()
    for fname, img in frames(source):
        if img is None:
            continue
        counts['images'] += 1
        h, w = img.shape[:2]
        labels = []
        for row in two_step.yunet.detect_rows(img):
            similarity = two_step.similarity(img, row)
            is_me = similarity >= threshold
            counts['me' if is_me else 'stranger'] += 1
            labels.append(Label(clip_box(row, w, h),
                                f'{"本人" if is_me else "陌生人"} 相似度 {similarity:.2f}', is_me))
        if not show_or_save(painter.draw(img, labels), fname, save, show,
                            'SFace verify (q to quit)'):
            break
    if save is None and show:
        cv2.destroyAllWindows()
    return counts


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description='两步法人脸识别：YuNet + SFace')
    ap.add_argument('--gallery', default=str(GALLERY), help='登记文件（默认 data/me_sface.npy）')
    sub = ap.add_subparsers(dest='cmd', required=True)
    e = sub.add_parser('enroll', help='登记本人')
    e.add_argument('--images', required=True)
    e.add_argument('--max', type=int, default=30)
    r = sub.add_parser('run', help='实时或批量比对')
    r.add_argument('--source', default='0')
    r.add_argument('--save', default='')
    a = ap.parse_args(argv)

    gallery = Path(a.gallery)
    if a.cmd == 'enroll':
        mean, features = enroll_from(Path(a.images), a.max)
        ensure_dir(gallery.parent)
        np.save(gallery, mean)
        sims = features @ mean
        print(f'已登记 {len(features)} 张 -> {gallery}；'
              f'登记照片与平均特征的相似度 {sims.min():.2f}–{sims.max():.2f}')
        return 0
    if not gallery.is_file():
        print(f'还没有登记（{gallery}）：先运行 python sface_verify.py enroll --images data/self/s1')
        return 1
    save = Path(a.save) if a.save else None
    c = verify(a.source, np.load(gallery), save=save)
    print(f'共 {c["images"]} 张画面：判为本人 {c["me"]} 次、陌生人 {c["stranger"]} 次'
          f'（阈值 {sface.THRESHOLD}）' + (f'；带框图片保存在 {save}' if save else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
