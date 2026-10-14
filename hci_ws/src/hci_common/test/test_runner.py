"""
节点运行样板 run()：Ctrl+C 与 kill 都先清理（destroy_node）再退出；启动失败给出一行中文原因。

每项测试在子进程里运行一个小节点，像在终端里一样向它发信号。最后一项检查运行子进程的
RosProcess 本身：覆盖率的设置不传给子进程。
"""
import signal
import sys
import textwrap
from types import SimpleNamespace

from hci_common.ros.runner import check_python_env
from hci_common.ros.testing import RosProcess
import pytest
from rclpy.node import Node

pytestmark = pytest.mark.ros

SCRIPT = textwrap.dedent("""
    import sys

    from hci_common.ros.runner import run
    from rclpy.node import Node


    class Demo(Node):
        def __init__(self):
            super().__init__('runner_demo')
            self.create_timer(0.1, lambda: None)
            print('READY', flush=True)

        def destroy_node(self):
            print('DESTROYED', flush=True)
            super().destroy_node()


    class Broken(Node):
        def __init__(self):
            raise RuntimeError('摄像头打不开')


    run(Broken if 'broken' in sys.argv else Demo)
    print('EXITED', flush=True)
""")


def start(*args: str) -> RosProcess:
    return RosProcess([sys.executable, '-c', SCRIPT, *args])


@pytest.mark.parametrize('sig', [signal.SIGINT, signal.SIGTERM], ids=['ctrl_c', 'kill'])
def test_signal_cleans_up_then_exits(ros_domain, sig):
    proc = start()
    assert proc.wait_for_output('READY', timeout=20), proc.output
    proc.proc.send_signal(sig)
    assert proc.proc.wait(timeout=10) == 0
    proc.stop()
    lines = proc.lines
    assert 'DESTROYED' in lines and 'EXITED' in lines, proc.output
    assert lines.index('DESTROYED') < lines.index('EXITED')


def test_startup_error_gives_one_line_reason(ros_domain):
    proc = start('broken')
    assert proc.proc.wait(timeout=20) != 0
    proc.stop()
    assert '[Broken] 启动或运行失败：摄像头打不开' in proc.output
    assert 'EXITED' not in proc.lines


def test_warns_when_not_run_by_system_python(ros_context, monkeypatch):
    node = Node('env_check')
    warnings = []
    monkeypatch.setattr(node, 'get_logger', lambda: SimpleNamespace(warning=warnings.append))
    monkeypatch.setattr(sys, 'executable', '/home/me/miniforge3/envs/hci-train/bin/python')
    check_python_env(node)
    assert warnings and 'conda deactivate' in warnings[0]
    warnings.clear()
    monkeypatch.setattr(sys, 'executable', '/usr/bin/python3')
    check_python_env(node)
    assert not warnings
    node.destroy_node()


def test_child_processes_do_not_inherit_coverage_settings(monkeypatch):
    # --cov 只统计测试进程本身；子进程也开启统计会变慢，系统测试的时序就和平时不一样了
    monkeypatch.setenv('COV_CORE_SOURCE', '/tmp')
    code = 'import os; print(sorted(k for k in os.environ if k.startswith("COV_CORE")))'
    proc = RosProcess([sys.executable, '-c', code])
    assert proc.wait_for_output('[]', timeout=10), proc.output
    proc.stop()
