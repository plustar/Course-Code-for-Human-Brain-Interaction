"""
recognizer_node 的节点测试。

header 原样复制；按 id_map 生成显示名；按 camera_info 算方位与距离，没有内参时用 hfov_deg；
限频且跳过的帧不解码；压缩图输入；收不到图像时提醒。
"""
import math
import time
from typing import Any, List, Sequence

from hci_common.camera_model import CameraModel
from hci_common.ros.image_msgs import bgr_to_compressed, bgr_to_imgmsg, camera_info_msg
from hci_common.ros.testing import LogSpy, Probe, spin_until
from hci_interfaces.msg import DetectionArray
from hci_perception.recognition.base import Detection
from hci_perception.ros import recognizer_node
from hci_perception.ros.recognizer_node import RecognizerNode
import numpy as np
import pytest
from rclpy.parameter import Parameter
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, CompressedImage, Image
from std_msgs.msg import Header

pytestmark = pytest.mark.ros

ME = Detection('stu_2023123456', 0.9, 100, 60, 140, 120)  # 框中心 u = 120，高 60 像素
OTHER = Detection('face', 0.8, 200, 80, 230, 120)


class FakeRecognizer:
    """测试替身：总是返回给定的检测结果，并记下收到的图像尺寸。"""

    backend = 'fake'

    def __init__(self, detections: Sequence[Detection] = (ME, OTHER)) -> None:
        self.detections = list(detections)
        self.shapes: List[Any] = []

    def detect(self, bgr: np.ndarray) -> List[Detection]:
        self.shapes.append(bgr.shape)
        return list(self.detections)


def make_node(namespace: str, recognizer: Any = None, **params: Any) -> RecognizerNode:
    params.setdefault('max_rate', 100.0)
    return RecognizerNode(recognizer or FakeRecognizer(), namespace=namespace,
                          parameter_overrides=[Parameter(k, value=v) for k, v in params.items()])


def image_msg(sec: int = 123, nanosec: int = 456, frame_id: str = 'camera') -> Image:
    header = Header(frame_id=frame_id)
    header.stamp.sec, header.stamp.nanosec = sec, nanosec
    return bgr_to_imgmsg(np.zeros((240, 320, 3), np.uint8), header)


def send_until_detected(node: RecognizerNode, probe: Probe, topic: str, msg: Any,
                        msg_type: Any = Image) -> DetectionArray:
    """反复发布同一帧（等发现完成），直到收到检测结果。"""
    pub = probe.talker(msg_type, topic)
    out = probe.listen(DetectionArray, 'detections')

    def got() -> bool:
        pub.publish(msg)
        return bool(out)

    assert spin_until([node, probe], got, timeout=10.0)
    return out[0]


def test_header_is_copied_and_image_size_reported(ros_context, namespace):
    node, probe = make_node(namespace), Probe(namespace)
    result = send_until_detected(node, probe, 'image_raw', image_msg(frame_id='my_camera'))
    assert (result.header.stamp.sec, result.header.stamp.nanosec) == (123, 456)
    assert result.header.frame_id == 'my_camera'
    assert (result.image_width, result.image_height) == (320, 240)


def test_display_names_follow_id_map(ros_context, namespace):
    node, probe = make_node(namespace, id_map=['stu_2023123456=张三']), Probe(namespace)
    result = send_until_detected(node, probe, 'image_raw', image_msg())
    assert [d.display_name for d in result.detections] == ['张三 2023123456', '他人']
    assert [d.class_name for d in result.detections] == ['stu_2023123456', 'face']
    assert (result.detections[0].x_min, result.detections[0].y_max) == (100, 120)


def test_bearing_and_distance_come_from_camera_info(ros_context, namespace):
    node, probe = make_node(namespace, target_height=0.22), Probe(namespace)
    camera = CameraModel(320, 240, fx=400.0, fy=400.0, cx=150.0, cy=120.0)  # 不在中心的主点
    info_pub = probe.talker(CameraInfo, 'camera_info')

    def info_received() -> bool:
        info_pub.publish(camera_info_msg(camera))
        return node.camera_info is not None

    assert spin_until([node, probe], info_received)
    me = send_until_detected(node, probe, 'image_raw', image_msg()).detections[0]
    assert me.bearing == pytest.approx(math.atan2(150.0 - 120.0, 400.0), abs=1e-6)  # 左正
    expected = 400.0 * 0.22 / 60.0 / math.cos(me.bearing)
    assert me.distance == pytest.approx(expected, rel=1e-5)


