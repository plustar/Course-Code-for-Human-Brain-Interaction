"""
viewer_node 的节点测试。

按时间戳配对；没人看时不画；没有图形界面不弹窗；空格键暂停机器人；他人默认打码；
状态条显示状态与问候语。
"""
import math
import time
from typing import Any, List

import cv2
from hci_common.ros.image_msgs import bgr_to_imgmsg
from hci_common.ros.testing import Probe, spin_for, spin_until
from hci_interfaces.msg import BehaviorState, Detection, DetectionArray
from hci_perception.ros.viewer_node import STATE_STYLE, ViewerNode
import numpy as np
import pytest
from rclpy.parameter import Parameter
from sensor_msgs.msg import Image
from std_msgs.msg import Header
from std_srvs.srv import SetBool

pytestmark = pytest.mark.ros


def make_node(namespace: str, **params: Any) -> ViewerNode:
    params.setdefault('show_window', False)
    return ViewerNode(namespace=namespace,
                      parameter_overrides=[Parameter(k, value=v) for k, v in params.items()])


def header(sec: int) -> Header:
    h = Header(frame_id='camera')
    h.stamp.sec = sec
    return h


def detection(class_name: str, box: List[int], name: str) -> Detection:
    d = Detection(class_name=class_name, display_name=name, confidence=0.9)
    d.x_min, d.y_min, d.x_max, d.y_max = box
    d.bearing, d.distance = 0.0, 1.5
    return d


def detections(sec: int) -> DetectionArray:
    msg = DetectionArray(header=header(sec), image_width=320, image_height=240)
    msg.detections = [detection('stu_2023123456', [40, 60, 120, 160], '张三 2023123456'),
                      detection('face', [180, 60, 260, 160], '他人')]
    return msg


def noisy_image() -> np.ndarray:
    return np.random.default_rng(0).integers(0, 256, (240, 320, 3), np.uint8)


def colors_in(img: np.ndarray, box: List[int]) -> int:
    """框内部（避开边框和标签）有多少种颜色。"""
    x1, y1, x2, y2 = box
    return len(np.unique(img[y1 + 6:y2 - 6, x1 + 6:x2 - 6].reshape(-1, 3), axis=0))


def test_image_and_detections_are_paired_by_timestamp(ros_context, namespace):
    node, probe = make_node(namespace), Probe(namespace)
    overlays = probe.listen(Image, 'overlay')
    images, dets = probe.talker(Image, 'image_raw'), probe.talker(DetectionArray, 'detections')
    assert spin_until([node, probe], lambda: node.pub.get_subscription_count() > 0)

    def publish_pair() -> bool:
        images.publish(bgr_to_imgmsg(noisy_image(), header(100)))
        dets.publish(detections(100))
        return bool(overlays)

    assert spin_until([node, probe], publish_pair, timeout=10.0)
    assert overlays[0].header.stamp.sec == 100 and overlays[0].width == 320

    overlays.clear()  # 时间戳相差 5 秒，超过 slop：不配对
    for _ in range(10):
        images.publish(bgr_to_imgmsg(noisy_image(), header(200)))
        dets.publish(detections(205))
        spin_for([node, probe], 0.05)
    spin_for([node, probe], 0.3)
    assert not [m for m in overlays if m.header.stamp.sec >= 200]


def test_draws_nothing_when_nobody_is_watching(ros_context, namespace, monkeypatch):
    node = make_node(namespace)  # 不弹窗，也没人订阅 overlay
    rendered = []
    monkeypatch.setattr(node, 'render', lambda *args: rendered.append(args))
    node.on_pair(bgr_to_imgmsg(noisy_image(), header(1)), detections(1))
    assert not rendered


def test_no_window_without_a_display(ros_context, namespace, monkeypatch):
    monkeypatch.delenv('DISPLAY', raising=False)
    monkeypatch.delenv('WAYLAND_DISPLAY', raising=False)
    assert make_node(namespace, show_window=True).show is False


def test_space_key_pauses_and_resumes_the_robot(ros_context, namespace, monkeypatch):
    monkeypatch.setattr(cv2, 'imshow', lambda *args: None)
    monkeypatch.setattr(cv2, 'waitKey', lambda delay: 32)  # 按下空格键
    node, probe = make_node(namespace), Probe(namespace)
    requests: List[bool] = []

    def enable(request: SetBool.Request, response: SetBool.Response) -> SetBool.Response:
        requests.append(request.data)
        response.success = True
        return response

    probe.create_service(SetBool, 'behavior_node/enable', enable)
    assert spin_until([node, probe], node.enable_client.service_is_ready)
    node.display(noisy_image())  # 机器人在运行：请求暂停
    assert spin_until([node, probe], lambda: requests == [False])
    node.state = BehaviorState(enabled=False)
    node.display(noisy_image())  # 已暂停：请求恢复
    assert spin_until([node, probe], lambda: requests == [False, True])


def test_others_are_pixelated_but_the_target_is_not(ros_context, namespace):
    out = make_node(namespace).render(noisy_image(), detections(1))
    me, other = detections(1).detections
    target_box = [me.x_min, me.y_min, me.x_max, me.y_max]
    other_box = [other.x_min, other.y_min, other.x_max, other.y_max]
    assert colors_in(out, other_box) <= 64  # 8×8 个色块
    assert colors_in(out, target_box) > 1000  # 本人保持原样


def test_blurring_can_be_turned_off(ros_context, namespace):
    out = make_node(namespace, blur_others=False).render(noisy_image(), detections(1))
    other = detections(1).detections[1]
    assert colors_in(out, [other.x_min, other.y_min, other.x_max, other.y_max]) > 1000


def test_status_bar_shows_state_target_and_greeting(ros_context, namespace):
    node = make_node(namespace)
    state = BehaviorState(state=BehaviorState.APPROACH, reason='靠近', enabled=True,
                          target_name='张三 2023123456', target_distance=1.6,
                          target_bearing=math.radians(4.0))
    text, color = node.status_text(state)
    assert text == '靠近：靠近  目标 张三 2023123456 1.6 m +4°'
    assert color == STATE_STYLE[BehaviorState.APPROACH][1]
    paused, _ = node.status_text(BehaviorState(state=BehaviorState.STOP, reason='已暂停'))
    assert '按空格键恢复' in paused

    node.state, node.greeting = state, ('你好，张三！', time.monotonic())
    white = np.full((240, 320, 3), 255, np.uint8)
    out = node.render(white, DetectionArray())
    b, g, r = (int(v) for v in out[236, 316])
    assert b > r and not (out[:150] != 255).any()  # 只有底部叠加了蓝色的状态条
