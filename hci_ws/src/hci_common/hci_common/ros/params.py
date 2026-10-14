"""把参数 dataclass 声明给 ROS 节点：一个字段一个参数，带中文说明，只读。"""
from typing import Any, Dict, Type, TypeVar

from hci_common.params import convert, param_table
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.node import Node

T = TypeVar('T')


def declare_params(node: Node, spec: Type[T]) -> T:
    """
    按参数 dataclass 声明全部参数，返回填好实际取值的参数对象。

    打开 dynamic_typing 后再按默认值的类型转换，所以 -p fps:=30 与 -p fps:=30.0 都能用。
    参数只在启动时读取一次，因此设为只读：运行中执行 ros2 param set 会明确报错，
    而不是"设置成功却不生效"。说明文字可以用 ros2 param describe 查看。
    """
    values: Dict[str, Any] = {}
    for name, default, doc in param_table(spec):
        descriptor = ParameterDescriptor(description=doc, dynamic_typing=True, read_only=True)
        # 空列表无法推断参数类型，先声明为"未设置"，没有传值时使用默认值
        initial = None if default == [] else default
        node.declare_parameter(name, initial, descriptor)
        value = node.get_parameter(name).value
        try:
            values[name] = default if value is None else convert(value, default)
        except (TypeError, ValueError) as e:  # 报错里带上参数名，学生才知道是哪一个写错了
            raise ValueError(f'参数 {name} 的值 {value!r} 不对：{e}（默认值是 {default!r}）') \
                from None
    return spec(**values)
