"""限频器：平均频率不超过上限；摄像头帧率与上限相同时，也不会因为时间抖动漏掉画面。"""
import random

from hci_common.rate import RateLimiter
import pytest


def simulate(fps: float, max_rate: float, seconds: float = 20.0, jitter: float = 0.0) -> float:
    """模拟摄像头按 fps 送来画面，返回实际处理的频率。"""
    limiter, n, t = RateLimiter(max_rate), 0, 0.0
    rnd = random.Random(0)
    while t < seconds:
        now = t + rnd.uniform(-jitter, jitter)
        if limiter.ready(now):
            limiter.mark(now)
            n += 1
        t += 1.0 / fps
    return n / seconds


def test_is_an_upper_bound():
    assert simulate(18, 15) <= 15.2
    assert simulate(30, 25) <= 25.2
    assert simulate(60, 15) <= 15.2


def test_does_not_drop_frames_when_rate_matches_despite_jitter():
    assert simulate(15, 15, jitter=0.008) >= 14.5


def test_processes_every_frame_when_camera_is_slower():
    assert simulate(10, 15) >= 9.9


def test_rejects_non_positive_rate():
    with pytest.raises(ValueError):
        RateLimiter(0.0)
