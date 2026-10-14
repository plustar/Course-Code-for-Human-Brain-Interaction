"""
hci_perception 测试的公共设置。

ROS 相关的夹具（ros_domain、ros_context、namespace）来自 hci_common.ros.testing。
训练环境（conda）里没有 ROS：那里只运行纯 Python 部分的测试，节点测试与 ament 检查自动略过。
"""
import importlib.util
from pathlib import Path
from typing import Callable, Optional, Sequence

from hci_perception.testing import make_tiny_yolo, onnx_available
import numpy as np
import pytest

NEEDS_ROS = ['test_camera_node.py', 'test_recognizer_node.py', 'test_viewer_node.py',
             'test_flake8.py', 'test_mypy.py', 'test_pep257.py', 'test_xmllint.py']

if importlib.util.find_spec('rclpy') is None:
    collect_ignore = NEEDS_ROS
else:
    from hci_common.ros.testing import namespace, ros_context, ros_domain  # noqa: F401

TinyYolo = Callable[..., str]


@pytest.fixture
def tiny_yolo(tmp_path: Path) -> TinyYolo:
    """生成微型的"YOLO"ONNX 模型（见 hci_perception/testing.py），返回模型文件的路径。"""
    if not onnx_available():
        pytest.skip('需要 python3-onnx（bash env/setup_ros_env.sh）')

    def make(raw: np.ndarray, size: Optional[int] = 320,
             names: Optional[Sequence[str]] = None) -> str:
        index = len(list(tmp_path.glob('tiny_*.onnx')))
        return str(make_tiny_yolo(tmp_path / f'tiny_{index}.onnx', raw, size, names))

    return make
