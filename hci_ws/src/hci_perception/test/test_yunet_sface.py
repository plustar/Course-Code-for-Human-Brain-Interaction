"""YuNet 检测与 SFace 两步法：空白图没有人脸、公有领域照片能检出；登记、比对、拒识陌生人。"""
from pathlib import Path

from hci_common.samples import sample_face, SAMPLE_FACE_RATIO
from hci_perception.recognition import sface
from hci_perception.recognition.yunet import clip_box, YuNet
import numpy as np
import pytest

needs_sface = pytest.mark.skipif(not Path(sface.default_model()).is_file(),
                                 reason='SFace 模型未下载：bash tools/download_models.sh')


def unit(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v)


def test_blank_image_has_no_face():
    assert YuNet().detect(np.full((240, 320, 3), 128, np.uint8)) == []


def test_public_domain_face_is_found_with_the_documented_size():
    img = sample_face()
    dets = YuNet().detect(img)
    assert len(dets) == 1 and dets[0].class_name == 'face' and dets[0].confidence > 0.8
    face = dets[0]
    assert abs(face.center_x - img.shape[1] / 2) < 30
    # 仿真按这个比例缩放头像，使检测框对应真实的人脸高度
    assert face.height / img.shape[0] == pytest.approx(SAMPLE_FACE_RATIO, abs=0.03)


def test_input_size_follows_each_image():
    detector = YuNet()
    big = np.zeros((480, 640, 3), np.uint8)
    big[100:349, 200:449] = sample_face()
    assert len(detector.detect(big)) == 1 and detector.size == (640, 480)
    assert len(detector.detect(sample_face())) == 1 and detector.size == (249, 249)


def test_large_frames_are_shrunk_before_detection_and_mapped_back():
    # 例如 Gazebo 里 waffle 的 1920×1080 相机：缩到 640×360 检测，框和关键点换算回原图
    import cv2

    frame = np.full((1080, 1920, 3), 128, np.uint8)
    frame[300:1047, 900:1647] = cv2.resize(sample_face(), (747, 747))  # 放大 3 倍
    detector = YuNet()
    rows = detector.detect_rows(frame)
    assert detector.size == (640, 360) and rows.shape == (1, 15)
    x, y, w, h = rows[0, :4]
    assert 900 <= x and x + w <= 1647 and 300 <= y and y + h <= 1047  # 在放人脸的地方
    eyes = rows[0, 4:8].reshape(2, 2)  # 两只眼睛的关键点
    assert ((eyes[:, 0] > x) & (eyes[:, 0] < x + w) & (eyes[:, 1] > y)
            & (eyes[:, 1] < y + h)).all()
    small = detector.detect_rows(cv2.resize(frame, (640, 360), interpolation=cv2.INTER_AREA))
    assert rows[0, :14] == pytest.approx(small[0, :14] * 3.0)  # 与直接检测缩小的画面一致


def test_missing_yunet_model():
    with pytest.raises(FileNotFoundError):
        YuNet('/no/such/yunet.onnx')


def test_clip_box_keeps_the_box_inside_the_image():
    row = np.array([-5.0, -5.0, 60.0, 60.0] + [0.0] * 11)
    assert clip_box(row, 40, 30) == (0, 0, 39, 29)


def test_enroll_averages_and_drops_outliers():
    rng = np.random.default_rng(0)
    me = unit(rng.normal(size=128))
    features = [unit(me + 0.02 * rng.normal(size=128)) for _ in range(6)]  # 6 张本人的照片
    features.append(unit(rng.normal(size=128)))  # 混进一张别人的照片
    enrolled = sface.enroll(features)
    plain_mean = unit(np.mean(features, axis=0))
    assert np.linalg.norm(enrolled) == pytest.approx(1.0, abs=1e-5)
    assert enrolled @ me > plain_mean @ me and enrolled @ me > 0.99


def test_enroll_needs_features():
    with pytest.raises(ValueError):
        sface.enroll([])


def test_missing_sface_model_says_how_to_download():
    with pytest.raises(FileNotFoundError, match='download_models.sh'):
        sface.load_sface('/no/such/sface.onnx')


@needs_sface
def test_two_step_recognizes_the_enrolled_face(tmp_path):
    img = sample_face()
    recognizer = sface.load_sface()
    row = YuNet().detect_rows(img)[0]
    gallery = tmp_path / 'me_sface.npy'
    np.save(gallery, sface.enroll([sface.embed(recognizer, img, row)]))
    two_step = sface.SFaceTwoStep(str(gallery), 'stu_2023123456')
    assert two_step.backend == 'sface'
    assert [d.class_name for d in two_step.detect(img)] == ['stu_2023123456']
    assert two_step.similarity(img, row) > 0.9


@needs_sface
def test_two_step_rejects_a_stranger(tmp_path):
    gallery = tmp_path / 'someone_else.npy'
    np.save(gallery, unit(np.random.default_rng(1).normal(size=128)).astype(np.float32))
    two_step = sface.SFaceTwoStep(str(gallery), 'stu_2023123456')
    assert [d.class_name for d in two_step.detect(sample_face())] == ['face']


@needs_sface
def test_two_step_needs_the_gallery_file():
    with pytest.raises(FileNotFoundError, match='登记文件'):
        sface.SFaceTwoStep('/no/such/me_sface.npy', 'stu_2023123456')
