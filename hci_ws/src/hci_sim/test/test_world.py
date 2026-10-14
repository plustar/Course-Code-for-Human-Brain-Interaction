"""仿真世界：世界文件的解析与检查、走动的人、世界坐标到机器人坐标的换算。"""
import math

from hci_sim.world import default_world, load_world, parse_world, Person, Pose2D, relative
import pytest


def test_default_world_has_one_stranger_ahead_right():
    (stranger,) = default_world().persons
    assert (stranger.name, stranger.image) == ('stranger', 'stranger')
    assert (stranger.x, stranger.y) == (7.6, 4.7)


def test_parse_world_fills_in_defaults(tmp_path):
    path = tmp_path / 'world.yaml'
    path.write_text('persons:\n'
                    '  - {name: stranger, x: 8.5, y: 4.2}\n'
                    '  - {name: me, image: me, x: 8, y: 7, walk: 1.0, period: 8}\n',
                    encoding='utf-8')
    stranger, me = load_world(str(path)).persons
    assert stranger.image == 'stranger' and stranger.walk == 0.0 and stranger.face_height == 0.22
    assert (me.image, me.x, me.walk, me.period) == ('me', 8.0, 1.0, 8.0)
    assert isinstance(me.x, float)


@pytest.mark.parametrize('data, hint', [
    ({}, 'persons'),
    ({'persons': ['stranger']}, '应是字典'),
    ({'persons': [{'name': 'a', 'x': 1, 'y': 1, 'height': 2}]}, '未知的键'),
    ({'persons': [{'name': 'a', 'x': 1}]}, '缺少'),
    ({'persons': [{'name': 'a', 'x': 'left', 'y': 1}]}, '数值写错了'),
    ({'persons': [{'name': '2nd', 'x': 1, 'y': 1}]}, '字母、数字、下划线'),
    ({'persons': [{'name': 'a', 'x': 12, 'y': 1}]}, '范围'),
    ({'persons': [{'name': 'a', 'x': 5, 'y': 10.5, 'walk': 1}]}, '走动范围'),
    ({'persons': [{'name': 'a', 'x': 5, 'y': 5, 'image': '/home/me/me.jpg'}]}, 'image'),
    ({'persons': [{'name': 'a', 'x': 5, 'y': 5, 'face_ratio': 1.5}]}, 'face_ratio'),
    ({'persons': [{'name': 'a', 'x': 5, 'y': 5, 'walk': 1, 'period': 0}]}, 'period'),
    ({'persons': [{'name': 'a', 'x': 5, 'y': 5}, {'name': 'a', 'x': 6, 'y': 6}]}, '重复'),
])
def test_mistakes_in_the_world_file_are_explained(data, hint):
    with pytest.raises(ValueError, match=hint):
        parse_world(data)


def test_walking_person_moves_back_and_forth():
    walker = Person('walker', 8.0, 5.0, walk=1.0, period=8.0)
    assert walker.position(0.0) == (8.0, 5.0)
    assert walker.position(2.0) == pytest.approx((8.0, 6.0))  # 四分之一个周期：走到最远
    assert walker.position(6.0) == pytest.approx((8.0, 4.0))
    assert Person('still', 8.0, 5.0).position(3.0) == (8.0, 5.0)


@pytest.mark.parametrize('theta, point, expected', [
    (0.0, (8.0, 5.0), (3.0, 0.0)),  # 朝右：正前方 3 米
    (0.0, (5.0, 7.0), (0.0, 2.0)),  # 朝右：左边 2 米
    (math.pi / 2, (5.0, 8.0), (3.0, 0.0)),  # 朝上：正前方 3 米
    (math.pi / 2, (4.0, 5.0), (0.0, 1.0)),  # 朝上：左边 1 米
])
def test_relative_gives_ahead_and_left(theta, point, expected):
    assert relative(Pose2D(5.0, 5.0, theta), *point) == pytest.approx(expected)
