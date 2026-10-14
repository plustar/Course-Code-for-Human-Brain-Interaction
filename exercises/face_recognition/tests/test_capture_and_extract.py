"""第 1、2 步：录制（用视频文件代替摄像头）与抽帧（去掉模糊帧和重复帧）。"""
from capture_sessions import record
import cv2
from extract_frames import extract, main as extract_main, sharpness
import numpy as np
import pytest
from synthetic import write_video

RNG = np.random.default_rng(0)


def sharp() -> np.ndarray:
    return RNG.integers(0, 256, (120, 160, 3), np.uint8)  # 随机噪声：非常"清晰"


def blurred(img: np.ndarray) -> np.ndarray:
    return cv2.GaussianBlur(img, (31, 31), 10)


def test_record_saves_every_frame(tmp_path):
    camera = write_video(tmp_path / 'camera.avi', [sharp() for _ in range(10)])
    out = tmp_path / 's1.mp4'
    assert record(str(camera), out, seconds=10, fps=15, show=False) == 10  # 视频读完就停
    cap = cv2.VideoCapture(str(out))
    assert cap.isOpened() and int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 10


def test_record_explains_when_the_video_cannot_be_written(tmp_path, monkeypatch):
    camera = write_video(tmp_path / 'camera.avi', [sharp() for _ in range(3)])

    class BrokenWriter:
        """写不进去的 VideoWriter（例如没有编码器、文件夹不能写）。"""

        def __init__(self, *args: object) -> None:
            pass

        def isOpened(self) -> bool:
            return False

    monkeypatch.setattr(cv2, 'VideoWriter', BrokenWriter)
    with pytest.raises(SystemExit, match='无法写入'):
        record(str(camera), tmp_path / 's1.mp4', seconds=1, fps=15, show=False)


def test_sharpness_drops_when_blurred():
    img = cv2.cvtColor(sharp(), cv2.COLOR_BGR2GRAY)
    assert sharpness(cv2.GaussianBlur(img, (31, 31), 10)) < 50.0 < sharpness(img)


def test_extract_keeps_sharp_distinct_frames(tmp_path):
    a, b, c = sharp(), sharp(), sharp()
    frames = [a, a, blurred(b), b, b, c]  # 第 2 帧重复，第 3 帧模糊，第 5 帧重复
    video = write_video(tmp_path / 's1.avi', frames)
    counts = extract(video, tmp_path / 'self' / 's1', every=1)
    assert counts == {'frames': 6, 'kept': 3, 'blurry': 1, 'duplicate': 2}
    assert sorted(p.name for p in (tmp_path / 'self' / 's1').iterdir()) == [
        's1_000000.jpg', 's1_000003.jpg', 's1_000005.jpg']


def test_extract_every_nth_frame(tmp_path):
    video = write_video(tmp_path / 's2.avi', [sharp() for _ in range(12)])
    assert extract(video, tmp_path / 'out', every=4)['kept'] == 3


def test_command_line_uses_the_data_folder(tmp_path):
    data = tmp_path / 'data'
    (data / 'videos').mkdir(parents=True)
    write_video(data / 'videos' / 's1.avi', [sharp() for _ in range(24)])
    write_video(data / 'videos' / 's2.avi', [sharp() for _ in range(24)])
    assert extract_main(['--data', str(data), '--every', '12']) == 0
    assert len(list((data / 'self' / 's1').glob('*.jpg'))) == 2
    assert len(list((data / 'self' / 's2').glob('*.jpg'))) == 2


def test_command_line_without_videos_explains(tmp_path, capsys):
    assert extract_main(['--data', str(tmp_path)]) == 1
    assert 'capture_sessions.py' in capsys.readouterr().out
