"""公有领域样例人脸：仿真里的陌生人，也是测试里的真实人脸。"""
from hci_common.samples import SAMPLE_FACE, sample_face, SAMPLE_FACE_RATIO


def test_sample_face_loads_as_bgr():
    img = sample_face()
    assert img.shape == (249, 249, 3) and img.dtype.name == 'uint8'
    assert SAMPLE_FACE.is_file() and 0.0 < SAMPLE_FACE_RATIO < 1.0
