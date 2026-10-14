"""
练习 2-②：最小订阅者。收到 /chatter 上的消息就打印出来。

运行：python3 listener.py（与 talker.py 同时运行）
"""
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String


class Listener(Node):
    """订阅 /chatter 并打印。"""

    def __init__(self) -> None:
        super().__init__('listener')
        self.create_subscription(String, '/chatter', self.on_msg, 10)

    def on_msg(self, msg: String) -> None:  # 消息到达时自动调用
        self.get_logger().info(f'收到：{msg.data}')


def main() -> None:
    try:
        with rclpy.init():  # 与 talker.py 相同的官方写法
            node = Listener()
            rclpy.spin(node)  # 每收到一条消息，就调用一次 on_msg
    except (KeyboardInterrupt, ExternalShutdownException):  # Ctrl+C
        pass


if __name__ == '__main__':
    main()
