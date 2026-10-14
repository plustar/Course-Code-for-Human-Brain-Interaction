"""估计：挑出要找的人、多帧确认（防抖）、指数平滑、丢失后清空。"""
import math
from typing import Sequence

from hci_behavior.config import BehaviorConfig
from hci_behavior.estimator import Observation, TargetEstimator
import pytest


def me(bearing: float = 0.0, distance: float = 2.0, confidence: float = 0.9,
       class_name: str = 'stu_2023123456') -> Observation:
    return Observation(class_name, '张三 2023123456', confidence, bearing, distance)


OTHER = Observation('face', '他人', 0.95, 0.3, 1.0)


def feed(est: TargetEstimator, frame: Sequence[Observation], n: int, t: float = 0.0) -> float:
    """连续 n 帧都看到 frame（每帧间隔 0.1 秒），返回最后的时刻。"""
    for _ in range(n):
        t += 0.1
        est.update(frame, now=t, stamp=t - 0.05)
    return t


def test_target_is_confirmed_after_3_of_5_frames():
    est = TargetEstimator(BehaviorConfig())
    feed(est, [me()], 2)
    assert est.target() is None  # 只看到 2 帧：可能是误检
    feed(est, [me()], 1)
    target = est.target()
    assert target is not None and target.name == '张三 2023123456' and target.distance == 2.0


def test_short_dropouts_do_not_lose_the_target():
    est = TargetEstimator(BehaviorConfig())
    feed(est, [me()], 5)
    feed(est, [], 2)  # 漏检 2 帧：最近 5 帧里还有 3 帧看到
    assert est.target() is not None
    feed(est, [], 1)
    assert est.target() is None


def test_losing_the_target_clears_its_position():
    est = TargetEstimator(BehaviorConfig())
    feed(est, [me(bearing=0.3)], 5)
    feed(est, [], 5)
    assert est.bearing is None and math.isnan(est.distance)
    feed(est, [me(bearing=-0.2)], 3)  # 重新出现：不和旧位置平均
    assert est.target().bearing == pytest.approx(-0.2)


def test_picks_the_most_confident_target_and_ignores_weak_ones():
    est = TargetEstimator(BehaviorConfig(smoothing=0.0))
    feed(est, [me(bearing=0.1, confidence=0.6), me(bearing=-0.1, confidence=0.9),
               me(bearing=0.5, confidence=0.3)], 3)
    assert est.target().bearing == pytest.approx(-0.1)


def test_keeps_following_the_same_person_when_confidences_swap():
    est = TargetEstimator(BehaviorConfig(smoothing=0.0, target_class='face'))
    left, right = 0.4, -0.4
    for i in range(10):  # 两张脸的置信度轮流领先：仍然跟着一开始的那个人
        high, low = (left, right) if i % 2 == 0 else (right, left)
        feed(est, [me(bearing=high, confidence=0.9, class_name='face'),
                   me(bearing=low, confidence=0.6, class_name='face')], 1)
        assert est.bearing == pytest.approx(left)


def test_others_are_noticed_but_never_followed():
    est = TargetEstimator(BehaviorConfig())
    feed(est, [OTHER], 5)
    assert est.target() is None and est.others_seen
    feed(est, [me()], 1)
    assert not est.others_seen  # 只看最近一帧


def test_target_class_restricts_who_counts():
    est = TargetEstimator(BehaviorConfig(target_class='stu_2023000001'))
    feed(est, [me(class_name='stu_2023123456')], 5)  # 别的同学
    assert est.target() is None and est.others_seen


def test_exponential_smoothing():
    est = TargetEstimator(BehaviorConfig(smoothing=0.5))
    feed(est, [me(bearing=0.0, distance=2.0)], 3)
    feed(est, [me(bearing=0.2, distance=1.0)], 1)
    target = est.target()
    assert target.bearing == pytest.approx(0.1) and target.distance == pytest.approx(1.5)


def test_unknown_distance_keeps_the_last_estimate():
    est = TargetEstimator(BehaviorConfig(smoothing=0.0))
    feed(est, [me(distance=2.0)], 3)
    feed(est, [me(distance=math.nan)], 1)
    assert est.target().distance == 2.0


def test_age_and_stamp_for_watchdog_and_latency():
    est = TargetEstimator(BehaviorConfig())
    assert est.age(1.0) == math.inf  # 从没收到过检测结果
    t = feed(est, [me()], 3)
    assert est.age(t + 0.3) == pytest.approx(0.3)
    assert est.target().stamp == pytest.approx(t - 0.05)  # 图像的采集时刻
