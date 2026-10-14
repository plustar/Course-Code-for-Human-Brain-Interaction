"""练习 3 的公共工具：YOLO 标注行与逆变换、标注文件的位置、人脸检测、画面来源。"""
from pathlib import Path
import sys
from typing import Dict

from common import (detect_faces, frames, from_yolo_line, label_path, list_images, need,
                    open_video, to_yolo_line, YuNet)
import cv2
from hypothesis import given
from hypothesis import strategies as st
import numpy as np
import pytest
from synthetic import face_frame, write_faces, write_video


def test_yolo_line():
    line = to_yolo_line(0, (100, 50, 300, 250), 400, 500)
    assert line == '0 0.500000 0.300000 0.500000 0.400000'


@given(st.integers(0, 1), st.integers(0, 600), st.integers(0, 440), st.integers(1, 40),
       st.integers(1, 40))
def test_yolo_line_roundtrip(cls_id, x, y, w, h):
    box = (float(x), float(y), float(x + w), float(y + h))
    back_cls, back = from_yolo_line(to_yolo_line(cls_id, box, 640, 480), 640, 480)
    assert back_cls == cls_id and back == pytest.approx(box, abs=0.01)


def test_label_path_mirrors_the_image_path(tmp_path):
    img = tmp_path / 'self' / 's1' / 's1_000012.jpg'
    assert label_path(img, tmp_path) == tmp_path / 'labels' / 'self' / 's1' / 's1_000012.txt'


def test_list_images_finds_images_in_subfolders(tmp_path):
    for name in ('a/1.jpg', 'a/2.PNG', 'b/3.jpeg', 'b/notes.txt'):
        (tmp_path / name).parent.mkdir(exist_ok=True)
        (tmp_path / name).write_bytes(b'x')
    assert [p.name for p in list_images(tmp_path)] == ['1.jpg', '2.PNG', '3.jpeg']
    assert list_images(tmp_path / 'missing') == []


def test_detect_faces_sorts_by_size_and_drops_small_ones():
    frame = face_frame(x=20, y=20)
    frame[300:375, 500:575] = cv2.resize(face_frame()[115:364, 195:444], (75, 75))  # 一张小脸
    faces = detect_faces(YuNet(), frame)
    assert len(faces) == 2
    (big, _, row), (small, _, _) = faces
    assert (big[3] - big[1]) > (small[3] - small[1]) and row.shape == (15,)
    assert len(detect_faces(YuNet(), frame, min_size=0.2)) == 1  # 小于画面高度 20% 的忽略


def test_frames_from_a_folder_and_a_video(tmp_path):
    write_faces(tmp_path / 'pics', n=2)
    assert [name for name, _ in frames(str(tmp_path / 'pics'))] == ['img_000.jpg', 'img_001.jpg']
    video = write_video(tmp_path / 'clip.avi', [np.zeros((48, 64, 3), np.uint8)] * 4)
    assert [name for name, _ in frames(str(video))] == [f'frame_{i:06d}.jpg' for i in range(4)]


def test_frames_explains_a_missing_source():
    with pytest.raises(SystemExit, match='找不到'):
        list(frames('/no/such/video.mp4'))


def test_frames_takes_a_camera_device_path():
    # /dev/video99 与 99 一样是摄像头：说明它为什么打不开，而不是说找不到这个文件
    with pytest.raises(SystemExit, match='usbipd'):
        list(frames('/dev/video99'))


def test_camera_is_opened_like_the_ros_camera_node(monkeypatch):
    # 与 camera_node 相同的 MJPG、640×480：默认的 YUYV 经 WSL2 的 usbipd 转发时，画面下半部分是绿的
    props: Dict[int, float] = {}

    class FakeCapture:
        """记下 set() 调用的假摄像头。"""

        def __init__(self, index: int) -> None:
            self.index = index

        def set(self, prop: int, value: float) -> bool:  # noqa: A003  与 cv2 的方法同名
            props[prop] = value
            return True

        def isOpened(self) -> bool:
            return True

    monkeypatch.setattr(cv2, 'VideoCapture', FakeCapture)
    open_video('0')
    assert props[cv2.CAP_PROP_FOURCC] == cv2.VideoWriter_fourcc(*'MJPG')
    assert (props[cv2.CAP_PROP_FRAME_WIDTH], props[cv2.CAP_PROP_FRAME_HEIGHT]) == (640, 480)


def test_camera_that_cannot_open_explains_why():
    with pytest.raises(SystemExit, match='usbipd'):
        open_video('99')  # 不存在的 /dev/video99


def test_need_says_which_environment_to_use(monkeypatch):
    monkeypatch.setitem(sys.modules, 'ultralytics_missing', None)
    with pytest.raises(SystemExit, match='conda activate hci-train'):
        need('ultralytics_missing')


def test_scripts_import_without_side_effects():
    """每个脚本都能被导入（逻辑写在函数里），导入时不会开始录像、训练或下载。"""
    import importlib
    here = Path(__file__).resolve().parents[1]
    for script in sorted(here.glob('*.py')):
        module = importlib.import_module(script.stem)
        if script.stem != 'common':
            assert callable(getattr(module, 'main', None)), f'{script.name} 应有 main(argv)'
