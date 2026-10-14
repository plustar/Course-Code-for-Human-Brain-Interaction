"""试用模型与两步法：predict.py 统计本人、他人；sface_verify.py 登记与比对（没有 SFace 模型时跳过）。"""
from pathlib import Path

import numpy as np
from predict import main as predict_main
from predict import predict
import pytest
from synthetic import write_faces

try:
    from hci_perception.recognition import sface
    from hci_perception.testing import make_tiny_yolo, onnx_available
except ImportError:  # pragma: no cover
    pytest.skip('找不到 hci_perception', allow_module_level=True)

needs_onnx = pytest.mark.skipif(not onnx_available(), reason='需要 onnx 包生成微型模型')
needs_sface = pytest.mark.skipif(not Path(sface.default_model()).is_file(),
                                 reason='SFace 模型未下载：bash tools/download_models.sh')


def tiny_model(tmp_path: Path) -> str:
    """不管输入什么，都"认出"一个本人和一个他人的微型模型。"""
    raw = np.zeros((1, 6, 2), np.float32)
    raw[0, :4, 0], raw[0, 4, 0] = [100, 115, 100, 100], 0.9
    raw[0, :4, 1], raw[0, 5, 1] = [220, 140, 40, 40], 0.8
    return str(make_tiny_yolo(tmp_path / 'best.onnx', raw, names=['stu_2023123456', 'face']))


@needs_onnx
def test_predict_counts_and_saves(tmp_path):
    write_faces(tmp_path / 'pics', n=3)
    counts = predict(tiny_model(tmp_path), str(tmp_path / 'pics'), name='张三',
                     save=tmp_path / 'out', show=False)
    assert counts == {'images': 3, 'me': 3, 'other': 3}
    assert sorted(p.name for p in (tmp_path / 'out').iterdir()) == [
        'img_000.jpg', 'img_001.jpg', 'img_002.jpg']


@needs_onnx
def test_predict_command_line(tmp_path, capsys):
    write_faces(tmp_path / 'pics', n=2)
    assert predict_main(['--model', tiny_model(tmp_path), '--source', str(tmp_path / 'pics'),
                         '--save', str(tmp_path / 'out')]) == 0
    assert '共 2 张画面：检出本人 2 次、他人 2 次' in capsys.readouterr().out


@needs_sface
def test_enroll_and_verify(tmp_path):
    from sface_verify import enroll_from, main, verify
    write_faces(tmp_path / 'me', n=4)
    gallery, features = enroll_from(tmp_path / 'me')
    assert len(features) == 4 and (features @ gallery).min() > 0.9
    assert verify(str(tmp_path / 'me'), gallery, show=False) == {'images': 4, 'me': 4}
    stranger = np.random.default_rng(0).normal(size=128)
    stranger /= np.linalg.norm(stranger)
    assert verify(str(tmp_path / 'me'), stranger, show=False)['stranger'] == 4
    path = tmp_path / 'me_sface.npy'  # 命令行：登记后比对
    assert main(['--gallery', str(path), 'enroll', '--images', str(tmp_path / 'me')]) == 0
    assert main(['--gallery', str(path), 'run', '--source', str(tmp_path / 'me'),
                 '--save', str(tmp_path / 'out')]) == 0
    assert len(list((tmp_path / 'out').iterdir())) == 4


def test_verify_without_enrolment_explains(tmp_path, capsys):
    from sface_verify import main
    assert main(['--gallery', str(tmp_path / 'none.npy'), 'run', '--source', '0']) == 1
    assert 'enroll' in capsys.readouterr().out
