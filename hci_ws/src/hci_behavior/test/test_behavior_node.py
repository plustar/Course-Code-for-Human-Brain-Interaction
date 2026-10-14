"""
behavior_node 的节点测试。

自动识别 Twist 与 TwistStamped；BehaviorState 与问候；~/enable 暂停期间持续发零速度；
看门狗；退出前停车；没有机器人订阅时提醒。
"""
import time
from types import SimpleNamespace
from typing import Any, Callable, List

from geometry_msgs.msg import Twist, TwistStamped
from hci_behavior.ros.behavior_node import BehaviorNode
from hci_behavior.state_machine import State
from hci_common.ros.testing import LogSpy, Probe, spin_for, spin_until
from hci_interfaces.msg import BehaviorState, Detection, DetectionArray
import pytest
from rclpy.parameter import Parameter
from std_msgs.msg import String
from std_srvs.srv import SetBool

pytestmark = pytest.mark.ros


def make_node(namespace: str, **params: Any) -> BehaviorNode:
    return BehaviorNode(namespace=namespace,
                        parameter_overrides=[Parameter(k, value=v) for k, v in params.items()])


class Person:
    """替识别节点按 15 Hz 发布检测结果：一个人站在 bearing（弧度）、distance（米）处。"""

    def __init__(self, probe: Probe, node: BehaviorNode, bearing: float = 0.0,
                 distance: float = 3.0, class_name: str = 'stu_2023123456') -> None:
        self.pub = probe.talker(DetectionArray, 'detections')
        self.node, self.last = node, 0.0
        self.bearing, self.distance, self.class_name = bearing, distance, class_name
        self.visible = True

    def __call__(self) -> None:
        if time.monotonic() - self.last < 1.0 / 15.0:
            return
        self.last = time.monotonic()
        msg = DetectionArray(image_width=640, image_height=480)
        msg.header.stamp = self.node.get_clock().now().to_msg()
        if self.visible:
            msg.detections = [Detection(class_name=self.class_name, display_name='张三 2023123456',
                                        confidence=0.9, bearing=self.bearing,
                                        distance=self.distance)]
        self.pub.publish(msg)


def run_until(node: BehaviorNode, probe: Probe, person: Person, condition: Callable[[], bool],
              timeout: float = 5.0) -> bool:
    """一边发布检测结果，一边等待条件成立。"""
    def check() -> bool:
        person()
        return condition()
    return spin_until([node, probe], check, timeout=timeout)


@pytest.mark.parametrize('msg_type', [Twist, TwistStamped])
def test_auto_follows_the_type_the_robot_subscribes(ros_context, namespace, msg_type):
    node, probe = make_node(namespace), Probe(namespace)
    received = probe.listen(msg_type, 'cmd_vel')
    assert spin_until([node, probe], lambda: len(received) >= 2)
    assert node.cmd_type is msg_type
    if msg_type is TwistStamped:
        assert received[-1].header.frame_id == 'base_link'


@pytest.mark.parametrize('cmd_vel_type, msg_type', [('twist', Twist), ('stamped', TwistStamped)])
def test_explicit_type_needs_no_subscriber(ros_context, namespace, cmd_vel_type, msg_type):
    node = make_node(namespace, cmd_vel_type=cmd_vel_type)
    spin_for([node], 0.25)
    assert node.cmd_type is msg_type


def test_invalid_type_is_rejected(ros_context, namespace):
    with pytest.raises(ValueError, match='cmd_vel_type'):
        make_node(namespace, cmd_vel_type='twist_stamped')


@pytest.mark.parametrize('params, hint', [({'control_rate': 0.0}, 'control_rate 必须大于 0'),
                                          ({'min_distance': 1.5}, 'min_distance')])
def test_bad_parameters_are_explained_at_start(ros_context, namespace, params, hint):
    with pytest.raises(ValueError, match=hint):
        make_node(namespace, **params)


def test_warns_when_no_robot_subscribes(ros_context, namespace):
    node = make_node(namespace)
    spy = LogSpy.attach(node)
    node.t_start -= 10.0  # 假装已经等了 10 秒
    assert node.ensure_publisher() is None
    assert '机器人或仿真启动了吗' in spy.text('warning')


def test_warns_when_types_are_ambiguous(ros_context, namespace, monkeypatch):
    # 同一个进程里不能用两种类型订阅同一个话题，所以这里直接替换"谁在订阅"的查询结果
    node = make_node(namespace)
    found = [SimpleNamespace(topic_type='geometry_msgs/msg/Twist'),
             SimpleNamespace(topic_type='geometry_msgs/msg/TwistStamped')]
    monkeypatch.setattr(node, 'get_subscriptions_info_by_topic', lambda topic: found)
    spy = LogSpy.attach(node)
    node.t_start -= 10.0
    assert node.ensure_publisher() is None and '请用 cmd_vel_type 指定' in spy.text('warning')


def test_publishes_behavior_state_every_cycle(ros_context, namespace):
    node, probe = make_node(namespace, cmd_vel_type='twist'), Probe(namespace)
    states = probe.listen(BehaviorState, 'behavior_state')
    cmds = probe.listen(Twist, 'cmd_vel')
    person = Person(probe, node, bearing=0.02, distance=3.0)
    assert run_until(node, probe, person, lambda: bool(states and cmds) and cmds[-1].linear.x > 0.0
                     and states[-1].state == BehaviorState.APPROACH)
    last = states[-1]
    assert last.enabled and last.target_name == '张三 2023123456'
    assert last.target_distance == pytest.approx(3.0) and last.linear == pytest.approx(0.2)
    assert 0.0 <= last.latency < 0.5  # 从图像采集到下发速度
    assert cmds and cmds[-1].linear.x == pytest.approx(0.2)


