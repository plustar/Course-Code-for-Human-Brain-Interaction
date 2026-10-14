"""决策：五个状态的转移、越近越慢、问候只触发一次、距离与方位的两处迟滞。"""
import math
from typing import Any, Optional

from hci_behavior.config import BehaviorConfig
from hci_behavior.estimator import Target
from hci_behavior.state_machine import clamp, State, StateMachine
from hci_interfaces.msg import BehaviorState
import pytest

CONFIG = BehaviorConfig()  # 问候距离 1.0 m、对准误差 8°、最大 0.2 m/s 与 0.6 rad/s


def person(bearing_deg: float = 0.0, distance: float = 3.0) -> Target:
    return Target('张三 2023123456', math.radians(bearing_deg), distance, stamp=0.0)


def machine(state: Optional[State] = None, **overrides: Any) -> StateMachine:
    m = StateMachine(BehaviorConfig(**overrides))
    if state is not None:
        m.state = state
    return m


def test_stops_without_a_confirmed_target():
    cmd = machine().step(None, others_seen=False)
    assert (cmd.state, cmd.linear, cmd.angular) == (State.STOP, 0.0, 0.0)
    assert cmd.reason == '没有确认看到本人'


def test_only_others_in_view_stops_with_a_reason():
    cmd = machine(search_turn_rate=0.3).step(None, others_seen=True)
    assert cmd.state == State.STOP and cmd.reason == '只看到他人'


def test_searches_in_place_when_enabled():
    cmd = machine(search_turn_rate=0.3).step(None, others_seen=False)
    assert (cmd.state, cmd.linear, cmd.angular) == (State.SEARCH, 0.0, 0.3)
    cmd = machine(search_turn_rate=0.3, stop_on_other=False).step(None, others_seen=True)
    assert cmd.state == State.SEARCH


@pytest.mark.parametrize('bearing_deg, sign', [(20.0, 1), (-20.0, -1)], ids=['left', 'right'])
def test_turns_toward_the_person(bearing_deg, sign):
    cmd = machine().step(person(bearing_deg), others_seen=False)
    assert cmd.state == State.ALIGN and cmd.linear == 0.0
    assert sign * cmd.angular > 0  # 人在左边（方位为正）就向左转（角速度为正）
    assert cmd.angular == pytest.approx(sign * min(2.0 * math.radians(20.0), 0.6))


def test_turn_rate_is_limited():
    cmd = machine().step(person(80.0), others_seen=False)
    assert cmd.angular == CONFIG.max_turn_rate


def test_approaches_at_full_speed_when_far_and_aligned():
    cmd = machine().step(person(2.0, distance=3.0), others_seen=False)
    assert cmd.state == State.APPROACH and cmd.linear == CONFIG.max_speed
    assert cmd.angular == pytest.approx(2.0 * math.radians(2.0))  # 边走边微调方向


def test_slows_down_near_the_person():
    m = machine()
    speeds = [m.step(person(0.0, d), others_seen=False).linear for d in (3.0, 2.0, 1.5, 1.2, 1.05)]
    assert speeds == sorted(speeds, reverse=True)
    assert speeds[2] == pytest.approx(0.1)  # 1.5 m：最大速度的一半
    assert speeds[-1] == CONFIG.min_speed  # 快到时不低于最小速度，不会停在半路


def test_greets_once_at_the_greet_distance():
    m = machine()
    first, second = (m.step(person(0.0, 0.95), others_seen=False) for _ in range(2))
    assert first.state == second.state == State.GREET
    assert first.greet and not second.greet and first.linear == second.linear == 0.0


def test_keeps_facing_the_person_while_greeting():
    m = machine()
    off = m.step(person(15.0, 0.9), others_seen=False)
    assert off.state == State.GREET and off.linear == 0.0 and off.angular > 0.0
    aligned = m.step(person(3.0, 0.9), others_seen=False)
    assert aligned.state == State.GREET and aligned.angular == 0.0


def test_greet_distance_hysteresis():
    m = machine()
    assert m.step(person(0.0, 1.0), others_seen=False).state == State.GREET
    stay = m.step(person(0.0, 1.15), others_seen=False)  # 人稍微退开：仍在问候
    assert stay.state == State.GREET and not stay.greet
    assert m.step(person(0.0, 1.25), others_seen=False).state == State.APPROACH  # 退开 0.2 m 以上
    again = m.step(person(0.0, 1.0), others_seen=False)
    assert again.state == State.GREET and again.greet  # 重新靠近后再问候一次


def test_no_flicker_when_distance_jitters_around_the_threshold():
    m = machine()
    greets = 0
    for i in range(20):
        cmd = m.step(person(0.0, 1.0 + (0.08 if i % 2 else -0.02)), others_seen=False)
        assert cmd.state == State.GREET
        greets += cmd.greet
    assert greets == 1


def test_alignment_hysteresis_while_approaching():
    assert machine(State.APPROACH).step(person(12.0), others_seen=False).state == State.APPROACH
    assert machine(State.ALIGN).step(person(12.0), others_seen=False).state == State.ALIGN
    assert machine(State.APPROACH).step(person(17.0), others_seen=False).state == State.ALIGN


def test_unknown_distance_only_turns():
    cmd = machine().step(person(0.0, math.nan), others_seen=False)
    assert cmd.state == State.ALIGN and cmd.linear == 0.0 and '估不出距离' in cmd.reason


def test_state_values_match_the_message_constants():
    for state in State:
        assert getattr(BehaviorState, state.name) == state.value


def test_clamp():
    assert clamp(2.0, 0.5) == 0.5 and clamp(-2.0, 0.5) == -0.5 and clamp(0.1, 0.5) == 0.1