@pytest.mark.parametrize('info_size', [None, (640, 480)], ids=['no_camera_info', 'other_size'])
def test_falls_back_to_hfov_without_matching_camera_info(ros_context, namespace, info_size):
    node, probe = make_node(namespace, hfov_deg=60.0), Probe(namespace)
    if info_size:
        node.camera_info = CameraModel.from_hfov(*info_size, 90.0)  # 尺寸与图像不符：不用
    me = send_until_detected(node, probe, 'image_raw', image_msg()).detections[0]
    camera = CameraModel.from_hfov(320, 240, 60.0)
    assert me.bearing == pytest.approx(camera.bearing(120.0), abs=1e-6)
    assert me.distance == pytest.approx(camera.distance(120.0, 60.0, 0.22), rel=1e-5)


def test_zero_height_box_gives_nan_distance(ros_context, namespace):
    flat = Detection('stu_1', 0.9, 10, 50, 40, 50)
    node, probe = make_node(namespace, recognizer=FakeRecognizer([flat])), Probe(namespace)
    result = send_until_detected(node, probe, 'image_raw', image_msg())
    assert math.isnan(result.detections[0].distance)


@pytest.mark.parametrize('reliability, received', [('best_effort', True), ('reliable', False)])
def test_best_effort_publishers_need_a_best_effort_subscription(
        ros_context, namespace, reliability, received):
    # 机器人的相机按惯例用 Best Effort 发布：Reliable 的订阅者匹配不上它，一帧也收不到
    node = make_node(namespace, image_reliability=reliability)
    probe = Probe(namespace)
    pub = probe.talker(Image, 'image_raw', qos_profile_sensor_data)
    out = probe.listen(DetectionArray, 'detections')

    def sent() -> bool:
        pub.publish(image_msg())
        return bool(out)

    assert spin_until([node, probe], sent, timeout=3.0) is received


def test_rate_limit_skips_frames_before_decoding(ros_context, namespace, monkeypatch):
    decoded = []
    real = recognizer_node.imgmsg_to_bgr

    def counting(msg: Image) -> np.ndarray:  # 数一数解码了几帧
        decoded.append(msg)
        return real(msg)

    monkeypatch.setattr(recognizer_node, 'imgmsg_to_bgr', counting)
    recognizer = FakeRecognizer()
    node = make_node(namespace, recognizer=recognizer, max_rate=5.0)
    msg = image_msg()
    for _ in range(30):  # 一口气来 30 帧：只处理第一帧
        node.on_image(msg)
    assert len(recognizer.shapes) == 1 and len(decoded) == 1
    time.sleep(0.25)  # 过了一个周期（1/5 秒）：又可以处理一帧
    node.on_image(msg)
    assert len(recognizer.shapes) == 2


def test_compressed_input(ros_context, namespace):
    recognizer = FakeRecognizer()
    node = make_node(namespace, recognizer=recognizer, use_compressed=True)
    probe = Probe(namespace)
    jpeg = bgr_to_compressed(np.zeros((240, 320, 3), np.uint8), image_msg().header)
    result = send_until_detected(node, probe, 'image_raw/compressed', jpeg, CompressedImage)
    assert recognizer.shapes[0] == (240, 320, 3) and result.header.stamp.sec == 123


def test_reports_rate_or_warns_when_no_images_arrive(ros_context, namespace):
    node = make_node(namespace)
    spy = LogSpy.attach(node)
    node.report()  # 5 秒内一帧都没有
    assert 'ros2 topic list' in spy.text('warning')
    node.process(image_msg().header, np.zeros((240, 320, 3), np.uint8))
    node.report()
    assert '帧/秒' in spy.text('info')
