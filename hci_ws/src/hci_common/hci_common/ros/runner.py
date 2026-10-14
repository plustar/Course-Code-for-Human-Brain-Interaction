"""
运行节点的通用样板：初始化、spin、Ctrl+C 或 kill 时先清理再退出。

每个节点文件的 main() 只有一行 run(某某Node)，样板集中在这里。
"""
import signal
import sys
from types import FrameType
from typing import Callable, Optional

import rclpy
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions


def check_python_env(node: Node) -> None:
    """ROS 节点应当由系统 Python（/usr/bin/python3）运行；在 conda 环境里运行时给出提示。"""
    if not sys.executable.startswith('/usr/bin/'):
        node.get_logger().warning(
            f'本节点由 {sys.executable} 运行，不是系统 Python。'
            'ROS 节点要用系统 Python：如果激活了 conda 环境，请先 conda deactivate')


def _interrupt(signum: int, frame: Optional[FrameType]) -> None:
    raise KeyboardInterrupt


def run(node_factory: Callable[[], Node]) -> None:
    """
    创建节点并运行，直到按下 Ctrl+C 或进程被 kill。

    node_factory：节点类（或返回节点的函数）。本课程的节点都用单线程执行器：回调一个接一个
    执行，不用考虑多线程同时修改数据的问题。

    这里关闭了 rclpy 默认的信号处理：默认处理会在 Ctrl+C 的瞬间关闭通信，节点就来不及
    在退出前发出"停车"指令（见 behavior_node 的 destroy_node）。
    """
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    signal.signal(signal.SIGINT, signal.default_int_handler)  # 从后台脚本启动时 Ctrl+C 也有效
    signal.signal(signal.SIGTERM, _interrupt)  # kill 也按 Ctrl+C 处理，同样会先停车
    node: Optional[Node] = None
    executor: Optional[SingleThreadedExecutor] = None
    try:
        node = node_factory()
        check_python_env(node)
        executor = SingleThreadedExecutor()
        executor.add_node(node)
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except Exception as e:  # 启动失败时先给出一行中文原因，再打印完整的错误信息
        name = node.get_name() if node else getattr(node_factory, '__name__', '节点')
        print(f'[{name}] 启动或运行失败：{e}', file=sys.stderr)
        raise
    finally:
        # 在终端按 Ctrl+C 时，节点会先后收到终端和 ros2 launch 发来的两次 SIGINT；
        # 清理期间忽略后续信号，保证"停车"指令一定能发出去
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if executor is not None:
            executor.shutdown(timeout_sec=1.0)
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
