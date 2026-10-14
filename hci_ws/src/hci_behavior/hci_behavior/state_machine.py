"""
决策：有限状态机（第 7 讲）。

  STOP      没确认看到本人（看不到人、只看到他人）
  SEARCH    没看到本人时原地慢转寻找（search_turn_rate > 0 时启用）
  ALIGN     看到本人但没对准：原地转向
  APPROACH  已对准且还远：向前靠近，越近越慢
  GREET     到达问候距离：停下问候；人走偏时原地转动，保持面向对方

两处迟滞（进入和离开用不同的阈值），避免在阈值附近来回切换：
  对准阈值：前进中放宽到 2 倍，不会因为一点偏差就停下；
  问候距离：进入 GREET 后，人要退开超过 greet_hysteresis 才重新靠近，也不会反复问候。
方位角左正：目标在左边（bearing > 0）时向左转，角速度为正（ROS 中逆时针为正）。
"""
from dataclasses import dataclass
from enum import IntEnum
import math
from typing import Optional

from hci_behavior.config import BehaviorConfig
from hci_behavior.estimator import Target


class State(IntEnum):
    """五个状态，取值与 hci_interfaces/BehaviorState 里的常量一致。"""

    STOP = 0
    SEARCH = 1
    ALIGN = 2
    APPROACH = 3
    GREET = 4


@dataclass(frozen=True)
class Command:
    """一次决策的结果：状态、原因、期望的线速度与角速度、是否刚进入问候。"""

    state: State
    reason: str
    linear: float
    angular: float
    greet: bool = False


def clamp(value: float, limit: float) -> float:
    """把 value 限制在 [-limit, limit] 之内。"""
    return max(-limit, min(limit, value))


class StateMachine:
    """每个控制周期调用一次 step()。"""

    def __init__(self, config: BehaviorConfig) -> None:
        self.c = config
        self.state = State.STOP

    def step(self, target: Optional[Target], others_seen: bool) -> Command:
        """根据确认过的目标（可能没有）做出决策。"""
        c = self.c
        if target is None:
            if others_seen and c.stop_on_other:
                return self._enter(State.STOP, '只看到他人', 0.0, 0.0)
            if c.search_turn_rate > 0:
                return self._enter(State.SEARCH, '寻找本人', 0.0, c.search_turn_rate)
            return self._enter(State.STOP, '没有确认看到本人', 0.0, 0.0)

        tolerance = math.radians(c.align_tolerance_deg)
        turn = clamp(c.kp_turn * target.bearing, c.max_turn_rate)
        aligned = abs(target.bearing) <= tolerance
        distance = target.distance
        # 迟滞：已经在问候时，人要退开超过 greet_hysteresis 才离开 GREET
        near = c.greet_distance + (c.greet_hysteresis if self.state == State.GREET else 0.0)
        if not math.isnan(distance) and distance <= near:
            return self._enter(State.GREET, '到达问候距离', 0.0, 0.0 if aligned else turn)
        # 迟滞：前进中对准阈值放宽到 2 倍，不会因为一点偏差就停下
        if self.state == State.APPROACH:
            aligned = abs(target.bearing) <= 2.0 * tolerance
        if not aligned:
            return self._enter(State.ALIGN, '转向对准', 0.0, turn)
        if math.isnan(distance):
            return self._enter(State.ALIGN, '估不出距离，只转向不前进', 0.0, turn)
        # 越近越慢：距离为问候距离的 2 倍以上时全速，到达问候距离时降到最小速度
        speed = c.max_speed * (distance - c.greet_distance) / c.greet_distance
        speed = max(c.min_speed, min(c.max_speed, speed))
        return self._enter(State.APPROACH, '靠近', speed, turn)

    def _enter(self, state: State, reason: str, linear: float, angular: float) -> Command:
        greet = state == State.GREET and self.state != State.GREET
        self.state = state
        return Command(state, reason, linear, angular, greet)
