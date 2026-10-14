"""按参数选择识别后端，以及用错参数时的中文提示。"""
from pathlib import Path
import sys

from hci_perception.recognition import sface
from hci_perception.recognition.factory import create_recognizer
import numpy as np
import pytest


def test_default_is_the_yunet_demo_mode():
    assert create_recognizer().backend == 'yunet'


def test_onnx_model_uses_the_onnx_backend(tiny_yolo):
    pytest.importorskip('onnxruntime')
    recognizer = create_recognizer(tiny_yolo(np.zeros((1, 6, 4), np.float32)), imgsz=320)
    assert recognizer.backend == 'yolo_onnx'


def test_pt_model_outside_training_env_explains_why(tmp_path, monkeypatch):
    pt = tmp_path / 'best.pt'
    pt.write_bytes(b'not really a model')
    monkeypatch.setitem(sys.modules, 'ultralytics', None)  # 模拟 ROS 环境：没有 ultralytics
    with pytest.raises(RuntimeError, match='hci-train'):
        create_recognizer(str(pt))


@pytest.mark.skipif(not Path(sface.default_model()).is_file(),
                    reason='SFace 模型未下载：bash tools/download_models.sh')
def test_gallery_uses_the_two_step_backend(tmp_path):
    gallery = tmp_path / 'me_sface.npy'
    np.save(gallery, np.ones(128, np.float32))
    assert create_recognizer(gallery=str(gallery), identity='stu_1').backend == 'sface'


@pytest.fixture
def files(tmp_path):
    for name in ('best.onnx', 'best.txt', 'me_sface.npy'):
        (tmp_path / name).write_bytes(b'x')
    return tmp_path


@pytest.mark.parametrize('kwargs, error, hint', [
    ({'model': '/no/such/best.onnx'}, FileNotFoundError, '绝对路径'),
    ({'model': 'best.onnx', 'gallery': 'me_sface.npy'}, ValueError, '只能设置一个'),
    ({'model': 'best.txt'}, ValueError, '.onnx'),
    ({'gallery': 'me_sface.npy'}, ValueError, 'identity'),
], ids=['missing_file', 'model_and_gallery', 'bad_extension', 'gallery_without_identity'])
def test_wrong_parameters_are_explained(files, kwargs, error, hint):
    kwargs = {k: (v if v.startswith('/') else str(files / v)) for k, v in kwargs.items()}
    with pytest.raises(error, match=hint):
        create_recognizer(**kwargs)
