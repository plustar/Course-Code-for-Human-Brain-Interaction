"""行为参数之间要相容：自相矛盾时启动就说明原因，而不是机器人默默地不动。"""
from hci_behavior.config import BehaviorConfig
import pytest


def test_the_defaults_are_consistent():
    BehaviorConfig()


@pytest.mark.parametrize('changes, hint', [
    ({'confirm_min': 6}, 'confirm_min'),  # 5 帧里要 6 帧看到：永远确认不了
    ({'confirm_min': 0}, 'confirm_min'),
    ({'min_distance': 1.2}, 'min_distance'),  # 比问候距离还远：走不到问候距离
    ({'greet_distance': 0.0}, 'greet_distance'),
    ({'smoothing': 1.0}, 'smoothing'),  # 1 表示永远用旧值
    ({'min_confidence': 1.5}, 'min_confidence'),
    ({'watchdog_timeout': 0.0}, 'watchdog_timeout'),
])
def test_contradictory_settings_are_explained(changes, hint):
    with pytest.raises(ValueError, match=hint):
        BehaviorConfig(**changes)
