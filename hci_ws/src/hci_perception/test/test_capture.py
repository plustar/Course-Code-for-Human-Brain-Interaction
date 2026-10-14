"""图像来源：视频文件按自身帧率播放、循环；摄像头的像素格式与分辨率；打不开时的中文提示。"""
import os
from pathlib import Path
from typing import Any, Dict, List

import cv2
from hci_perception.capture import camera_index, camera_problem, VideoSource
import numpy as np
import pytest


@pytest.fixture
def video(tmp_path: Path) -> str:
    """一段 10 帧、12 帧/秒的小视频，第 i 帧的灰度值是 20 × i。"""
    path = str(tmp_path / 'clip.avi')
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'MJPG'), 12.0, (64, 48))
    for i in range(10):
        writer.write(np.full((48, 64, 3), 20 * i, np.uint8))
    writer.release()
    return path


def brightness(frame: Any) -> int:
    return int(round(float(frame.mean()) / 20.0))  # 还原成帧号


def test_video_file_reports_its_size_and_frame_rate(video):
    source = VideoSource(video)
    assert source.is_file and source.size == (64, 48) and source.native_fps == pytest.approx(12.0)
    assert [brightness(source.read()) for _ in range(3)] == [0, 1, 2]
    source.release()


def test_video_loops_back_to_the_first_frame(video):
    source = VideoSource(video, loop=True)
    frames = [brightness(source.read()) for _ in range(12)]
    assert frames[:10] == list(range(10)) and frames[10:] == [0, 1]


def test_video_without_loop_ends_with_none(video):
    source = VideoSource(video, loop=False)
    for _ in range(10):
        assert source.read() is not None
    assert source.read() is None


def test_missing_video_file_asks_for_an_absolute_path():
    with pytest.raises(FileNotFoundError, match='绝对路径'):
        VideoSource('/no/such/video.mp4')


@pytest.mark.parametrize('source', ['99', '/dev/video99'])  # 编号和设备文件两种写法
def test_camera_that_cannot_open_suggests_usbipd_or_a_video(source):
    with pytest.raises(RuntimeError, match='无法打开摄像头 99.*usbipd'):
        VideoSource(source)  # 不存在的 /dev/video99


def test_camera_index():
    assert camera_index('0') == 0 and camera_index('/dev/video2') == 2
    assert camera_index('/home/me/me.mp4') is None and camera_index('video0') is None


def test_camera_problem_names_the_likely_cause(tmp_path, monkeypatch):
    assert 'usbipd' in camera_problem(0, str(tmp_path))  # 设备还没转发进来
    (tmp_path / 'video0').touch()
    monkeypatch.setattr(os, 'access', lambda path, mode: False)
    assert 'usermod -aG video' in camera_problem(0, str(tmp_path))  # WSL2 的新用户不在 video 组
    monkeypatch.setattr(os, 'access', lambda path, mode: True)
    assert '占用' in camera_problem(0, str(tmp_path))


class FakeCapture:
    """记下 set() 调用的假摄像头。"""

    calls: List[Dict[int, float]] = []

    def __init__(self, index: int) -> None:
        self.index = index
        self.props: Dict[int, float] = {}
        FakeCapture.calls.append(self.props)

    # 方法名与 cv2.VideoCapture.set 相同，所以忽略"遮蔽内置名 set"的提示
    def set(self, prop: int, value: float) -> bool:  # noqa: A003
        self.props[prop] = value
        return True

    def isOpened(self) -> bool:
        return True


@pytest.mark.parametrize('fourcc, expected', [('MJPG', cv2.VideoWriter_fourcc(*'MJPG')),
                                              ('', None)])
def test_camera_gets_pixel_format_and_resolution(monkeypatch, fourcc, expected):
    FakeCapture.calls = []
    monkeypatch.setattr(cv2, 'VideoCapture', FakeCapture)
    source = VideoSource('0', width=1280, height=720, fourcc=fourcc)
    props = FakeCapture.calls[0]
    assert not source.is_file and source.cap.index == 0
    assert props[cv2.CAP_PROP_FRAME_WIDTH] == 1280 and props[cv2.CAP_PROP_FRAME_HEIGHT] == 720
    assert props.get(cv2.CAP_PROP_FOURCC) == expected
