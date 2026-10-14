"""
练习 2-①：最小发布者。每 0.5 秒向 /chatter 发布一句话。

运行：source /opt/ros/lyrical/setup.bash && python3 talker.py（不要激活 conda）
验证：另开终端 ros2 topic echo /chatter
"""
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String


class Talker(Node):
    """每 0.5 秒发布一条消息。"""

    def __init__(self) -> None:
        super().__init__('talker')  # 节点名
        self.pub = self.create_publisher(String, '/chatter', 10)  # 话题名、队列深度
        self.count = 0
        self.create_timer(0.5, self.on_timer)  # 定时器：每 0.5 秒回调一次

    def on_timer(self) -> None:
        msg = String(data=f'你好，ROS 2！第 {self.count} 条')
        self.pub.publish(msg)
        self.get_logger().info(f'发布：{msg.data}')
        self.count += 1


def main() -> None:
    # ROS 2 Lyrical 官方教程的写法：离开 with 时自动关闭 rclpy
    try:
        with rclpy.init():
            node = Talker()
            rclpy.spin(node)  # 进入事件循环，等待定时器触发
    except (KeyboardInterrupt, ExternalShutdownException):  # Ctrl+C
        pass


if __name__ == '__main__':
    main()
