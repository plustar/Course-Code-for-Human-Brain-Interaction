"""
仿真世界：turtlesim 的 11 m × 11 m 平面，机器人就是 turtle1，世界里站着几个"虚拟人"。

坐标沿用 turtlesim：原点在左下角，x 向右、y 向上，单位米；角度逆时针为正。
turtle1 出生在 (5.54, 5.54)，朝向 x 正方向。世界写在 yaml 里（见 hci_bringup/config/sim_world.yaml）::

    persons:
      - name: stranger   # 名字，也是 turtlesim 里人物标记的名字
        image: stranger  # 头像：stranger = 内置的公有领域照片；me = 参数 me_image 指定的照片
        x: 7.6
        y: 4.7
"""
from dataclasses import dataclass, fields
import math
import re
from typing import Any, Dict, Tuple

from hci_common.camera_model import FACE_HEIGHT
from hci_common.samples import SAMPLE_FACE_RATIO

WORLD_SIZE = 11.0  # turtlesim 窗口对应的边长（米）
NAME_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')  # turtlesim 的海龟名字只能这样写
IMAGES = ('stranger', 'me')  # 头像：内置的公有领域照片；参数 me_image 指定的照片
NUMBERS = ('x', 'y', 'face_ratio', 'face_height', 'walk', 'period')


@dataclass(frozen=True)
class Pose2D:
    """机器人在平面上的位姿：位置（米）与朝向（弧度，逆时针为正）。"""

    x: float
    y: float
    theta: float


@dataclass(frozen=True)
class Person:
    """世界里的一个虚拟人。"""

    name: str
    x: float
    y: float
    image: str = 'stranger'  # stranger：内置照片；me：参数 me_image 指定的照片
    face_ratio: float = SAMPLE_FACE_RATIO  # 人脸框高度占头像高度的比例
    face_height: float = FACE_HEIGHT  # 人脸的实际高度（米），与识别节点估距离用的相同
    walk: float = 0.0  # 沿 y 方向来回走动的幅度（米），0 表示站着不动
    period: float = 10.0  # 走一个来回的时间（秒）

    def position(self, t: float) -> Tuple[float, float]:
        """t 秒时所在的位置。"""
        if self.walk <= 0.0:
            return self.x, self.y
        return self.x, self.y + self.walk * math.sin(2.0 * math.pi * t / self.period)


@dataclass(frozen=True)
class World:
    """一组虚拟人。"""

    persons: Tuple[Person, ...]


def default_world() -> World:
    """没有给世界文件时的默认世界：右前方约 2.2 m 处站着一位"陌生人"。"""
    return World((Person('stranger', 7.6, 4.7),))


def parse_world(data: Dict[str, Any]) -> World:
    """由 yaml 读出的字典构造世界，并检查每一项是否合理（报错用中文说明哪里不对）。"""
    if not isinstance(data, dict) or not isinstance(data.get('persons'), list):
        raise ValueError('世界文件应包含 persons 列表')
    allowed = {f.name for f in fields(Person)}
    persons = []
    for i, item in enumerate(data['persons'], start=1):
        where = f'persons 第 {i} 项'
        if not isinstance(item, dict):
            raise ValueError(f'{where}应是字典')
        unknown = set(item) - allowed
        if unknown:
            raise ValueError(f'{where}有未知的键：{sorted(unknown)}')
        missing = [key for key in ('name', 'x', 'y') if key not in item]
        if missing:
            raise ValueError(f'{where}缺少 {missing}')
        values: Dict[str, Any] = {}
        try:
            for key, value in item.items():
                values[key] = float(value) if key in NUMBERS else str(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f'{where}的数值写错了：{e}') from e
        person = Person(**values)
        check_person(person)
        persons.append(person)
    names = [p.name for p in persons]
    if len(set(names)) != len(names):
        raise ValueError(f'人物名字重复：{names}')
    return World(tuple(persons))


def check_person(person: Person) -> None:
    """检查一个虚拟人的设置，不合理时用中文说明。"""
    name = person.name
    if not NAME_PATTERN.match(name):
        raise ValueError(f'名字 {name!r} 只能由字母、数字、下划线组成，且不以数字开头')
    if person.image not in IMAGES:
        raise ValueError(f'{name} 的 image 只能是 {" 或 ".join(IMAGES)}，收到 {person.image!r}')
    if person.walk < 0.0 or person.period <= 0.0:
        raise ValueError(f'{name} 的 walk 不能为负，period 应为正')
    for y in (person.y - person.walk, person.y + person.walk):
        if not (0.0 < person.x < WORLD_SIZE and 0.0 < y < WORLD_SIZE):
            raise ValueError(f'{name} 的位置（含走动范围）不在 turtlesim 的 '
                             f'0–{WORLD_SIZE:.0f} 米范围内')
    if not 0.0 < person.face_ratio <= 1.0 or person.face_height <= 0.0:
        raise ValueError(f'{name} 的 face_ratio 应在 (0, 1]，face_height 应为正')


def load_world(path: str) -> World:
    """读取世界文件（yaml）。"""
    import yaml

    with open(path, encoding='utf-8') as f:
        return parse_world(yaml.safe_load(f))


def relative(pose: Pose2D, x: float, y: float) -> Tuple[float, float]:
    """世界坐标 (x, y) -> 机器人坐标（前方距离, 左方距离）。"""
    dx, dy = x - pose.x, y - pose.y
    c, s = math.cos(pose.theta), math.sin(pose.theta)
    return c * dx + s * dy, -s * dx + c * dy
