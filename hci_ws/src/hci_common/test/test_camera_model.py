"""相机模型：内参与视场角、像素与方位角、像素高度与距离（第 3 讲"相机成像模型"）。"""
import math
from types import SimpleNamespace

from hci_common.camera_model import CameraModel
from hypothesis import given
from hypothesis import strategies as st
import pytest

CAM = CameraModel.from_hfov(640, 480, 60.0)  # 与仿真和摄像头节点的默认值相同


def test_from_hfov_gives_square_pixels_and_centered_principal_point():
    assert CAM.hfov_deg == pytest.approx(60.0)
    assert (CAM.cx, CAM.cy) == (320.0, 240.0) and CAM.fx == CAM.fy
    assert CAM.fx == pytest.approx(320.0 / math.tan(math.radians(30.0)))  # 约 554 像素


@pytest.mark.parametrize('width, height, hfov', [(640, 480, 0.0), (640, 480, 180.0),
                                                 (0, 480, 60.0), (640, -1, 60.0)])
def test_from_hfov_rejects_bad_values(width, height, hfov):
    with pytest.raises(ValueError):
        CameraModel.from_hfov(width, height, hfov)


def test_bearing_is_zero_ahead_and_positive_on_the_left():
    assert CAM.bearing(320.0) == 0.0
    assert CAM.bearing(0.0) == pytest.approx(math.radians(30.0))  # 画面最左边：左 30°
    assert CAM.bearing(640.0) == pytest.approx(-math.radians(30.0))


@given(st.floats(min_value=-1.2, max_value=1.2))  # 约 ±69°，比视场还宽
def test_pixel_and_bearing_are_inverse(bearing):
    assert CAM.bearing(CAM.pixel_u(bearing)) == pytest.approx(bearing, abs=1e-9)


def test_depth_and_pixel_height_are_inverse():
    face_px = CAM.pixel_height(1.0, 0.22)  # 1 m 外一张 22 cm 高的脸
    assert face_px == pytest.approx(CAM.fy * 0.22)
    assert CAM.depth(face_px, 0.22) == pytest.approx(1.0)
    assert math.isnan(CAM.depth(0.0, 0.22)) and math.isnan(CAM.depth(10.0, 0.0))


def test_distance_is_depth_divided_by_cos_bearing():
    u = CAM.pixel_u(math.radians(25.0))
    face_px = CAM.pixel_height(2.0, 0.22)  # 深度 2 m
    assert CAM.distance(u, face_px, 0.22) == pytest.approx(2.0 / math.cos(math.radians(25.0)))


def test_camera_info_roundtrip_and_uncalibrated():
    info = SimpleNamespace(width=640, height=480, k=CAM.k_matrix())
    assert CameraModel.from_camera_info(info) == CAM
    uncalibrated = SimpleNamespace(width=640, height=480, k=[0.0] * 9)  # 没标定的相机 K 全为 0
    assert CameraModel.from_camera_info(uncalibrated) is None


def test_in_view_matches_the_field_of_view():
    assert CAM.in_view(math.radians(29.0)) and CAM.in_view(-math.radians(29.0))
    assert not CAM.in_view(math.radians(31.0))
