"""
用 dataclass 描述节点参数：参数只写一处。

每个节点把自己的参数写成一个 dataclass，例如::

    @dataclass
    class Params:
        fps: float = param(30.0, '摄像头的发布频率（Hz）')

字段名就是参数名，默认值就是默认值，第二个参数是中文说明。
hci_common.ros.params.declare_params() 按它向 ROS 声明参数；
README 的参数表和 hci_bringup/config 下的 yaml 都由测试对照它检查，改参数只需要改这里。
"""
from dataclasses import field, fields, is_dataclass
from typing import Any, List, Tuple

TRUE_WORDS = ('1', 'true', 'yes', 'on')
FALSE_WORDS = ('0', 'false', 'no', 'off', '')


def param(default: Any, doc: str) -> Any:
    """声明一个参数字段：默认值加中文说明（列表默认值会自动复制，避免多个对象共用）。"""
    if isinstance(default, (list, tuple)):
        items = list(default)
        return field(default_factory=lambda: list(items), metadata={'doc': doc})
    return field(default=default, metadata={'doc': doc})


def param_table(spec: Any) -> List[Tuple[str, Any, str]]:
    """列出参数 dataclass 的全部字段：[(参数名, 默认值, 说明), ...]，供文档与测试使用。"""
    if not is_dataclass(spec):
        raise TypeError(f'{spec!r} 不是 dataclass')
    instance = spec() if isinstance(spec, type) else spec
    return [(f.name, getattr(instance, f.name), f.metadata.get('doc', ''))
            for f in fields(instance)]


def convert(value: Any, default: Any) -> Any:
    """
    把参数值转换成与默认值相同的类型。

    ROS 2 默认要求类型严格一致：参数声明为小数时，命令行写 -p fps:=30（整数）会报错。
    节点声明参数时打开 dynamic_typing，再用这个函数按默认值的类型转换，两种写法都能用。
    例：默认 30.0、传入 30 -> 30.0；默认 '0'、传入 0 -> '0'；
        默认是列表、传入 'stu_1=张三, stu_2=李四' -> ['stu_1=张三', 'stu_2=李四']
    转换不了（例如 'abc' 给小数参数、列表给单个值的参数、'ture' 给开关）时抛出 ValueError。
    """
    if isinstance(default, (list, tuple)):
        if isinstance(value, str):
            return [x.strip() for x in value.split(',') if x.strip()]
        return list(value)
    if isinstance(value, (list, tuple)):
        raise ValueError('这个参数只接受单个值，收到的是列表')
    if isinstance(default, bool):
        if isinstance(value, str):
            word = value.strip().lower()
            if word not in TRUE_WORDS + FALSE_WORDS:
                raise ValueError('应为 true 或 false')
            return word in TRUE_WORDS
        return bool(value)
    if isinstance(default, int) and isinstance(value, float) and not value.is_integer():
        raise ValueError('应为整数')
    if isinstance(default, (int, float, str)):
        return type(default)(value)
    return value


def require_positive(spec_instance: Any, *names: str) -> None:
    """检查这些参数都大于 0，例如频率：设成 0 时，定时器的周期 1/频率 就成了除以零。"""
    for name in names:
        value = getattr(spec_instance, name)
        if not value > 0:  # 也挡住 NaN
            raise ValueError(f'参数 {name} 必须大于 0，收到 {value}')
