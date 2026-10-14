"""
测试与仿真共用的一张公有领域人脸照片。

data/sample_face.jpg 截取自 NASA 拍摄的宇航员 Eileen Collins 的照片
（scikit-image 的 skimage.data.astronaut，注明 "No known copyright restrictions,
released into the public domain."）。它是仿真里的"陌生人"，也是测试里的"真实人脸"。
学生自己的照片一律不放进仓库。
"""
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).resolve().parent / 'data'
SAMPLE_FACE = DATA_DIR / 'sample_face.jpg'
# YuNet 检测框高度占这张图片高度的比例。仿真按它缩放头像，使检测框对应真实的人脸高度
SAMPLE_FACE_RATIO = 0.437


def sample_face() -> np.ndarray:
    """读入样例人脸（BGR 数组）。"""
    import cv2

    img = cv2.imread(str(SAMPLE_FACE))
    if img is None:
        raise FileNotFoundError(f'找不到样例人脸：{SAMPLE_FACE}')
    return img
