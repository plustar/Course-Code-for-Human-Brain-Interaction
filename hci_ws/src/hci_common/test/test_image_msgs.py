"""图像消息与 NumPy 互转：7 种编码、行尾填充、可写副本、压缩图像、相机内参。"""
from types import SimpleNamespace
from typing import Any

from hci_common.camera_model import CameraModel
from hci_common.ros.image_msgs import (bgr_to_compressed, bgr_to_imgmsg, camera_info_msg,
                                       compressed_to_bgr, imgmsg_to_bgr)
import numpy as np
import pytest
from std_msgs.msg import Header

pytestmark = pytest.mark.ros

RNG = np.random.default_rng(0)


def fake_msg(img: np.ndarray, encoding: str, pad: int = 0) -> Any:
    """像 sensor_msgs/Image 一样排布的假消息：每行末尾可以有 pad 个填充字节。"""
    h, w = img.shape[:2]
    ch = 1 if img.ndim == 2 else img.shape[2]
    rows = np.zeros((h, w * ch + pad), np.uint8)
    rows[:, : w * ch] = img.reshape(h, -1)
    return SimpleNamespace(height=h, width=w, step=w * ch + pad, encoding=encoding,
                           data=rows.tobytes())


def test_bgr_with_row_padding_gives_a_writable_copy():
    img = RNG.integers(0, 256, (4, 5, 3), np.uint8)
    out = imgmsg_to_bgr(fake_msg(img, 'bgr8', pad=3))
    assert np.array_equal(out, img) and out.flags.writeable


@pytest.mark.parametrize('encoding, to_bgr', [
    ('rgb8', lambda img: img[:, :, ::-1]),
    ('8uc3', lambda img: img),
    ('bgra8', lambda img: img[:, :, :3]),
    ('rgba8', lambda img: img[:, :, 2::-1]),
])
def test_color_encodings(encoding, to_bgr):
    channels = 4 if encoding.endswith('a8') else 3
    img = RNG.integers(0, 256, (3, 4, channels), np.uint8)
    assert np.array_equal(imgmsg_to_bgr(fake_msg(img, encoding)), to_bgr(img))


@pytest.mark.parametrize('encoding', ['mono8', '8UC1'])
def test_gray_becomes_three_channels(encoding):
    img = RNG.integers(0, 256, (3, 4), np.uint8)
    out = imgmsg_to_bgr(fake_msg(img, encoding))
    assert out.shape == (3, 4, 3) and all(np.array_equal(out[:, :, c], img) for c in range(3))


def test_unsupported_encoding_is_reported():
    with pytest.raises(ValueError, match='yuv422'):
        imgmsg_to_bgr(fake_msg(np.zeros((2, 2, 3), np.uint8), 'yuv422'))


def test_bgr_to_imgmsg_roundtrip_keeps_the_header():
    img = RNG.integers(0, 256, (6, 7, 3), np.uint8)
    msg = bgr_to_imgmsg(img, Header(frame_id='camera'))
    assert (msg.encoding, msg.step, msg.header.frame_id) == ('bgr8', 21, 'camera')
    assert np.array_equal(imgmsg_to_bgr(msg), img)


@pytest.mark.parametrize('bad', [np.zeros((4, 4), np.uint8), np.zeros((4, 4, 3), np.float32)])
def test_bgr_to_imgmsg_rejects_other_arrays(bad):
    with pytest.raises(ValueError):
        bgr_to_imgmsg(bad)


def test_compressed_roundtrip():
    ramp = np.linspace(0, 255, 64, dtype=np.uint8)
    img = np.dstack([np.tile(ramp, (48, 1)), np.tile(ramp[:48, None], (1, 64)),
                     np.full((48, 64), 128, np.uint8)])  # 平滑的渐变图：JPEG 几乎无损
    msg = bgr_to_compressed(img, Header(frame_id='camera'), quality=95)
    assert msg.format == 'jpeg' and msg.header.frame_id == 'camera'
    out = compressed_to_bgr(msg)
    assert out.shape == img.shape and np.abs(out.astype(int) - img.astype(int)).mean() < 3


def test_compressed_garbage_is_reported():
    with pytest.raises(ValueError):
        compressed_to_bgr(SimpleNamespace(data=b'not an image', format='jpeg'))


def test_camera_info_matches_the_camera_model():
    camera = CameraModel.from_hfov(640, 480, 60.0)
    info = camera_info_msg(camera, Header(frame_id='camera'))
    assert (info.width, info.height, info.header.frame_id) == (640, 480, 'camera')
    assert info.k[0] == pytest.approx(camera.fx) and info.distortion_model == 'plumb_bob'
    assert CameraModel.from_camera_info(info) == camera  # 发布端与接收端得到同一个模型
