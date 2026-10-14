"""
"认出我"的命名约定：类别角色（本人 / 他人）与显示名。

练习 3 的 YOLO 模型固定两类，**按角色命名、不绑定具体实现**：
  · 第 0 类 本人：`stu_<学号>`（以 TARGET_PREFIX 开头）
  · 第 1 类 他人：类别名可配——Track A（人脸识别）默认叫 `face`，
    Track B（学生证 / 自制标志物）用 `other`。
代码一律按"是不是 `stu_` 开头"来判断角色，**不依赖他人类到底叫什么**，所以同一套
核心代码对两条 Track 完全等价；换 Track 只是换第 1 类的名字和负样本来源。

参数 id_map 把类别名对应到姓名，如 ['stu_2023123456=张三']，画面显示"张三 2023123456"。
感知包用它显示名字，行为包用它判断"是不是要找的人"，所以放在地基包里。
"""
from typing import Dict, Iterable, Optional

TARGET_PREFIX = 'stu_'          # 本人类别（第 0 类）的前缀
DEFAULT_OTHER_CLASS = 'face'    # 他人类（第 1 类）的默认名：Track A=人脸；Track B 改为 'other'
OTHERS = DEFAULT_OTHER_CLASS    # 向后兼容的别名；人脸后端（yunet/sface）用它标注他人


def parse_id_map(entries: Optional[Iterable[str]]) -> Dict[str, str]:
    """把 ['stu_2023123456=张三', ...] 解析成 {'stu_2023123456': '张三'}；格式不对的条目忽略。"""
    out: Dict[str, str] = {}
    for entry in entries or []:
        if '=' in entry:
            key, value = entry.split('=', 1)
            out[key.strip()] = value.strip()
    return out


def display_name(class_name: str, id_map: Dict[str, str]) -> str:
    """
    类别名 -> 显示名。

    本人（`stu_` 开头）-> '姓名 学号'（没登记姓名时只显示学号）；
    其余一律视为"他人"类（不论它叫 `face` 还是 `other`）-> '他人'。
    按角色判断，所以 Track A / Track B 的他人类都正确显示为"他人"。
    """
    if class_name.startswith(TARGET_PREFIX):
        student_id = class_name[len(TARGET_PREFIX):]
        return f'{id_map.get(class_name, "")} {student_id}'.strip()
    return '他人'


def is_target(class_name: str, target_class: str = '') -> bool:
    """是不是要找的人：target_class 为空时，任何 stu_ 开头的类别都算；否则必须完全相同。"""
    if target_class:
        return class_name == target_class
    return class_name.startswith(TARGET_PREFIX)
