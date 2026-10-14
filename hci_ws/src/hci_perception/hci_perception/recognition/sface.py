"""
两步法后端：YuNet 检测人脸，再用 SFace 把人脸变成 128 维特征，和登记的本人特征比较。

与两类 YOLO 相比：YOLO 只会在"本人 / face"之间二选一，没有"陌生人"的概念；两步法比较
余弦相似度，低于阈值就判为他人，天然能拒识从没见过的人。OpenCV 给出的阈值是 0.363。
本人的特征（登记文件，如 me_sface.npy）由练习 3 的 sface_verify.py enroll 生成，只留在本机。
SFace 模型约 37 MB，不随仓库发布，用 bash tools/download_models.sh 下载。
"""
import os
from pathlib import Path
from typing import Any, Iterable, List, Union

from hci_common.identity import OTHERS
from hci_perception.recognition.base import Detection
from hci_perception.recognition.yunet import clip_box, MODELS_DIR, YuNet
import numpy as np

THRESHOLD = 0.363  # 余弦相似度不低于它就认为是同一个人


def default_model() -> str:
    """SFace 模型的默认位置（与 YuNet 放在同一个目录）。"""
    return str(MODELS_DIR / 'face_recognition_sface_2021dec.onnx')


def load_sface(model_path: str = '') -> Any:
    """创建 OpenCV 的 SFace 识别器；模型不存在时提示怎么下载。"""
    import cv2

    path = model_path or default_model()
    if not os.path.isfile(path):
        raise FileNotFoundError(f'找不到 SFace 模型：{path}。'
                                '请在仓库根目录运行 bash tools/download_models.sh 下载')
    return cv2.FaceRecognizerSF.create(path, '')


def embed(recognizer: Any, bgr: np.ndarray, face_row: np.ndarray) -> np.ndarray:
    """按 5 个关键点对齐、裁剪成 112×112，再提取单位长度的 128 维特征。"""
    aligned = recognizer.alignCrop(bgr, face_row)
    feature = recognizer.feature(aligned).flatten()
    return feature / (np.linalg.norm(feature) + 1e-9)


def enroll(features: Iterable[np.ndarray]) -> np.ndarray:
    """
    由多张照片的特征生成登记特征：先取平均，再剔除与平均差太多的（多半是别人或检测错误）。

    返回单位长度的平均特征，保存成 .npy 即为登记文件。
    """
    feats = np.array(list(features), dtype=np.float32)
    if feats.ndim != 2 or len(feats) == 0:
        raise ValueError('没有可用的人脸特征')
    mean = _unit(feats.mean(axis=0))
    keep = feats @ mean >= THRESHOLD
    if keep.sum() >= max(3, len(feats) // 2) and not keep.all():
        mean = _unit(feats[keep].mean(axis=0))
    return mean


def _unit(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v) + 1e-9)


class SFaceTwoStep:
    """
    两步法识别：相似度不低于阈值的人脸标成 identity（如 stu_2023123456），其余标成 face。

    gallery：登记文件（.npy）的路径，或者已经读进来的登记特征。
    """

    backend = 'sface'

    def __init__(self, gallery: Union[str, np.ndarray], identity: str, yunet_model: str = '',
                 sface_model: str = '', min_confidence: float = 0.6,
                 threshold: float = THRESHOLD) -> None:
        if isinstance(gallery, str):
            if not Path(gallery).is_file():
                raise FileNotFoundError(f'找不到登记文件：{gallery}')
            gallery = np.load(gallery)
        self.gallery = _unit(np.asarray(gallery, dtype=np.float32).flatten())
        self.identity, self.threshold = identity, threshold
        self.yunet = YuNet(yunet_model, min_confidence)
        self.sface = load_sface(sface_model)

    def similarity(self, bgr: np.ndarray, face_row: np.ndarray) -> float:
        """这张脸与登记特征的余弦相似度。"""
        return float(embed(self.sface, bgr, face_row) @ self.gallery)

    def detect(self, bgr: np.ndarray) -> List[Detection]:
        """检测并比对；置信度沿用 YuNet 的检测分数。"""
        h, w = bgr.shape[:2]
        out = []
        for row in self.yunet.detect_rows(bgr):
            same = self.similarity(bgr, row) >= self.threshold
            out.append(Detection(self.identity if same else OTHERS, float(row[14]),
                                 *clip_box(row, w, h)))
        return out
