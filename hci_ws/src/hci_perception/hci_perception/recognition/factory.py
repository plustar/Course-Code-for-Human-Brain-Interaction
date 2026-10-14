"""按参数选择识别后端。"""
import os

from hci_perception.recognition.base import Recognizer


def create_recognizer(model: str = '', min_confidence: float = 0.5, imgsz: int = 416,
                      iou: float = 0.5, gallery: str = '', identity: str = '') -> Recognizer:
    """
    按参数选择识别后端。

      model 以 .onnx 结尾 -> yolo_onnx：练习 3 导出的模型，ROS 节点的常规用法
      model 以 .pt 结尾   -> ultralytics_pt：只在训练环境里可用
      gallery 不为空      -> sface：两步法，比对登记的本人特征，匹配上的标成 identity
      都没有给            -> yunet：演示模式，所有人脸都标成 face
    """
    for path in (model, gallery):
        if path and not os.path.isfile(path):
            raise FileNotFoundError(f'找不到文件：{path}（请使用绝对路径）')
    if model and gallery:
        raise ValueError('model 和 gallery 只能设置一个：要么用 YOLO 模型，要么用两步法')
    if model.endswith('.onnx'):
        from hci_perception.recognition.yolo_onnx import OnnxYolo
        return OnnxYolo(model, min_confidence, imgsz, iou)
    if model.endswith('.pt'):
        from hci_perception.recognition.ultralytics_pt import UltralyticsPt
        return UltralyticsPt(model, min_confidence, imgsz, iou)
    if model:
        raise ValueError(f'模型文件应为 .onnx（ROS 节点用）或 .pt（只在训练环境用）：{model}')
    if gallery:
        if not identity:
            raise ValueError('两步法需要设置 identity，即本人的类别名，如 stu_2023123456')
        from hci_perception.recognition.sface import SFaceTwoStep
        return SFaceTwoStep(gallery, identity, min_confidence=min_confidence)
    from hci_perception.recognition.yunet import YuNet
    return YuNet(min_confidence=min_confidence)
