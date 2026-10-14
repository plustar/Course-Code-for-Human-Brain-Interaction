"""
安全：状态机之后的最后一道关。

五条规则用属性测试检查：hypothesis 每条随机生成 1000 组输入（状态、速度、数据新旧、
是否暂停、目标距离），找不到一个反例才算通过。第 8 讲"测试方法"可以直接拿它举例。
"""
import math

from hci_behavior.config import BehaviorConfig
from hci_behavior.estimator import Observation, TargetEstimator
from hci_behavior.safety import SafetyFilter
from hci_behavior.state_machine import Command, State, StateMachine
from hypothesis import given, settings
from hypothesis import strategies as st

CONFIG = BehaviorConfig()
SAFETY = SafetyFilter(CONFIG)

commands = st.builds(Command, st.sampled_from(State), st.just('决策'),
                     st.floats(-5.0, 5.0), st.floats(-5.0, 5.0), st.booleans())
ages = st.floats(0.0, 2.0)  # 距离上一次收到检测结果的秒数
distances = st.one_of(st.just(math.nan), st.floats(0.0, 10.0))


@settings(max_examples=1000, deadline=None)
@given(commands, ages, st.booleans(), distances)
def test_never_reverses_and_never_exceeds_the_speed_limit(cmd, age, enabled, distance):
    out = SAFETY.check(cmd, age, enabled, distance)
    assert 0.0 <= out.linear <= CONFIG.max_speed
    assert abs(out.angular) <= CONFIG.max_turn_rate


@settings(max_examples=1000, deadline=None)
@given(commands, ages, st.booleans(), distances)
def test_only_approach_moves_forward(cmd, age, enabled, distance):
    out = SAFETY.check(cmd, age, enabled, distance)
    assert out.linear == 0.0 or out.state == State.APPROACH


@settings(max_examples=1000, deadline=None)
@given(commands, ages, st.booleans(), st.floats(0.0, CONFIG.min_distance, exclude_max=True))
def test_never_moves_forward_when_closer_than_min_distance(cmd, age, enabled, distance):
    assert SAFETY.check(cmd, age, enabled, distance).linear == 0.0


@settings(max_examples=1000, deadline=None)
@given(commands, st.floats(CONFIG.watchdog_timeout, 100.0, exclude_min=True), st.booleans(),
       distances)
def test_watchdog_stops_when_detections_are_stale(cmd, age, enabled, distance):
    out = SAFETY.check(cmd, age, enabled, distance)
    assert (out.state, out.linear, out.angular) == (State.STOP, 0.0, 0.0)


@settings(max_examples=1000, deadline=None)
@given(commands, ages, distances)
def test_pause_always_stops(cmd, age, distance):
    out = SAFETY.check(cmd, age, False, distance)
    assert (out.state, out.linear, out.angular) == (State.STOP, 0.0, 0.0)
    assert '暂停' in out.reason


def test_reasons_explain_each_override():
    approach = Command(State.APPROACH, '靠近', 0.2, 0.1)
    assert '看门狗' in SAFETY.check(approach, 1.0, True).reason
    too_close = SAFETY.check(approach, 0.1, True, target_distance=0.4)
    assert too_close.linear == 0.0 and too_close.angular == 0.1 and '太近' in too_close.reason
    assert SAFETY.check(approach, 0.1, True, target_distance=2.0) == approach  # 正常情况原样放行


observations = st.lists(st.builds(
    Observation, st.sampled_from(['stu_2023123456', 'face']), st.just('某人'),
    st.floats(0.0, 1.0), st.floats(-1.5, 1.5), st.one_of(st.just(math.nan), st.floats(0.1, 6.0))),
    max_size=3)


@settings(max_examples=300, deadline=None)
@given(st.lists(st.tuples(observations, st.floats(0.0, 0.8), st.booleans()), min_size=1,
                max_size=40))
def test_the_whole_pipeline_stays_safe(frames):
    """估计 -> 状态机 -> 安全层串起来，随机的检测序列下每个周期的输出都满足安全规则。"""
    estimator, machine = TargetEstimator(CONFIG), StateMachine(CONFIG)
    t = 0.0
    for frame, delay, enabled in frames:
        t += delay
        estimator.update(frame, now=t, stamp=t)
        target = estimator.target()
        cmd = machine.step(target, estimator.others_seen)
        distance = target.distance if target else math.nan
        out = SAFETY.check(cmd, estimator.age(t + 0.1), enabled, distance)
        assert 0.0 <= out.linear <= CONFIG.max_speed and abs(out.angular) <= CONFIG.max_turn_rate
        assert out.linear == 0.0 or (out.state == State.APPROACH and enabled)
        if not math.isnan(distance) and distance < CONFIG.min_distance:
            assert out.linear == 0.0
