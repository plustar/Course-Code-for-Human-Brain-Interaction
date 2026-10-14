"""
behavior_node：根据检测结果控制机器人——估计 -> 决策 -> 安全 -> 下发速度。

订阅  detections      hci_interfaces/DetectionArray
发布  cmd_vel         Twist 或 TwistStamped（launch 把它重映射到机器人的速度话题）
      behavior_state  hci_interfaces/BehaviorState：状态、原因、目标、速度、延迟，每个控制周期一条
      greeting        std_msgs/String：刚进入 GREET 时发布一次问候语
服务  ~/enable        std_srvs/SetBool：false 暂停（暂停期间持续发零速度），true 恢复
退出（Ctrl+C 或 kill）前一定先发零速度：Gazebo 里的小车不会自己停。

换平台只改参数（见 hci_bringup/config/robots）：
  turtlesim       cmd_vel -> /turtle1/cmd_vel   Twist
  TurtleBot 3     cmd_vel -> /cmd_vel           TwistStamped（Lyrical 的 Gazebo 仿真）
  ros_gz 演示小车  cmd_vel -> /model/vehicle_blue/cmd_vel   Twist
  TurtleBot 4     cmd_vel -> /cmd_vel           TwistStamped（Jazzy 真机，只作案例）
  不确定时用 cmd_vel_type: auto：等机器人订阅了速度话题后，按它的类型发布。
"""
from dataclasses import dataclass
import math
import sys
import time
from typing import Any, Dict, List, Optional, Type, Union

from geometry_msgs.msg import Twist, TwistStamped
from hci_behavior.config import BehaviorConfig
from hci_behavior.estimator import Observation, Target, TargetEstimator
from hci_behavior.safety import SafetyFilter
from hci_behavior.state_machine import Command, State, StateMachine
from hci_common.params import param, require_positive
from hci_common.ros.params import declare_params
from hci_common.ros.runner import run
from hci_interfaces.msg import BehaviorState, DetectionArray
from rclpy.node import Node
from rclpy.publisher import Publisher
from rclpy.time import Time
from std_msgs.msg import String
from std_srvs.srv import SetBool

CmdType = Union[Type[Twist], Type[TwistStamped]]
CMD_TYPES: Dict[str, CmdType] = {'geometry_msgs/msg/Twist': Twist,
                                 'geometry_msgs/msg/TwistStamped': TwistStamped}


@dataclass
class Params(BehaviorConfig):
    """behavior_node 的参数：行为参数（见 config.py）加上与 ROS 接线有关的几项。"""

    cmd_vel_type: str = param('auto', '速度消息类型：auto（按机器人订阅的类型）、twist 或 stamped')
    frame_id: str = param('base_link', 'TwistStamped 消息的坐标系名')
    control_rate: float = param(10.0, '控制频率（Hz）')
    greeting_template: str = param('你好，{name}！', '问候语模板，{name} 会换成对方的显示名')


def observations_from_msg(msg: DetectionArray) -> List[Observation]:
    """DetectionArray 消息 -> 行为关心的观测列表。"""
    return [Observation(d.class_name, d.display_name, d.confidence, d.bearing, d.distance)
            for d in msg.detections]


