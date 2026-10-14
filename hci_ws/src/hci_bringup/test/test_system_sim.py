"""
仿真闭环的系统测试：真正启动 turtlesim、虚拟相机、识别、行为、显示五个节点，看机器人能否独立完成任务。

  找到人 -> 转向 -> 靠近 -> 停在问候距离 -> 问候一次；只有陌生人时不动；暂停与 Ctrl+C 一定停车；
  录包不含原始图像；设置了自己的照片和模型时，还检查仿真里能不能认出"我"。

每项测试在子进程里运行 ros2 launch（与在终端里输入命令相同），用探针节点观察话题。
turtlesim 用 Qt 的 offscreen 模式运行，不需要真的弹出窗口。
"""
from contextlib import contextmanager
import importlib.util
import math
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Dict, Iterator, List, Optional

from geometry_msgs.msg import Twist
from hci_common.ros.testing import Probe, RosProcess, spin_for, spin_until
from hci_interfaces.msg import BehaviorState
import pytest
from std_msgs.msg import String
from std_srvs.srv import SetBool
from turtlesim_msgs.msg import Pose

pytestmark = [pytest.mark.ros, pytest.mark.launch, pytest.mark.slow, pytest.mark.timeout(120)]

STRANGER = (7.6, 4.7)  # hci_bringup/config/sim_world.yaml
ME = (7.6, 6.4)


@contextmanager
def system(*args: str, env: Optional[Dict[str, str]] = None) -> Iterator[RosProcess]:
    """启动整个系统（不弹出显示窗口），结束时像按 Ctrl+C 一样停止。"""
    proc = RosProcess(['ros2', 'launch', 'hci_bringup', 'system.launch.py', 'show_window:=false',
                       *args], env={'QT_QPA_PLATFORM': 'offscreen', **(env or {})})
    try:
        yield proc
    finally:
        proc.stop()


class Watcher(Probe):
    """观察者：记下机器人的位姿、行为状态、问候语和速度指令。"""

    def __init__(self) -> None:
        super().__init__(name='system_watcher')
        self.poses: List[Pose] = self.listen(Pose, '/turtle1/pose')
        self.states: List[BehaviorState] = self.listen(BehaviorState, '/hci/behavior_state')
        self.greetings: List[String] = self.listen(String, '/hci/greeting')
        self.cmds: List[Twist] = self.listen(Twist, '/turtle1/cmd_vel')

    def distance_to(self, target: Any) -> float:
        pose = self.poses[-1]
        return math.hypot(target[0] - pose.x, target[1] - pose.y)

    def state_names(self) -> List[str]:
        names = {getattr(BehaviorState, n): n
                 for n in ('STOP', 'SEARCH', 'ALIGN', 'APPROACH', 'GREET')}
        return [names[s.state] for s in self.states]

    def until(self, condition: Any, timeout: float) -> bool:
        return spin_until([self], condition, timeout=timeout)


def in_state(watcher: Watcher, state: int) -> bool:
    return bool(watcher.states) and watcher.states[-1].state == state


def test_robot_finds_approaches_and_greets_the_person(ros_context):
    watcher = Watcher()
    with system() as proc:  # 没有自己的模型：演示模式，跟随画面里的任何人脸
        assert watcher.until(lambda: in_state(watcher, BehaviorState.GREET)
                             and bool(watcher.poses), 40.0), \
            f'40 秒内没有进入 GREET：{watcher.state_names()[-20:]}\n{proc.output[-3000:]}'
        spin_for([watcher], 3.0)  # 再看 3 秒：应停稳、不再重复问候
        states = watcher.state_names()
        assert 'APPROACH' in states and states.index('APPROACH') < states.index('GREET')
        assert watcher.states[-1].state == BehaviorState.GREET
        assert [g.data for g in watcher.greetings] == ['你好！']
        assert abs(watcher.distance_to(STRANGER) - 1.0) <= 0.15  # 停在问候距离 1.0 m
        assert watcher.cmds[-1].linear.x == 0.0
        latencies = [s.latency for s in watcher.states if not math.isnan(s.latency)]
        assert latencies and max(latencies) < 1.0  # 从图像采集到下发速度不超过 1 秒


def test_never_moves_toward_a_stranger(ros_context):
    watcher = Watcher()
    with system('follow:=me'):  # 只跟随本人；YuNet 只会认出"他人"
        assert watcher.until(lambda: bool(watcher.poses) and any(
            '只看到他人' in s.reason for s in watcher.states), 30.0)
        start = watcher.poses[-1]
        spin_for([watcher], 5.0)
        end = watcher.poses[-1]
        moved = (end.x - start.x, end.y - start.y, end.theta - start.theta)
        assert moved == pytest.approx((0.0, 0.0, 0.0), abs=1e-3)  # 不前进，也不转向
        assert all(c.linear.x == 0.0 and c.angular.z == 0.0 for c in watcher.cmds)
        assert not watcher.greetings


