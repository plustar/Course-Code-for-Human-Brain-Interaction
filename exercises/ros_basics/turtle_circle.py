"""
练习 2-③：让 turtlesim 里的海龟画圆（半径 r = v / ω）。

运行：终端 1  ros2 run turtlesim turtlesim_node
      终端 2  python3 turtle_circle.py --v 2.0 --w 1.0     # 半径 2.0
"""
import argparse
from typing import List, Optional

from geometry_msgs.msg import Twist
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions


class Circle(Node):
    """以 10 Hz 持续发送速度指令。"""

    def __init__(self, v: float, w: float) -> None:
        super().__init__('turtle_circle')
        self.pub = self.create_publisher(Twist, '/turtle1/cmd_vel', 10)
        self.v, self.w = v, w
        self.create_timer(0.1, self.on_timer)  # turtlesim 约 1 秒收不到指令就会停，所以持续发送
        radius = f'{abs(v / w):.2f}' if w else '无穷大（角速度为 0，走直线）'
        self.get_logger().info(f'线速度 {v}、角速度 {w}，理论半径 {radius}')

    def on_timer(self) -> None:
        t = Twist()
        t.linear.x, t.angular.z = self.v, self.w
        self.pub.publish(t)


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description='让海龟画圆')
    ap.add_argument('--v', type=float, default=2.0, help='线速度（m/s）')
    ap.add_argument('--w', type=float, default=1.0, help='角速度（rad/s）')
    a = ap.parse_args(argv)
    # 关闭 rclpy 默认的 Ctrl+C 处理：默认处理会立刻关闭通信，finally 里的停止指令就发不出去了
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = Circle(a.v, a.w)
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):  # Ctrl+C
        pass
    finally:
        node.pub.publish(Twist())  # 退出前发一条零速度，让海龟停下
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
