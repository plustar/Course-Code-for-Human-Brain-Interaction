"""
节点测试与系统测试的辅助工具（只在测试里用）。

- isolate_ros_domain() 与夹具 ros_domain：本测试进程分到一个与别人不冲突的 ROS_DOMAIN_ID
  （Lyrical 自带的 rmw_test_fixture），并且只在本机发现。局域网里别的 ROS 程序干扰不到测试，
  测试也不打扰它们；测试启动的子进程继承同一个 domain。
- ros_context：每个测试独立初始化、关闭 rclpy。
- namespace：每个测试一个随机命名空间，前一个测试留下的话题不会串进来。
- Probe：探针节点，替测试发布消息、记录收到的消息；LogSpy：记下节点打印的日志。
- spin_until、spin_for：一边转动执行器一边等待。
- RosProcess：以子进程运行 ros2 launch 或 ros2 run，结束时像在终端按 Ctrl+C 一样停止。
- needs_gui：要弹窗的测试，只有用 bash tools/run_tests.sh --gui 运行时才执行。

在包的 test/conftest.py 里导入需要的夹具即可使用，例如::

    from hci_common.ros.testing import namespace, ros_context, ros_domain  # noqa: F401
"""
import atexit
import os
import random
import signal
import subprocess
import threading
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

import pytest
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.publisher import Publisher

_domain: Optional[int] = None

needs_gui = pytest.mark.skipif(os.environ.get('HCI_TEST_GUI') != '1',
                               reason='要弹出窗口：用 bash tools/run_tests.sh --gui 运行')


def isolate_ros_domain() -> int:
    """
    让本进程（以及它启动的子进程）使用一个独占的 ROS_DOMAIN_ID，只在本机发现。

    可以重复调用，只在第一次生效；进程退出时自动释放。返回分到的 domain。
    """
    global _domain
    if _domain is None:
        os.environ['ROS_AUTOMATIC_DISCOVERY_RANGE'] = 'LOCALHOST'
        try:
            from rmw_test_fixture_implementation import RMWTestIsolator
        except ImportError:  # 极少数安装缺少这个包：退回随机选一个 domain
            os.environ['ROS_DOMAIN_ID'] = str(random.randint(1, 100))
        else:
            isolator = RMWTestIsolator()
            isolator.__enter__()
            atexit.register(isolator.__exit__, None, None, None)
        _domain = int(os.environ.get('ROS_DOMAIN_ID', '0'))
    return _domain


@pytest.fixture(scope='session')
def ros_domain() -> int:
    """整个测试进程用一个独占的 ROS_DOMAIN_ID，只在本机发现。"""
    return isolate_ros_domain()


@pytest.fixture
def ros_context(ros_domain: int) -> Iterator[None]:
    """为一个测试初始化 rclpy，测试结束后关闭。"""
    rclpy.init()
    try:
        yield
    finally:
        rclpy.try_shutdown()


@pytest.fixture
def namespace() -> str:
    """一个测试一个随机命名空间。"""
    return f'/test_{random.randint(0, 10**9):09d}'


class Probe(Node):
    """测试用的探针节点：listen() 记录某个话题收到的消息，talker() 创建发布者。"""

    def __init__(self, namespace: str = '', name: str = 'probe') -> None:
        super().__init__(name, namespace=namespace)

    def listen(self, msg_type: Any, topic: str, qos: Any = 10) -> List[Any]:
        """订阅一个话题，返回会不断追加新消息的列表。"""
        msgs: List[Any] = []
        self.create_subscription(msg_type, topic, msgs.append, qos)
        return msgs

    def talker(self, msg_type: Any, topic: str, qos: Any = 10) -> Publisher:
        """创建一个发布者。"""
        return self.create_publisher(msg_type, topic, qos)


