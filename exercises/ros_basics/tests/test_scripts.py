"""
练习 2 的脚本：在子进程里像在终端里一样运行，检查输出和效果。

turtlesim 用 Qt 的 offscreen 模式运行，不弹出窗口；只有 cam_view 的测试真的要开窗口（--gui）。
"""
from contextlib import contextmanager
import importlib.util
import math
from pathlib import Path
import sys
import tempfile
import time
from types import ModuleType
from typing import Dict, Iterator

import cv2
from geometry_msgs.msg import Twist
from hci_common.ros.testing import needs_gui, Probe, RosProcess, spin_for, spin_until
import numpy as np
import pytest
from rclpy.action import ActionServer, GoalResponse
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from turtlesim_msgs.action import RotateAbsolute
from turtlesim_msgs.msg import Pose

pytestmark = [pytest.mark.ros, pytest.mark.launch]
EX2 = Path(__file__).resolve().parents[1]


def script(name: str, *args: str) -> RosProcess:
    """像在终端里输入 python3 <脚本> 一样运行。"""
    return RosProcess([sys.executable, str(EX2 / name), *args])


# 用 rclpy 默认 Ctrl+C 处理的官方模板，偶尔撞上 rclpy 自身的时序问题：Ctrl+C 恰好落在执行器建立
# 等待集的瞬间，rclpy 抛出 RCLError，进程以 1 退出（README 有说明）。只放过这一种，其他错误照样失败
RCLPY_SHUTDOWN_RACE = 'rcl_shutdown() was called'


def stopped_by_ctrl_c(*procs: RosProcess) -> bool:
    """像按 Ctrl+C 一样停止每个进程（先全部停掉，不留后台进程），都正常退出时返回 True。"""
    codes = [proc.stop() for proc in procs]
    return all(code == 0 or (code == 1 and RCLPY_SHUTDOWN_RACE in proc.output)
               for code, proc in zip(codes, procs))


@contextmanager
def turtlesim() -> Iterator[RosProcess]:
    proc = RosProcess(['ros2', 'run', 'turtlesim', 'turtlesim_node'],
                      env={'QT_QPA_PLATFORM': 'offscreen'})
    try:
        yield proc
    finally:
        proc.stop()


def video(fps: float = 10.0, n: int = 30) -> str:
    """一段小视频，给 cam_pub.py 当图像来源。"""
    path = str(Path(tempfile.mkdtemp()) / 'clip.avi')
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'MJPG'), fps, (160, 120))
    for i in range(n):
        writer.write(np.full((120, 160, 3), 8 * i, np.uint8))
    writer.release()
    return path


def test_talker_and_listener(ros_domain):
    talker, listener = script('talker.py'), script('listener.py')
    try:
        assert listener.wait_for_output('收到：你好，ROS 2！', timeout=20), listener.output
        assert '发布：你好，ROS 2！第 0 条' in talker.output
    finally:
        assert stopped_by_ctrl_c(talker, listener), talker.output + listener.output


def test_turtle_circle_draws_a_circle_and_stops_on_ctrl_c(ros_context):
    watcher = Probe(name='watcher')
    poses, cmds = watcher.listen(Pose, '/turtle1/pose'), watcher.listen(Twist, '/turtle1/cmd_vel')
    with turtlesim():
        circle = script('turtle_circle.py', '--v', '2.0', '--w', '1.0')
        # 也等探针收到速度指令：探针发现脚本需要时间，发现之前按 Ctrl+C，最后那条零速度它就收不到
        assert spin_until([watcher], lambda: bool(cmds) and bool(poses)
                          and poses[-1].angular_velocity == 1.0
                          and poses[-1].linear_velocity == 2.0, timeout=20)
        assert '理论半径 2.00' in circle.output
        assert circle.stop() == 0
        spin_for([watcher], 0.5)
        assert (cmds[-1].linear.x, cmds[-1].angular.z) == (0.0, 0.0)  # 退出前发了零速度
        assert spin_until([watcher], lambda: poses[-1].linear_velocity == 0.0, timeout=3)


def test_turtle_spawn_calls_the_service(ros_context):
    watcher = Probe(name='watcher')
    poses = watcher.listen(Pose, '/buddy/pose')
    with turtlesim():
        spawn = script('turtle_spawn.py', '--x', '2', '--y', '8', '--name', 'buddy')
        assert spawn.proc.wait(timeout=30) == 0, spawn.output
        spawn.stop()
        assert '已放下海龟 buddy' in spawn.output
        assert spin_until([watcher], lambda: bool(poses), timeout=10)
        assert (poses[-1].x, poses[-1].y) == pytest.approx((2.0, 8.0), abs=0.01)


def test_turtle_circle_with_zero_turn_rate_drives_straight(ros_domain):
    circle = script('turtle_circle.py', '--v', '1.0', '--w', '0')  # 半径 v/ω：ω 为 0 时不能除
    try:
        assert circle.wait_for_output('无穷大', timeout=20), circle.output
    finally:
        assert stopped_by_ctrl_c(circle), circle.output


