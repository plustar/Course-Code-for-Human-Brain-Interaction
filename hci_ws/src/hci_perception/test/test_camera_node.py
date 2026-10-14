"""camera_node：图像与相机内参成对发布、frame_id、帧率、压缩图、中文错误提示、话题冲突警告。"""
from typing import Any, Optional

import cv2
from hci_common.camera_model import CameraModel
from hci_common.ros.testing import LogSpy, Probe, spin_until
from hci_perception.ros.camera_node import CameraNode
import numpy as np
import pytest
from rclpy.parameter import Parameter
from sensor_msgs.msg import CameraInfo, CompressedImage, Image

pytestmark = pytest.mark.ros


class FakeSource:
    """测试替身：不需要真摄像头的图像来源，第 n 帧的红色通道等于 n。"""

    def __init__(self, width: int = 320, height: int = 240, native_fps: float = 0.0) -> None:
        self.size = (width, height)
        self.native_fps = native_fps
        self.frames = 0
        self.released = False

    def read(self) -> Optional[np.ndarray]:
        self.frames += 1
        img = np.zeros((self.size[1], self.size[0], 3), np.uint8)
        img[:, :, 2] = self.frames % 256
        return img

    def release(self) -> None:
        self.released = True


def make_node(namespace: str, source: Any = None, **params: Any) -> CameraNode:
    return CameraNode(source or FakeSource(), namespace=namespace,
                      parameter_overrides=[Parameter(k, value=v) for k, v in params.items()])


def test_image_and_camera_info_are_published_in_pairs(ros_context, namespace):
    node = make_node(namespace, frame_id='test_camera', hfov_deg=60.0)
    probe = Probe(namespace)
    images, infos = probe.listen(Image, 'image_raw'), probe.listen(CameraInfo, 'camera_info')
    assert spin_until([node, probe], lambda: len(images) >= 3 and len(infos) >= 3)
    image = images[-1]
    assert (image.width, image.height, image.encoding) == (320, 240, 'bgr8')
    assert image.header.frame_id == 'test_camera'
    pair = [i for i in infos if i.header.stamp == image.header.stamp]
    assert pair, '每帧图像都应有同一时间戳的 camera_info'
    assert CameraModel.from_camera_info(pair[0]) == CameraModel.from_hfov(320, 240, 60.0)


def test_publish_rate_follows_fps(ros_context, namespace):
    node = make_node(namespace, fps=20.0)
    assert node.timer.timer_period_ns == pytest.approx(1e9 / 20.0)
    probe = Probe(namespace)
    images = probe.listen(Image, 'image_raw')
    assert spin_until([node, probe], lambda: len(images) >= 21, timeout=5.0)
    stamps = [m.header.stamp.sec + m.header.stamp.nanosec * 1e-9 for m in images]
    rate = (len(stamps) - 1) / (stamps[-1] - stamps[0])
    assert 15.0 < rate < 25.0


def test_video_file_plays_at_its_own_frame_rate(ros_context, namespace):
    node = make_node(namespace, source=FakeSource(native_fps=12.0), fps=30.0)
    assert node.timer.timer_period_ns == pytest.approx(1e9 / 12.0)


def test_compressed_images_on_request(ros_context, namespace):
    node = make_node(namespace, publish_compressed=True)
    probe = Probe(namespace)
    jpegs = probe.listen(CompressedImage, 'image_raw/compressed')
    assert spin_until([node, probe], lambda: len(jpegs) >= 1)
    decoded = cv2.imdecode(np.frombuffer(jpegs[0].data, np.uint8), cv2.IMREAD_COLOR)
    assert jpegs[0].format == 'jpeg' and decoded.shape == (240, 320, 3)


def test_no_compressed_topic_by_default(ros_context, namespace):
    node = make_node(namespace)
    assert node.pub_compressed is None


def test_missing_video_file_fails_with_a_chinese_message(ros_context, namespace):
    with pytest.raises(FileNotFoundError, match='绝对路径'):
        CameraNode(namespace=namespace,
                   parameter_overrides=[Parameter('source', value='/no/such/video.mp4')])


def test_warns_when_another_node_publishes_the_same_topic(ros_context, namespace):
    node = make_node(namespace)
    spy = LogSpy.attach(node)
    node.check_topic_conflict()
    assert not node.warned_conflict  # 只有自己在发布：不警告
    probe = Probe(namespace)
    probe.talker(Image, 'image_raw')  # 例如同时启动了仿真相机
    topic = node.pub_image.topic_name
    assert spin_until([node, probe], lambda: node.count_publishers(topic) == 2)
    node.check_topic_conflict()
    assert node.warned_conflict and '两路画面会交替出现' in spy.text('warning')


def test_releases_the_source_on_destroy(ros_context, namespace):
    source = FakeSource()
    node = make_node(namespace, source=source)
    node.destroy_node()
    assert source.released
