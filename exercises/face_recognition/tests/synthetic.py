"""
合成的测试数据：人脸只用仓库里那张公有领域照片（hci_common/data/sample_face.jpg）。

不需要你自己的照片，也不联网。
"""
from pathlib import Path
from typing import List

import cv2
from hci_common.samples import sample_face
import numpy as np


def face_frame(x: int = 195, y: int = 115, scale: float = 1.0, flip: bool = False) -> np.ndarray:
    """640×480 的灰色画面，(x, y) 处贴一张公有领域人脸（scale 倍大小，flip 为左右翻转）。"""
    frame = np.full((480, 640, 3), 128, np.uint8)
    face = cv2.resize(sample_face(), None, fx=scale, fy=scale)
    if flip:
        face = np.ascontiguousarray(face[:, ::-1])
    h, w = face.shape[:2]
    frame[y:y + h, x:x + w] = face
    return frame


def write_faces(folder: Path, n: int = 3, prefix: str = 'img', **kwargs: object) -> List[Path]:
    """在 folder 里写 n 张人脸图片（人脸位置依次右移），返回路径列表。"""
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(n):
        path = folder / f'{prefix}_{i:03d}.jpg'
        cv2.imwrite(str(path), face_frame(x=150 + 20 * i, **kwargs))  # type: ignore[arg-type]
        paths.append(path)
    return paths


def write_video(path: Path, frames: List[np.ndarray], fps: float = 10.0) -> Path:
    """把若干帧写成一段 MJPG 视频。"""
    h, w = frames[0].shape[:2]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), fps, (w, h))
    for frame in frames:
        writer.write(frame)
    writer.release()
    return path
