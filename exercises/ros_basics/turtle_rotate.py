"""
练习 2-⑤：动作。用 /turtle1/rotate_absolute 动作让海龟转到指定朝向，过程中打印反馈。

动作适合"要花一段时间、想看进度、可能中途取消"的任务：客户端发目标（goal），服务端边做边发
反馈（feedback），做完回结果（result）。这里的反馈是"还差多少弧度"。

运行：终端 1  ros2 run turtlesim turtlesim_node
      终端 2  python3 turtle_rotate.py --theta 90     # 转到朝上（90°）
验证：ros2 action list、ros2 action info /turtle1/rotate_absolute
"""
import argparse
import math
from typing import Any, List, Optional

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from turtlesim_msgs.action import RotateAbsolute


class Rotator(Node):
    """RotateAbsolute 动作的客户端。"""

    def __init__(self) -> None:
        super().__init__('turtle_rotate')
        self.client = ActionClient(self, RotateAbsolute, '/turtle1/rotate_absolute')
        self.feedback: List[float] = []

    def on_feedback(self, msg: Any) -> None:
        remaining = msg.feedback.remaining
        self.feedback.append(remaining)
        self.get_logger().info(f'反馈：还差 {math.degrees(remaining):6.1f}°')

    def rotate(self, theta: float, timeout: float = 20.0) -> float:
        """转到绝对朝向 theta（弧度），返回实际转过的角度（弧度）。"""
        if not self.client.wait_for_server(timeout_sec=5.0):
            raise RuntimeError('等了 5 秒还没有 rotate_absolute 动作：turtlesim_node 启动了吗？')
        goal = self.client.send_goal_async(RotateAbsolute.Goal(theta=theta),
                                           feedback_callback=self.on_feedback)
        rclpy.spin_until_future_complete(self, goal, timeout_sec=5.0)
        if not goal.done():
            raise RuntimeError('5 秒内没有收到 turtlesim 对目标的答复')
        handle = goal.result()
        if handle is None or not handle.accepted:
            raise RuntimeError('目标被拒绝')
        future = handle.get_result_async()
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout)
        response = future.result() if future.done() else None
        if response is None:
            raise RuntimeError(f'{timeout} 秒内没有转到位')
        return response.result.delta


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description='用动作让海龟转到指定朝向')
    ap.add_argument('--theta', type=float, default=90.0, help='目标朝向（度，逆时针为正）')
    a = ap.parse_args(argv)
    with rclpy.init():
        node = Rotator()
        try:
            delta = node.rotate(math.radians(a.theta))
        except RuntimeError as e:
            node.get_logger().error(str(e))
            return 1
        node.get_logger().info(f'结果：转过了 {math.degrees(delta):.1f}°，'
                               f'共收到 {len(node.feedback)} 条反馈')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
