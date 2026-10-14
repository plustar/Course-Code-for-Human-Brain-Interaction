"""练习 2 测试的公共设置：这些测试要在 ROS 环境里运行，训练环境里自动略过。"""
import importlib.util

if importlib.util.find_spec('rclpy') is None:
    collect_ignore_glob = ['test_*.py']
else:
    from hci_common.ros.testing import ros_context, ros_domain  # noqa: F401