def test_turtle_spawn_explains_a_taken_name(ros_domain):
    # turtlesim 不能放下海龟时也会应答，只是名字为空：脚本要说明原因，而不是报告成功
    with turtlesim():
        first = script('turtle_spawn.py', '--name', 'buddy')
        assert first.proc.wait(timeout=30) == 0, first.output
        first.stop()
        again = script('turtle_spawn.py', '--name', 'buddy')
        assert again.proc.wait(timeout=30) == 1, again.output
        again.stop()
        assert '已经被占用' in again.output and '已放下' not in again.output


def test_turtle_spawn_without_turtlesim_explains(ros_domain):
    spawn = script('turtle_spawn.py')
    assert spawn.proc.wait(timeout=30) == 1
    spawn.stop()
    assert 'turtlesim_node 启动了吗' in spawn.output


def test_turtle_rotate_explains_a_rejected_goal(ros_context):
    fake = Probe(name='fake_turtlesim')  # 只提供动作、并且拒绝所有目标的"turtlesim"
    server = ActionServer(fake, RotateAbsolute, '/turtle1/rotate_absolute',
                          execute_callback=lambda goal: RotateAbsolute.Result(),
                          goal_callback=lambda request: GoalResponse.REJECT)
    rotate = script('turtle_rotate.py', '--theta', '90')
    try:
        assert spin_until([fake], lambda: rotate.proc.poll() is not None, timeout=30)
    finally:
        rotate.stop()
        server.destroy()
    assert rotate.proc.returncode == 1 and '目标被拒绝' in rotate.output, rotate.output


def test_turtle_rotate_uses_the_action(ros_context):
    watcher = Probe(name='watcher')
    poses = watcher.listen(Pose, '/turtle1/pose')
    with turtlesim():
        rotate = script('turtle_rotate.py', '--theta', '90')
        assert rotate.proc.wait(timeout=40) == 0, rotate.output
        rotate.stop()
        assert '反馈：还差' in rotate.output and '结果：转过了' in rotate.output
        assert spin_until([watcher], lambda: bool(poses), timeout=10)
        assert poses[-1].theta == pytest.approx(math.pi / 2, abs=0.05)


def load(name: str) -> ModuleType:
    """在测试进程里导入练习 2 的一个脚本（不运行它的 main）。"""
    spec = importlib.util.spec_from_file_location(name, EX2 / f'{name}.py')
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cam_pub_opens_cameras_like_the_camera_node(monkeypatch):
    # 与 camera_node 相同的 MJPG、640×480：默认的 YUYV 经 WSL2 的 usbipd 转发时，画面下半部分是绿的
    props: Dict[int, float] = {}

    class FakeCapture:
        """记下 set() 调用的假摄像头。"""

        def __init__(self, index: int) -> None:
            self.index = index

        def set(self, prop: int, value: float) -> bool:  # noqa: A003  与 cv2 的方法同名
            props[prop] = value
            return True

        def isOpened(self) -> bool:
            return True

    monkeypatch.setattr(cv2, 'VideoCapture', FakeCapture)
    load('cam_pub').open_source('0')
    assert props[cv2.CAP_PROP_FOURCC] == cv2.VideoWriter_fourcc(*'MJPG')
    assert (props[cv2.CAP_PROP_FRAME_WIDTH], props[cv2.CAP_PROP_FRAME_HEIGHT]) == (640, 480)


def test_cam_pub_explains_a_camera_that_cannot_open():
    with pytest.raises(RuntimeError, match='usbipd'):
        load('cam_pub').open_source('99')  # 不存在的 /dev/video99


def test_cam_pub_publishes_at_the_video_frame_rate(ros_context):
    watcher = Probe(name='watcher')
    images = watcher.listen(Image, '/camera/image_raw', qos_profile_sensor_data)
    pub = script('cam_pub.py', '--source', video(fps=10.0))
    try:
        assert spin_until([watcher], lambda: len(images) >= 15, timeout=20), pub.output
    finally:
        assert stopped_by_ctrl_c(pub), pub.output
    stamps = [m.header.stamp.sec + m.header.stamp.nanosec * 1e-9 for m in images]
    assert (len(stamps) - 1) / (stamps[-1] - stamps[0]) == pytest.approx(10.0, rel=0.2)
    assert (images[-1].width, images[-1].height, images[-1].encoding) == (160, 120, 'bgr8')


@pytest.mark.gui
@needs_gui
@pytest.mark.parametrize('qos', [[], ['--reliable']], ids=['best_effort', 'reliable'])
def test_cam_view_shows_the_stream(ros_domain, qos):
    pub = script('cam_pub.py', '--source', video())
    view = script('cam_view.py', *qos)
    try:
        assert view.wait_for_output('图像订阅的 QoS', timeout=20), view.output
        time.sleep(3.0)
        assert view.proc.poll() is None, view.output  # 窗口一直开着，没有崩溃
    finally:
        assert stopped_by_ctrl_c(view, pub), view.output + pub.output
