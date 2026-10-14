"""hci_bringup 测试的公共设置：ROS 相关的夹具来自 hci_common.ros.testing。"""
import pytest

try:
    from hci_common.ros.testing import namespace, ros_context, ros_domain  # noqa: F401
except ImportError:  # 例如在训练环境（conda）里直接运行了 pytest：那里没有 ROS
    pytest.exit('这是 ROS 环境的测试：先 conda deactivate（直到提示符前面没有括号），'
                '再 source hci_ws/install/setup.bash', returncode=4)
