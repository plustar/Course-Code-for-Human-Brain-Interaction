"""
练习 2-④：服务。调用 turtlesim 的 /spawn 服务，在指定位置放一只新海龟。

服务是"一问一答"：客户端发一个请求，等服务端处理完回一个应答。与话题不同，它适合
"做一件事、要知道结果"的场合。期末的仿真器 hci_sim 就是用这个服务在 turtlesim 里标出虚拟人。

运行：终端 1  ros2 run turtlesim turtlesim_node
      终端 2  python3 turtle_spawn.py --x 2 --y 8 --name buddy
验证：ros2 service list、ros2 topic echo /buddy/pose
"""
import argparse
import math
from typing import List, Optional

import rclpy
from rclpy.node import Node
from turtlesim_msgs.srv import Spawn


class Spawner(Node):
    """调用 /spawn 服务的客户端。"""

    def __init__(self) -> None:
        super().__init__('turtle_spawn')
        self.client = self.create_client(Spawn, '/spawn')

    def spawn(self, x: float, y: float, theta: float, name: str) -> str:
        """请求在 (x, y) 处放一只朝向 theta（弧度）的海龟，返回它实际的名字。"""
        if not self.client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError('等了 5 秒还没有 /spawn 服务：turtlesim_node 启动了吗？')
        future = self.client.call_async(Spawn.Request(x=x, y=y, theta=theta, name=name))
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)  # 等应答，同时处理回调
        response = future.result() if future.done() else None
        if response is None:
            raise RuntimeError('5 秒内没有收到 /spawn 的应答')
        if not response.name:  # turtlesim 不能放下海龟时也会应答，只是名字为空
            raise RuntimeError(f'turtlesim 没有放下海龟：名字 {name!r} 已经被占用了，换一个 --name')
        return response.name


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description='调用 /spawn 服务放一只新海龟')
    ap.add_argument('--x', type=float, default=2.0)
    ap.add_argument('--y', type=float, default=8.0)
    ap.add_argument('--theta', type=float, default=0.0, help='朝向（度，逆时针为正）')
    ap.add_argument('--name', default='', help='新海龟的名字；留空由 turtlesim 自动起名')
    a = ap.parse_args(argv)
    with rclpy.init():
        node = Spawner()
        try:
            name = node.spawn(a.x, a.y, math.radians(a.theta), a.name)
        except RuntimeError as e:
            node.get_logger().error(str(e))
            return 1
        node.get_logger().info(f'已放下海龟 {name}：位置 ({a.x}, {a.y})，朝向 {a.theta}°')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
