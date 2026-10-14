"""
hci_common 测试的公共设置。

ROS 相关的夹具（ros_domain、ros_context、namespace）来自 hci_common.ros.testing。
训练环境（conda）里没有 ROS：那里只运行纯 Python 部分的测试，下面这些文件自动略过。
"""
import importlib.util

NEEDS_ROS = ['test_declare_params.py', 'test_image_msgs.py', 'test_qos.py', 'test_runner.py',
             'test_flake8.py', 'test_mypy.py', 'test_pep257.py', 'test_xmllint.py']

if importlib.util.find_spec('rclpy') is None:
    collect_ignore = NEEDS_ROS
else:
    from hci_common.ros.testing import namespace, ros_context, ros_domain  # noqa: F401
