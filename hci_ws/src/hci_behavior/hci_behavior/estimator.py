"""
估计：从每一帧的检测结果里挑出要找的人，防抖、平滑，给出"确认过的目标"。

  挑选  画面里有几个候选时，已经在跟的人优先（方位与上一次最接近），不会在两人之间来回跳；
        还没在跟谁时选置信度最高的
  防抖  最近 confirm_window 帧中至少 confirm_min 帧看到本人，才算确认（如 5 帧中 3 帧）
  平滑  方位与距离做指数平滑：新值 = smoothing × 旧值 + (1 − smoothing) × 本帧
  丢失  最近几帧都没看到本人，就清空旧的方位与距离
"""
from collections import deque
from dataclasses import dataclass
import math
from typing import Deque, Optional, Sequence

from hci_behavior.config import BehaviorConfig
from hci_common.identity import is_target


@dataclass(frozen=True)
class Observation:
    """一个检测结果里行为关心的部分（由 DetectionArray 消息转换而来）。"""

    class_name: str
    display_name: str
    confidence: float
    bearing: float  # 方位角（弧度，左正）
    distance: float  # 直线距离（米），估不出时为 NaN


@dataclass(frozen=True)
class Target:
    """确认过的目标。"""

    name: str  # 显示名，如"张三 2023123456"
    bearing: float  # 平滑后的方位角（弧度）
    distance: float  # 平滑后的距离（米），可能为 NaN
    stamp: float  # 最近一次看到它的那帧图像的采集时刻（秒），用来算延迟


class TargetEstimator:
    """每收到一帧检测结果调用 update()；控制周期里用 target() 取确认过的目标。"""

    def __init__(self, config: BehaviorConfig) -> None:
        self.c = config
        self.history: Deque[bool] = deque(maxlen=config.confirm_window)
        self.bearing: Optional[float] = None
        self.distance = math.nan
        self.name = ''
        self.stamp = math.nan
        self.others_seen = False  # 最近一帧里有没有他人
        self.last_update: Optional[float] = None

    def update(self, observations: Sequence[Observation], now: float, stamp: float) -> None:
        """收到一帧检测结果。now：收到的时刻；stamp：这帧图像的采集时刻。"""
        self.last_update = now
        valid = [o for o in observations if o.confidence >= self.c.min_confidence]
        targets = [o for o in valid if is_target(o.class_name, self.c.target_class)]
        self.others_seen = any(not is_target(o.class_name, self.c.target_class) for o in valid)
        self.history.append(bool(targets))
        if targets:
            best = self._pick(targets)
            self.bearing = self._smooth(self.bearing, best.bearing)
            if not math.isnan(best.distance):
                previous = None if math.isnan(self.distance) else self.distance
                self.distance = self._smooth(previous, best.distance)
            self.name = best.display_name or best.class_name
            self.stamp = stamp
        if not any(self.history):  # 最近几帧都没看到本人：丢弃旧位置
            self.bearing, self.distance = None, math.nan

    def _pick(self, targets: Sequence[Observation]) -> Observation:
        if self.bearing is None:  # 还没在跟谁：选置信度最高的那个
            return max(targets, key=lambda o: o.confidence)
        last = self.bearing
        # 已经在跟谁：选方位与上一次最接近的，两人同时在画面里也不会来回跳
        return min(targets, key=lambda o: abs(o.bearing - last))

    def _smooth(self, old: Optional[float], new: float) -> float:
        a = self.c.smoothing  # 平滑系数 ∈ [0, 1)：越大越稳、也越滞后
        # 指数平滑：新估计 = a×旧 + (1−a)×本帧；第一次没有旧值，直接用本帧
        return new if old is None else a * old + (1.0 - a) * new

    def target(self) -> Optional[Target]:
        """确认过的目标；没有确认时返回 None。"""
        if sum(self.history) >= self.c.confirm_min and self.bearing is not None:
            return Target(self.name, self.bearing, self.distance, self.stamp)
        return None

    def age(self, now: float) -> float:
        """距离上一次收到检测结果过了多少秒；从没收到过时为无穷大。"""
        return math.inf if self.last_update is None else now - self.last_update
