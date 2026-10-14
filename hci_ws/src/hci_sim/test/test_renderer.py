"""渲染：把针孔模型反过来用。投影的位置与大小、视野外不画、近的挡住远的。"""
import math
from typing import Optional, Tuple

from hci_common.camera_model import CameraModel
from hci_sim.renderer import FLOOR, Renderer, WALL
from hci_sim.world import Person, Pose2D
from hypothesis import given, settings
from hypothesis import strategies as st
import numpy as np
import pytest

CAMERA = CameraModel.from_hfov(640, 480, 60.0)
RED = np.full((100, 100, 3), (0, 0, 255), np.uint8)  # 纯色"头像"，便于找到它画在哪里
BLUE = np.full((100, 100, 3), (255, 0, 0), np.uint8)
ROBOT = Pose2D(2.0, 5.0, 0.0)  # 朝右（x 正方向）


def bbox(img: np.ndarray, bgr: Tuple[int, int, int]) -> Optional[Tuple[int, int, int, int]]:
    """某种颜色的像素占据的矩形 (x1, y1, x2, y2)，不含 x2、y2；没有时返回 None。"""
    ys, xs = np.nonzero((img == bgr).all(axis=2))
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def place(depth: float, bearing: float) -> Tuple[float, float]:
    """机器人前方 depth 米、方位 bearing（左正）处的世界坐标。"""
    return ROBOT.x + depth, ROBOT.y + depth * math.tan(bearing)


def test_background_is_wall_above_and_floor_below():
    img = Renderer(CAMERA, {}).render(ROBOT, [])
    assert tuple(img[10, 10]) == WALL and tuple(img[470, 10]) == FLOOR


def test_person_ahead_is_centered_with_the_size_of_the_pinhole_model():
    person = Person('p', 0, 0, image='red', face_ratio=0.5)
    img = Renderer(CAMERA, {'red': RED}).render(ROBOT, [(person, *place(2.0, 0.0))])
    x1, y1, x2, y2 = bbox(img, (0, 0, 255))
    expected_height = CAMERA.fy * 0.22 / 2.0 / 0.5  # 人脸像素高 ÷ 人脸占头像的比例
    assert y2 - y1 == pytest.approx(expected_height, abs=1)
    assert (x1 + x2) / 2 == pytest.approx(CAMERA.cx, abs=1)
    assert (y1 + y2) / 2 == pytest.approx(CAMERA.cy, abs=1)


@settings(max_examples=150, deadline=None)
@given(st.floats(1.0, 4.0), st.floats(-25.0, 25.0))
def test_projection_matches_the_camera_model(depth, bearing_deg):
    bearing = math.radians(bearing_deg)
    person = Person('p', 0, 0, image='red', face_ratio=0.5)
    img = Renderer(CAMERA, {'red': RED}).render(ROBOT, [(person, *place(depth, bearing))])
    x1, y1, x2, y2 = bbox(img, (0, 0, 255))
    size = CAMERA.pixel_height(depth, 0.22) / 0.5  # 正方形头像的边长：越远越小
    left = CAMERA.pixel_u(bearing) - size / 2.0  # 中心画在方位角对应的那一列
    assert y2 - y1 == pytest.approx(size, abs=2.0)
    assert x1 == pytest.approx(max(left, 0.0), abs=1.0)  # 超出画面的部分被裁掉
    assert x2 == pytest.approx(min(left + size, 640.0), abs=1.0)


@pytest.mark.parametrize('position', [(1.0, 5.0), (3.0, 9.0), (2.1, 5.0)],
                         ids=['behind', 'outside_the_view', 'too_close'])
def test_people_outside_the_view_are_not_drawn(position):
    person = Person('p', 0, 0, image='red')
    img = Renderer(CAMERA, {'red': RED}).render(ROBOT, [(person, *position)])
    assert bbox(img, (0, 0, 255)) is None


def test_person_at_the_edge_is_partly_drawn():
    person = Person('p', 0, 0, image='red', face_ratio=0.5)
    edge = math.radians(30.0) + 0.05  # 中心刚出视场
    img = Renderer(CAMERA, {'red': RED}).render(ROBOT, [(person, *place(2.0, edge))])
    x1, _, x2, _ = bbox(img, (0, 0, 255))
    assert x1 == 0 and 0 < x2 < 100


def test_near_person_hides_the_far_one():
    near = Person('near', 0, 0, image='blue')
    far = Person('far', 0, 0, image='red')
    renderer = Renderer(CAMERA, {'red': RED, 'blue': BLUE})
    for order in ([(far, *place(3.0, 0.0)), (near, *place(1.5, 0.0))],
                  [(near, *place(1.5, 0.0)), (far, *place(3.0, 0.0))]):
        img = renderer.render(ROBOT, order)
        assert tuple(img[240, 320]) == (255, 0, 0)  # 不管列表顺序，画面中心都是近处的人
        assert bbox(img, (0, 0, 255)) is None  # 远处的人整个被挡住


def test_person_without_an_image_is_skipped():
    me = Person('me', 0, 0, image='me')  # 没有给 me_image
    img = Renderer(CAMERA, {'red': RED}).render(ROBOT, [(me, *place(2.0, 0.0))])
    assert bbox(img, (0, 0, 255)) is None
