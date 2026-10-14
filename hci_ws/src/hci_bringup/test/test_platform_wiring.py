"""
换平台只改参数：同一套节点接到 Gazebo 小车与 TurtleBot 4 上（用"假机器人"代替真机与仿真）。

假机器人订阅 /cmd_vel（TwistStamped，与 Lyrical 的 Gazebo 和 Jazzy 的 TurtleBot 4 相同）；
camera:=robot 时它还发布相机的图像和内参：像 OAK-D 一样用 Best Effort（TurtleBot 4），
或者像 ros_gz 的图像桥一样用 Reliable（Gazebo）。检查的是接线：图像进得去、订阅的可靠性
与发布端相容、检测结果出得来、速度指令按机器人要的类型发到对的话题上。
"""
from contextlib import contextmanager
import os
import tempfile
import time
from typing import Any, Iterator, List, Optional

import cv2
from geometry_msgs.msg import Twist, TwistStamped
from hci_common.camera_model import CameraModel
from hci_common.ros.image_msgs import bgr_to_imgmsg, camera_info_msg
from hci_common.ros.testing import Probe, RosProcess, spin_until
from hci_common.samples import sample_face
from hci_interfaces.msg import BehaviorState, DetectionArray
import numpy as np
import pytest
from rclpy.qos import qos_profile_sensor_data, ReliabilityPolicy
from sensor_msgs.msg import CameraInfo, Image

pytestmark = [pytest.mark.ros, pytest.mark.launch, pytest.mark.slow, pytest.mark.timeout(90)]


def face_frame() -> np.ndarray:
    frame = np.full((480, 640, 3), 128, np.uint8)
    frame[115:364, 95:344] = sample_face()  # 人脸在画面偏左
    return frame


@contextmanager
def system(*args: str) -> Iterator[RosProcess]:
    proc = RosProcess(['ros2', 'launch', 'hci_bringup', 'system.launch.py', 'show_window:=false',
                       'follow:=anyone', *args])
    try:
        yield proc
    finally:
        proc.stop()


class FakeRobot(Probe):
    """假机器人：订阅 /cmd_vel；需要时还发布相机画面。"""

    def __init__(self) -> None:
        super().__init__(name='fake_robot')
        self.cmds: List[TwistStamped] = self.listen(TwistStamped, '/cmd_vel')
        self.states: List[BehaviorState] = self.listen(BehaviorState, '/hci/behavior_state')
        self.detections: List[DetectionArray] = self.listen(DetectionArray, '/hci/detections')


def face_video() -> str:
    video = os.path.join(tempfile.mkdtemp(), 'face.avi')
    writer = cv2.VideoWriter(video, cv2.VideoWriter_fourcc(*'MJPG'), 15.0, (640, 480))
    for _ in range(30):
        writer.write(face_frame())
    writer.release()
    return video


def test_gazebo_with_a_video_file(ros_context):
    video = face_video()
    robot = FakeRobot()
    with system('robot:=gazebo', 'camera:=video', f'source:={video}') as proc:
        ok = spin_until([robot], lambda: len(robot.cmds) >= 5 and any(
            s.state == BehaviorState.ALIGN for s in robot.states), timeout=40.0)
        assert ok, proc.output[-3000:]
        turning = [c for c in robot.cmds if c.twist.angular.z != 0.0]
        assert turning and turning[-1].twist.angular.z > 0.0  # 人在左边：向左转
        assert robot.cmds[-1].header.frame_id == 'base_link'
        assert '/turtle1' not in proc.output  # 没有启动 turtlesim


def robot_camera(robot: FakeRobot, topic: str, qos: Any) -> Any:
    """让假机器人像相机一样每秒发布 15 帧图像和内参；返回给 spin_until 用的"发一帧"函数。"""
    camera = CameraModel.from_hfov(640, 480, 60.0)
    images = robot.talker(Image, topic, qos)
    infos = robot.talker(CameraInfo, topic.rsplit('/', 1)[0] + '/camera_info', qos)
    frame, last = face_frame(), [0.0]

    def publish() -> None:
        if time.monotonic() - last[0] > 1.0 / 15.0:
            last[0] = time.monotonic()
            msg = bgr_to_imgmsg(frame)
            msg.header.stamp = robot.get_clock().now().to_msg()
            images.publish(msg)
            infos.publish(camera_info_msg(camera, msg.header))
    return publish


def reliability(robot: FakeRobot, topic: str, node: str) -> Optional[ReliabilityPolicy]:
    """node 订阅 topic 时用的可靠性（从 ROS 图里查）。"""
    for info in robot.get_subscriptions_info_by_topic(topic):
        if info.node_name == node:
            return info.qos_profile.reliability
    return None


def test_turtlebot4_with_its_own_camera(ros_context):
    robot = FakeRobot()
    topic = '/oakd/rgb/preview/image_raw'
    publish = robot_camera(robot, topic, qos_profile_sensor_data)  # OAK-D：Best Effort

    def ready() -> bool:
        publish()
        return bool(robot.detections) and len(robot.cmds) >= 5

    with system('robot:=turtlebot4', 'camera:=robot') as proc:
        assert spin_until([robot], ready, timeout=40.0), proc.output[-3000:]
        assert robot.detections[-1].detections[0].class_name == 'face'
        assert robot.detections[-1].detections[0].bearing > 0.0  # 左正
        assert 'camera_node' not in proc.output  # 用机器人自己的相机，不启动摄像头节点
        assert reliability(robot, topic, 'recognizer_node') == ReliabilityPolicy.BEST_EFFORT


def test_gazebo_with_its_own_camera(ros_context):
    # TurtleBot 3 waffle：ros_gz 的图像桥默认用 Reliable 发布。用 Best Effort 订阅虽然也能连上，
    # 但大画面会在传输中大量丢帧（在 WSL2 上实测检测频率从约 5 Hz 降到约 1 Hz），所以要用 Reliable
    robot = FakeRobot()
    publish = robot_camera(robot, '/camera/image_raw', 10)  # rclcpp::QoS(10)：Reliable

    def ready() -> bool:
        publish()
        return bool(robot.detections) and len(robot.cmds) >= 5

    with system('robot:=gazebo', 'camera:=robot') as proc:
        assert spin_until([robot], ready, timeout=40.0), proc.output[-3000:]
        assert reliability(robot, '/camera/image_raw',
                           'recognizer_node') == ReliabilityPolicy.RELIABLE


def test_custom_cmd_vel_topic(ros_context):
    # 例如 ros_gz 的差速小车演示：速度话题是 /model/vehicle_blue/cmd_vel，类型是 Twist
    car = Probe(name='demo_car')
    cmds: List[Twist] = car.listen(Twist, '/model/vehicle_blue/cmd_vel')
    with system('robot:=gazebo', 'camera:=video', f'source:={face_video()}',
                'cmd_vel_topic:=/model/vehicle_blue/cmd_vel') as proc:
        assert spin_until([car], lambda: len(cmds) >= 5, timeout=40.0), proc.output[-3000:]