class LogSpy:
    """
    记录节点日志的替身：spy = LogSpy.attach(node) 之后，node 打印的每一条日志都记在 spy 里。

    用来检查"该提醒的时候提醒了"，例如 spy.text('warning') 里有没有某句话。
    """

    def __init__(self) -> None:
        self.records: List[Tuple[str, str]] = []

    @classmethod
    def attach(cls, node: Node) -> 'LogSpy':
        spy = cls()
        setattr(node, 'get_logger', lambda: spy)
        return spy

    def text(self, level: str = '') -> str:
        """某个级别（留空为全部）的日志，一条一行。"""
        return '\n'.join(msg for lv, msg in self.records if not level or lv == level)

    def _log(self, level: str, msg: Any) -> bool:
        self.records.append((level, str(msg)))
        return True

    def debug(self, msg: Any, **kwargs: Any) -> bool:
        return self._log('debug', msg)

    def info(self, msg: Any, **kwargs: Any) -> bool:
        return self._log('info', msg)

    def warning(self, msg: Any, **kwargs: Any) -> bool:
        return self._log('warning', msg)

    def error(self, msg: Any, **kwargs: Any) -> bool:
        return self._log('error', msg)


def spin_until(nodes: Sequence[Node], condition: Callable[[], bool], timeout: float = 5.0,
               step: float = 0.02) -> bool:
    """转动这些节点，直到 condition() 为真或超时；返回最后一次检查的结果。"""
    executor = SingleThreadedExecutor()
    for node in nodes:
        executor.add_node(node)
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if condition():
                return True
            executor.spin_once(timeout_sec=step)
        return condition()
    finally:
        for node in nodes:
            executor.remove_node(node)
        executor.shutdown()


def spin_for(nodes: Sequence[Node], seconds: float) -> None:
    """转动这些节点一段时间（等消息传开、定时器触发）。"""
    spin_until(nodes, lambda: False, timeout=seconds)


class RosProcess:
    """
    以子进程运行一条命令（ros2 launch、ros2 run 或 python3 脚本），收集它的全部输出。

    子进程单独成为一个进程组；stop() 向整个组发送 SIGINT，与在终端里按 Ctrl+C 相同。
    """

    def __init__(self, cmd: Sequence[str], env: Optional[Dict[str, str]] = None,
                 cwd: Optional[str] = None) -> None:
        self.cmd = list(cmd)
        # 覆盖率只统计测试进程本身（--cov）。apt 版 pytest-cov 5 会通过 COV_CORE_* 在子进程里也开启
        # 统计，节点因此变慢，Ctrl+C 的时序也跟着变：去掉它们，测试在有无 --cov 时行为一致
        full_env = {k: v for k, v in os.environ.items() if not k.startswith('COV_CORE_')}
        full_env.update(env or {})
        full_env.setdefault('PYTHONUNBUFFERED', '1')  # 输出立刻可见，测试才能及时看到日志
        self.proc = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, text=True, env=full_env, cwd=cwd,
                                     start_new_session=True)
        self.lines: List[str] = []
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self.lines.append(line.rstrip('\n'))

    @property
    def output(self) -> str:
        """到目前为止的全部输出。"""
        return '\n'.join(self.lines)

    def wait_for_output(self, text: str, timeout: float = 20.0) -> bool:
        """等到输出里出现 text，或进程退出、超时。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if text in self.output:
                return True
            if self.proc.poll() is not None:
                self._reader.join(timeout=1.0)
                return text in self.output
            time.sleep(0.05)
        return text in self.output

    def stop(self, timeout: float = 15.0) -> int:
        """像按 Ctrl+C 一样停止整个进程组，返回主进程的退出码；超时后强制结束。"""
        group = self.proc.pid
        if self.proc.poll() is None:
            _signal_group(group, signal.SIGINT)
            try:
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                _signal_group(group, signal.SIGKILL)
                self.proc.wait()
        # 主进程退出后，组里可能还有没退出的节点：稍等片刻，再强制结束，不留后台进程
        deadline = time.monotonic() + 5.0
        while _signal_group(group, 0) and time.monotonic() < deadline:
            time.sleep(0.1)
        _signal_group(group, signal.SIGKILL)
        self._reader.join(timeout=2.0)
        return self.proc.returncode


def _signal_group(group: int, sig: int) -> bool:
    """向进程组发信号；组里已经没有进程时返回 False。"""
    try:
        os.killpg(group, sig)
        return True
    except (ProcessLookupError, PermissionError):
        return False
