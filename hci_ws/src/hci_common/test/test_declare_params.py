"""把参数 dataclass 声明给 ROS 节点：类型宽容、只读、带中文说明。"""
from dataclasses import dataclass
from typing import Any, List, Tuple

from hci_common.params import param
from hci_common.ros.params import declare_params
import pytest
from rclpy.node import Node
from rclpy.parameter import Parameter

pytestmark = pytest.mark.ros


@dataclass
class Spec:
    """测试用的参数表。"""

    fps: float = param(30.0, '帧率（Hz）')
    source: str = param('0', '摄像头编号或视频文件')
    show: bool = param(True, '是否弹窗')
    id_map: List[str] = param(['stu_1=张三'], '学号与姓名')
    extra: List[str] = param([], '默认为空的列表')


def declare(**overrides: Any) -> Tuple[Node, Spec]:
    node = Node('spec_node', parameter_overrides=[Parameter(k, value=v)
                                                  for k, v in overrides.items()])
    return node, declare_params(node, Spec)


def test_defaults_when_nothing_is_given(ros_context):
    node, p = declare()
    assert p == Spec()
    node.destroy_node()


def test_integer_for_float_and_number_for_string(ros_context):
    node, p = declare(fps=15, source=2, show='false')  # 即 -p fps:=15 -p source:=2 -p show:=false
    assert p.fps == 15.0 and isinstance(p.fps, float)
    assert p.source == '2' and p.show is False
    node.destroy_node()


def test_lists_including_an_empty_default(ros_context):
    node, p = declare(id_map=['stu_2=李四', 'stu_3=王五'], extra=['x'])
    assert p.id_map == ['stu_2=李四', 'stu_3=王五'] and p.extra == ['x']
    node.destroy_node()


def test_a_wrong_value_names_the_parameter(ros_context):
    node = Node('spec_node', parameter_overrides=[Parameter('fps', value='abc')])
    try:
        with pytest.raises(ValueError, match="参数 fps 的值 'abc' 不对"):
            declare_params(node, Spec)
    finally:
        node.destroy_node()


def test_parameters_are_read_only_and_described(ros_context):
    node, _ = declare()
    result = node.set_parameters([Parameter('fps', value=10.0)])[0]
    assert not result.successful  # 运行中修改会明确失败，而不是"设置成功却不生效"
    descriptor = node.describe_parameter('fps')
    assert descriptor.read_only and descriptor.description == '帧率（Hz）'
    node.destroy_node()
