"""参数 dataclass：参数只写一处，命令行传入的值按默认值的类型转换。"""
from dataclasses import dataclass
from typing import List

from hci_common.params import convert, param, param_table, require_positive
import pytest


@dataclass
class Spec:
    """测试用的参数表。"""

    fps: float = param(30.0, '帧率（Hz）')
    names: List[str] = param(['stu_1=张三'], '学号与姓名')


def test_param_table_lists_name_default_and_doc():
    assert param_table(Spec) == [('fps', 30.0, '帧率（Hz）'), ('names', ['stu_1=张三'], '学号与姓名')]
    assert param_table(Spec(fps=15.0))[0] == ('fps', 15.0, '帧率（Hz）')
    with pytest.raises(TypeError):
        param_table(object)


def test_list_defaults_are_not_shared_between_objects():
    a, b = Spec(), Spec()
    a.names.append('stu_2=李四')
    assert b.names == ['stu_1=张三']


def test_convert_follows_the_type_of_the_default():
    assert convert(30, 30.0) == 30.0 and isinstance(convert(30, 30.0), float)
    assert convert(416.0, 416) == 416 and convert(0, '0') == '0'
    assert convert('false', True) is False and convert(1, False) is True
    assert convert('stu_1=张三, stu_2=李四', ['x']) == ['stu_1=张三', 'stu_2=李四']
    assert convert(('a', 'b'), ['x']) == ['a', 'b']


@pytest.mark.parametrize('value, default', [('abc', 30.0), (['a', 'b'], 30.0), ('ture', True),
                                            (2.5, 416)])
def test_convert_rejects_values_it_cannot_understand(value, default):
    # 例如 -p fps:=abc、给单个值的参数传了列表、开关写成 ture、整数参数写成 2.5
    with pytest.raises(ValueError):
        convert(value, default)


def test_switch_words():
    assert convert('ON', False) is True and convert('no', True) is False
    assert convert('', True) is False


@pytest.mark.parametrize('fps', [0.0, -1.0, float('nan')])
def test_require_positive_names_the_parameter(fps):
    require_positive(Spec(fps=30.0), 'fps')
    with pytest.raises(ValueError, match='fps 必须大于 0'):
        require_positive(Spec(fps=fps), 'fps')