class BehaviorNode(Node):
    """行为节点：估计目标、状态机决策、安全检查，然后发布速度与状态。"""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__('behavior_node', **kwargs)
        self.p = declare_params(self, Params)
        require_positive(self.p, 'control_rate')
        if self.p.cmd_vel_type not in ('auto', 'twist', 'stamped'):
            raise ValueError(f'cmd_vel_type 只能是 auto、twist 或 stamped，收到 {self.p.cmd_vel_type}')
        self.estimator = TargetEstimator(self.p)
        self.machine = StateMachine(self.p)
        self.safety = SafetyFilter(self.p)
        self.enabled = True
        self.greet_pending = False  # 进入 GREET 时正暂停（或看门狗停车）：恢复后再问候
        self.last_state: Optional[State] = None
        self.cmd_pub: Optional[Publisher] = None
        self.cmd_type: Optional[CmdType] = None
        self.t_start = time.monotonic()
        self.warned_no_robot = False

        self.create_subscription(DetectionArray, 'detections', self.on_detections, 10)
        self.state_pub = self.create_publisher(BehaviorState, 'behavior_state', 10)
        self.greeting_pub = self.create_publisher(String, 'greeting', 10)
        self.create_service(SetBool, '~/enable', self.on_enable)
        self.create_timer(1.0 / self.p.control_rate, self.on_control)
        self.get_logger().info(
            f'限速 {self.p.max_speed} m/s、{self.p.max_turn_rate} rad/s；问候距离 '
            f'{self.p.greet_distance} m；看门狗 {self.p.watchdog_timeout} s；速度类型 '
            f'{self.p.cmd_vel_type}')

    def now(self) -> float:
        return self.get_clock().now().nanoseconds * 1e-9

    # ---------- 输入 ----------
    def on_detections(self, msg: DetectionArray) -> None:
        stamp = Time.from_msg(msg.header.stamp).nanoseconds * 1e-9
        self.estimator.update(observations_from_msg(msg), self.now(), stamp)

    def on_enable(self, request: SetBool.Request,
                  response: SetBool.Response) -> SetBool.Response:
        """~/enable 服务：false 暂停，true 恢复。"""
        self.enabled = bool(request.data)
        response.success = True
        response.message = '已恢复' if self.enabled else '已暂停：持续发送零速度'
        self.get_logger().info(response.message)
        return response

    # ---------- 控制周期：估计 -> 决策 -> 安全 -> 输出 ----------
    def on_control(self) -> None:
        now = self.now()
        target = self.estimator.target()
        cmd = self.machine.step(target, self.estimator.others_seen)
        distance = target.distance if target else math.nan
        # 安全层只改输出、不改状态机：看门狗短暂超时后人还在原地时，不会重新问候一遍
        safe = self.safety.check(cmd, self.estimator.age(now), self.enabled, distance)
        self.send(safe.linear, safe.angular)
        self.publish_state(safe, target, now)
        if safe.state != self.last_state:
            self.get_logger().info(f'状态 -> {safe.state.name}（{safe.reason}）')
            self.last_state = safe.state
        # 问候只在刚进入 GREET 时发一次。那一刻安全层正让机器人停着（暂停、看门狗）时先记下，
        # 恢复后人还在问候距离内再问候；人在这期间走开了就不问候
        self.greet_pending = (self.greet_pending or cmd.greet) and cmd.state == State.GREET
        if self.greet_pending and safe.state == State.GREET and target is not None:
            self.greet_pending = False
            text = self.p.greeting_template.format(name=target.name)
            self.greeting_pub.publish(String(data=text))
            self.get_logger().info(text)

    def publish_state(self, cmd: Command, target: Optional[Target], now: float) -> None:
        msg = BehaviorState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.state, msg.reason, msg.enabled = int(cmd.state), cmd.reason, self.enabled
        msg.linear, msg.angular = float(cmd.linear), float(cmd.angular)
        msg.target_name = target.name if target else ''
        msg.target_bearing = float(target.bearing) if target else math.nan
        msg.target_distance = float(target.distance) if target else math.nan
        msg.latency = float(now - target.stamp) if target else math.nan
        self.state_pub.publish(msg)

    # ---------- 速度输出：按参数或按机器人实际订阅的类型创建发布者 ----------
    def ensure_publisher(self) -> Optional[Publisher]:
        """返回速度指令的发布者；cmd_vel_type: auto 而机器人还没有订阅速度话题时返回 None。"""
        if self.cmd_pub is not None:
            return self.cmd_pub
        if self.p.cmd_vel_type == 'twist':
            msg_type: CmdType = Twist
        elif self.p.cmd_vel_type == 'stamped':
            msg_type = TwistStamped
        else:
            topic = self.resolve_topic_name('cmd_vel')
            found = {i.topic_type for i in self.get_subscriptions_info_by_topic(topic)}
            found &= set(CMD_TYPES)
            if len(found) != 1:
                if time.monotonic() - self.t_start > 3.0 and not self.warned_no_robot:
                    self.warned_no_robot = True
                    self.get_logger().warning(
                        f'还没有节点订阅 {topic}：机器人或仿真启动了吗？话题名对吗？' if not found
                        else f'{topic} 上同时存在 {sorted(found)}，请用 cmd_vel_type 指定')
                return None
            msg_type = CMD_TYPES[found.pop()]
        self.cmd_type = msg_type
        self.cmd_pub = self.create_publisher(msg_type, 'cmd_vel', 10)
        self.get_logger().info(f'速度指令 -> {self.cmd_pub.topic_name}（{msg_type.__name__}）')
        return self.cmd_pub

    def send(self, linear: float, angular: float) -> None:
        pub = self.ensure_publisher()
        if pub is None:
            return
        twist = Twist()
        twist.linear.x, twist.angular.z = float(linear), float(angular)
        if self.cmd_type is TwistStamped:
            msg = TwistStamped()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = self.p.frame_id
            msg.twist = twist
            pub.publish(msg)
        else:
            pub.publish(twist)

    def destroy_node(self) -> None:
        """退出前一定先停车（Gazebo 里的小车不会自己停）。构造中途失败时还没有发布者，跳过。"""
        if getattr(self, 'cmd_pub', None) is not None:
            try:
                for _ in range(3):
                    self.send(0.0, 0.0)
                    time.sleep(0.05)
                self.get_logger().info('已发送停车指令')
            except Exception as e:  # 通信或日志可能已经关闭：直接打印，不让真正的退出原因被盖住
                print(f'[behavior_node] 停车指令可能没有发出去（{e}），请确认机器人已经停下',
                      file=sys.stderr)
        super().destroy_node()


def main() -> None:
    run(BehaviorNode)


if __name__ == '__main__':
    main()