def test_greets_once_when_close(ros_context, namespace):
    node, probe = make_node(namespace, cmd_vel_type='twist'), Probe(namespace)
    greetings: List[String] = probe.listen(String, 'greeting')
    states = probe.listen(BehaviorState, 'behavior_state')
    person = Person(probe, node, distance=0.9)
    assert run_until(node, probe, person, lambda: len(states) >= 10 and bool(greetings))
    run_until(node, probe, person, lambda: False, timeout=0.5)
    assert [g.data for g in greetings] == ['你好，张三 2023123456！']
    assert states[-1].state == BehaviorState.GREET and states[-1].linear == 0.0


def test_short_watchdog_stop_does_not_greet_again(ros_context, namespace):
    node, probe = make_node(namespace, cmd_vel_type='twist'), Probe(namespace)
    greetings = probe.listen(String, 'greeting')
    states = probe.listen(BehaviorState, 'behavior_state')
    person = Person(probe, node, distance=0.9)
    assert run_until(node, probe, person, lambda: bool(greetings))
    assert spin_until([node, probe], lambda: '看门狗' in states[-1].reason, timeout=2.0)  # 卡了一下
    assert run_until(node, probe, person, lambda: states[-1].state == BehaviorState.GREET)
    run_until(node, probe, person, lambda: False, timeout=0.5)
    assert len(greetings) == 1  # 人还在原地：不再问候第二遍


def test_greeting_while_paused_is_given_after_resuming(ros_context, namespace):
    # 暂停期间人走到了问候距离：状态机已经进入 GREET，恢复后要问候一次，而不是一直不问候
    node, probe = make_node(namespace, cmd_vel_type='twist'), Probe(namespace)
    greetings = probe.listen(String, 'greeting')
    node.enabled = False  # 等同于在显示窗口按了空格键
    person = Person(probe, node, distance=0.9)
    assert run_until(node, probe, person, lambda: node.machine.state == State.GREET)
    run_until(node, probe, person, lambda: False, timeout=0.3)
    assert not greetings  # 暂停期间不问候
    node.enabled = True
    assert run_until(node, probe, person, lambda: bool(greetings))
    run_until(node, probe, person, lambda: False, timeout=0.5)
    assert [g.data for g in greetings] == ['你好，张三 2023123456！']


def test_enable_service_pauses_with_zero_velocity_and_resumes(ros_context, namespace):
    node, probe = make_node(namespace, cmd_vel_type='twist'), Probe(namespace)
    cmds, states = probe.listen(Twist, 'cmd_vel'), probe.listen(BehaviorState, 'behavior_state')
    client = probe.create_client(SetBool, 'behavior_node/enable')
    person = Person(probe, node, distance=3.0)
    assert run_until(node, probe, person, lambda: bool(cmds) and cmds[-1].linear.x > 0.0)

    def call(enable: bool) -> SetBool.Response:
        future = client.call_async(SetBool.Request(data=enable))
        assert run_until(node, probe, person, future.done)
        return future.result()

    assert call(False).success
    cmds.clear()
    run_until(node, probe, person, lambda: False, timeout=1.0)
    assert len(cmds) >= 5 and all(c.linear.x == 0.0 and c.angular.z == 0.0 for c in cmds)
    assert states[-1].state == BehaviorState.STOP and not states[-1].enabled
    assert call(True).success
    assert run_until(node, probe, person, lambda: cmds[-1].linear.x > 0.0)


def test_watchdog_stops_when_detections_stop(ros_context, namespace):
    node, probe = make_node(namespace, cmd_vel_type='twist'), Probe(namespace)
    cmds, states = probe.listen(Twist, 'cmd_vel'), probe.listen(BehaviorState, 'behavior_state')
    person = Person(probe, node, distance=3.0)
    assert run_until(node, probe, person, lambda: bool(cmds) and cmds[-1].linear.x > 0.0)
    assert spin_until([node, probe], lambda: '看门狗' in states[-1].reason, timeout=2.0)
    assert cmds[-1].linear.x == 0.0 and cmds[-1].angular.z == 0.0


def test_warns_when_the_stop_command_cannot_be_sent(ros_context, namespace, monkeypatch, capsys):
    node = make_node(namespace, cmd_vel_type='twist')
    spin_for([node], 0.25)  # 控制周期里已经建好速度的发布者

    def broken(linear: float, angular: float) -> None:
        raise RuntimeError('通信已经关闭')

    monkeypatch.setattr(node, 'send', broken)
    node.destroy_node()
    assert '停车指令可能没有发出去' in capsys.readouterr().err


def test_sends_zero_velocity_before_exit(ros_context, namespace):
    node, probe = make_node(namespace, cmd_vel_type='twist'), Probe(namespace)
    cmds = probe.listen(Twist, 'cmd_vel')
    person = Person(probe, node, distance=3.0)
    assert run_until(node, probe, person, lambda: bool(cmds) and cmds[-1].linear.x > 0.0)
    node.destroy_node()
    assert spin_until([probe], lambda: cmds[-1].linear.x == 0.0, timeout=2.0)
