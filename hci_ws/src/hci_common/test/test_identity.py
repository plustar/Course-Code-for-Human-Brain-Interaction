"""类别名的约定：id_map、显示名、谁是要找的人（练习 3 的 stu_<学号> 与 face）。"""
from hci_common.identity import display_name, is_target, parse_id_map


def test_parse_id_map_ignores_malformed_entries():
    entries = ['stu_2023123456=张三', 'bad-entry', ' stu_2 = 李四 ']
    assert parse_id_map(entries) == {'stu_2023123456': '张三', 'stu_2': '李四'}
    assert parse_id_map(None) == {}


def test_display_names():
    id_map = {'stu_2023123456': '张三'}
    assert display_name('stu_2023123456', id_map) == '张三 2023123456'
    assert display_name('stu_2023000000', id_map) == '2023000000'  # 没登记姓名：只显示学号
    assert display_name('face', id_map) == '他人'   # Track A 的他人类
    assert display_name('other', id_map) == '他人'  # Track B 的他人类：按角色一律显示"他人"


def test_is_target():
    assert is_target('stu_2023123456') and not is_target('face')
    assert is_target('stu_1', target_class='stu_1')
    assert not is_target('stu_2', target_class='stu_1')
    assert is_target('face', target_class='face')  # 演示模式：跟随任何人脸
