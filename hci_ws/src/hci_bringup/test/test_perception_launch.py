"""
感知管线的系统测试，用 ROS 官方的 launch_testing 写法（第 8 讲"集成测试"可以对照这个文件）。

视频文件 -> camera_node -> recognizer_node（YuNet）-> viewer_node：三个节点都跑起来，
检测结果在 1 秒内送达（端到端延迟），测试结束停止时每个进程都正常退出（退出码 0）。

写法要点：generate_test_description() 返回要启动的系统和 ReadyToTest；普通的 unittest 类
在系统运行期间执行；带 @post_shutdown_test 的类在系统关闭之后检查退出码。
"""
import os
import tempfile
import time
from typing import Set
import unittest

from ament_index_python.packages import get_package_share_directory
import cv2
from hci_common.ros.testing import isolate_ros_domain
from hci_common.samples import sample_face
from hci_interfaces.msg import DetectionArray
import launch
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
import launch_testing
import launch_testing.actions
import launch_testing.asserts
import numpy as np
import pytest
import rclpy
from rclpy.time import Time


def make_video(path: str) -> None:
    """一段 3 秒、15 帧/秒的视频：灰色背景正中一张公有领域人脸。"""
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'MJPG'), 15.0, (640, 480))
    frame = np.full((480, 640, 3), 128, np.uint8)
    frame[115:364, 195:444] = sample_face()
    for _ in range(45):
        writer.write(frame)
    writer.release()


@pytest.mark.launch_test
@pytest.mark.launch
@pytest.mark.ros
def generate_test_description() -> launch.LaunchDescription:
    isolate_ros_domain()  # 独占一个 ROS_DOMAIN_ID：启动的节点继承它
    video = os.path.join(tempfile.mkdtemp(), 'face.avi')
    make_video(video)
    share = get_package_share_directory('hci_bringup')
    perception = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(share, 'launch', 'perception.launch.py')),
        launch_arguments={'camera': 'video', 'source': video, 'show_window': 'false'}.items())
    return launch.LaunchDescription([perception, launch_testing.actions.ReadyToTest()])


class TestPerceptionPipeline(unittest.TestCase):
    """系统运行期间执行。"""

    @classmethod
    def setUpClass(cls) -> None:
        rclpy.init()

    @classmethod
    def tearDownClass(cls) -> None:
        rclpy.shutdown()

    def setUp(self) -> None:
        self.node = rclpy.create_node('pipeline_probe')

    def tearDown(self) -> None:
        self.node.destroy_node()

    def test_faces_are_detected_within_one_second(self) -> None:
        received = []  # (检测结果, 收到的时刻)
        self.node.create_subscription(
            DetectionArray, '/hci/detections',
            lambda msg: received.append((msg, self.node.get_clock().now())), 10)
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline and len(received) < 15:
            rclpy.spin_once(self.node, timeout_sec=0.1)
        self.assertGreaterEqual(len(received), 15, '30 秒内没有收到足够的检测结果')
        msg, _ = received[-1]
        self.assertEqual([d.class_name for d in msg.detections], ['face'])
        self.assertEqual(msg.detections[0].display_name, '他人')
        self.assertAlmostEqual(msg.detections[0].bearing, 0.0, delta=0.05)  # 人脸在画面正中
        latencies = [(now - Time.from_msg(m.header.stamp)).nanoseconds * 1e-9
                     for m, now in received[5:]]
        self.assertLess(max(latencies), 1.0, f'端到端延迟过大：{max(latencies):.2f} 秒')

    def test_all_three_nodes_are_running(self, proc_output: launch_testing.ActiveIoHandler
                                         ) -> None:
        proc_output.assertWaitFor('识别后端：yunet', timeout=20)
        names: Set[str] = set()
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and len(names) < 3:
            names = {ns + '/' + n for n, ns in self.node.get_node_names_and_namespaces()}
            names &= {'/camera/camera_node', '/hci/recognizer_node', '/hci/viewer_node'}
            rclpy.spin_once(self.node, timeout_sec=0.2)
        self.assertEqual(len(names), 3, f'只找到 {names}')


@launch_testing.post_shutdown_test()
class TestShutdown(unittest.TestCase):
    """系统关闭之后执行：每个节点都应正常退出。"""

    def test_exit_codes(self, proc_info: launch_testing.ProcInfoHandler) -> None:
        launch_testing.asserts.assertExitCodes(proc_info)
