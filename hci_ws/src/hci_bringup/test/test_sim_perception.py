"""
仿真画面能被真实的识别后端认出来（跨包检查：hci_sim 渲染、hci_perception 识别）。

把公有领域人脸按针孔模型渲染到 1–4 米、左右 25° 之内，用 YuNet 检测，再用同一个相机模型
反算距离与方位：距离误差不超过 10%、方位误差不超过 1°。这保证了仿真闭环里的"看见"是真的。
"""
import math

from hci_common.camera_model import CameraModel
from hci_common.samples import sample_face, SAMPLE_FACE_RATIO
from hci_perception.recognition.yunet import YuNet
from hci_sim.renderer import Renderer
from hci_sim.world import Person, Pose2D
import pytest

CAMERA = CameraModel.from_hfov(640, 480, 60.0)
ROBOT = Pose2D(1.0, 5.5, 0.0)
STRANGER = Person('stranger', 0.0, 0.0, face_ratio=SAMPLE_FACE_RATIO)


@pytest.fixture(scope='module')
def detector() -> YuNet:
    return YuNet()


@pytest.mark.parametrize('distance', [1.0, 1.5, 2.0, 3.0, 4.0])
@pytest.mark.parametrize('bearing_deg', [-25.0, 0.0, 25.0])
def test_rendered_face_is_detected_where_it_was_placed(detector, distance, bearing_deg):
    bearing = math.radians(bearing_deg)
    x = ROBOT.x + distance * math.cos(bearing)
    y = ROBOT.y + distance * math.sin(bearing)
    frame = Renderer(CAMERA, {'stranger': sample_face()}).render(ROBOT, [(STRANGER, x, y)])
    faces = detector.detect(frame)
    assert len(faces) == 1, f'{distance} m、{bearing_deg}° 处的人脸没有被检出'
    face = faces[0]
    assert CAMERA.distance(face.center_x, face.height, 0.22) == pytest.approx(distance, rel=0.10)
    assert math.degrees(CAMERA.bearing(face.center_x)) == pytest.approx(bearing_deg, abs=1.0)