def test_pause_and_ctrl_c_stop_the_robot(ros_context):
    watcher = Watcher()
    client = watcher.create_client(SetBool, '/hci/behavior_node/enable')

    def call(enable: bool) -> bool:
        future = client.call_async(SetBool.Request(data=enable))
        return watcher.until(future.done, 5.0) and future.result().success

    with system() as proc:
        assert watcher.until(lambda: in_state(watcher, BehaviorState.APPROACH)
                             and bool(watcher.poses), 40.0)
        assert call(False)  # 暂停（与在显示窗口里按空格键相同）
        spin_for([watcher], 0.5)
        n, pose = len(watcher.cmds), watcher.poses[-1]
        spin_for([watcher], 1.5)
        assert all(c.linear.x == 0.0 and c.angular.z == 0.0 for c in watcher.cmds[n:])
        assert watcher.distance_to((pose.x, pose.y)) < 0.01  # 暂停期间停在原地
        assert not watcher.states[-1].enabled
        assert call(True)  # 恢复：接着靠近
        assert watcher.until(lambda: bool(watcher.cmds) and watcher.cmds[-1].linear.x > 0.0, 5.0)
        assert proc.stop() == 0  # Ctrl+C：每个节点都正常退出
        spin_for([watcher], 1.0)
        assert watcher.cmds[-1].linear.x == 0.0 and watcher.cmds[-1].angular.z == 0.0


def readme_topics() -> List[Any]:
    """README 第 9 节话题表里的 (名字, 类型)。"""
    text = (Path(__file__).resolve().parents[4] / 'README.md').read_text(encoding='utf-8')
    rows = re.findall(r'^\| `(/[^`]+)` \| (?:服务 )?`([^`]+)`', text, re.MULTILINE)
    return rows


def test_running_system_matches_the_readme_topic_table(ros_context):
    """README 的话题表与真正运行的系统一致：表里的都在，系统里 /hci、/camera 下的也都在表里。"""
    documented = dict(readme_topics())
    optional = {'/camera/image_raw/compressed'}  # 只有 publish_compressed 为 true 时才有
    watcher = Watcher()
    with system():
        names: Dict[str, List[str]] = {}

        def ready() -> bool:
            names.clear()
            names.update(watcher.get_topic_names_and_types())
            names.update(watcher.get_service_names_and_types())
            return all(t in names for t in documented if t not in optional)
        assert watcher.until(ready, 30.0), f'系统里缺少：{set(documented) - set(names)}'
    for topic, msg_type in documented.items():
        if topic in names:
            assert msg_type in names[topic], f'{topic}：系统里是 {names[topic]}，README 是 {msg_type}'
    builtin = ('/describe_parameters', '/get_parameter_types', '/get_parameters',  # 每个节点都有
               '/list_parameters', '/set_parameters', '/set_parameters_atomically',
               '/get_type_description')
    hidden = [t for t in names if any(part.startswith('_') for part in t.split('/'))]  # 隐藏话题
    ours = [t for t in names if t.startswith(('/hci/', '/camera/')) and not t.endswith(builtin)
            and t not in hidden]
    undocumented = [t for t in ours if t not in documented]
    assert not undocumented, f'README 的话题表里没有：{undocumented}'


@pytest.mark.skipif(importlib.util.find_spec('ros2bag') is None,
                    reason='没有安装 rosbag2：sudo apt install ros-lyrical-rosbag2')
def test_record_writes_a_bag_without_raw_images(ros_context, tmp_path):
    watcher = Watcher()
    with system('record:=true', env={'HOME': str(tmp_path)}) as proc:
        assert watcher.until(lambda: in_state(watcher, BehaviorState.APPROACH), 40.0)
        spin_for([watcher], 2.0)
        assert proc.stop() == 0
    (bag,) = (tmp_path / 'hci_bags').iterdir()
    info = subprocess.run(['ros2', 'bag', 'info', str(bag)], capture_output=True, text=True,
                          check=True).stdout
    for topic in ('/hci/detections', '/hci/behavior_state', '/turtle1/cmd_vel', '/turtle1/pose'):
        assert topic in info
    assert 'image_raw' not in info  # 人脸属于个人信息：不录原始图像


ME_PHOTO, ME_MODEL = os.environ.get('HCI_ME_PHOTO', ''), os.environ.get('HCI_ME_MODEL', '')


@pytest.mark.skipif(not (ME_PHOTO and ME_MODEL),
                    reason='用自己的照片和模型测试时设置 HCI_ME_PHOTO 与 HCI_ME_MODEL（只在本机读取）')
def test_recognizes_me_in_simulation(ros_context):
    for path in (ME_PHOTO, ME_MODEL):
        assert Path(path).is_file(), f'找不到 {path}（请使用绝对路径）'
    watcher = Watcher()
    args = [f'me_image:={ME_PHOTO}', f'model:={ME_MODEL}']
    if os.environ.get('HCI_ME_ID_MAP'):
        args.append(f'id_map:={os.environ["HCI_ME_ID_MAP"]}')
    with system(*args) as proc:
        assert watcher.until(lambda: in_state(watcher, BehaviorState.GREET)
                             and bool(watcher.poses), 60.0), \
            f'60 秒内没有走到"我"面前：{watcher.state_names()[-20:]}\n{proc.output[-3000:]}'
        spin_for([watcher], 2.0)
        assert watcher.distance_to(ME) < watcher.distance_to(STRANGER)  # 走向的是"我"
        assert abs(watcher.distance_to(ME) - 1.0) <= 0.25  # 真人照片的脸大小因人而异，放宽一些
        assert len(watcher.greetings) == 1 and watcher.greetings[0].data.startswith('你好，')
