"""
行为的全部可调参数。

单位一律用 SI（REP 103）：距离用米，角度用弧度，时间用秒，速度用 m/s 和 rad/s；
只有给人调的角度用度，名字带 _deg。所以 yaml 里可以直接写"停在 1.0 m""对准误差 8°"。
"""
from dataclasses import dataclass

from hci_common.params import param


@dataclass
class BehaviorConfig:
    """估计、状态机、安全层共用的参数。"""

    target_class: str = param('', '要找的人的类别名；留空表示任何 stu_ 开头的类别都算本人')
    min_confidence: float = param(0.5, '置信度低于它的检测结果不予理会')
    confirm_window: int = param(5, '防抖：看最近多少帧')
    confirm_min: int = param(3, '防抖：其中至少多少帧看到本人才算确认')
    smoothing: float = param(0.5, '方位与距离的指数平滑系数，0 表示不平滑')
    align_tolerance_deg: float = param(8.0, '方位误差小于它算已对准（度）；前进中放宽到 2 倍')
    kp_turn: float = param(2.0, '转向的比例系数：角速度 = kp_turn × 方位角')
    max_turn_rate: float = param(0.6, '最大角速度（rad/s）')
    max_speed: float = param(0.2, '最大线速度（m/s）；接近人时研究建议约 0.2')
    min_speed: float = param(0.05, '靠近时的最小线速度（m/s），避免停在半路')
    greet_distance: float = param(1.0, '到达这个距离（米）就停下问候；研究建议 0.8–1.0')
    greet_hysteresis: float = param(0.2, '问候后，人退开超过这么多（米）才重新靠近')
    min_distance: float = param(0.5, '安全：目标比这个距离（米）还近时绝不前进')
    watchdog_timeout: float = param(0.5, '安全：超过这么多秒没收到检测结果就停车')
    search_turn_rate: float = param(0.0, '没看到本人时原地慢转寻找的角速度（rad/s），0 表示不找')
    stop_on_other: bool = param(True, '只看到他人时停车并说明原因')

    def __post_init__(self) -> None:
        """参数之间要相容：自相矛盾时启动就说明，而不是机器人默默地不动。"""
        problems = []
        if not 1 <= self.confirm_min <= self.confirm_window:
            problems.append(f'confirm_min（{self.confirm_min}）要在 1 和 confirm_window'
                            f'（{self.confirm_window}）之间，否则永远确认不了目标')
        if not self.greet_distance > 0:
            problems.append(f'greet_distance 必须大于 0，收到 {self.greet_distance}')
        elif not 0 <= self.min_distance < self.greet_distance:
            problems.append(f'min_distance（{self.min_distance}）要小于 greet_distance'
                            f'（{self.greet_distance}），否则走不到问候距离就被安全层拦下')
        if not 0 <= self.smoothing < 1:
            problems.append(f'smoothing 要在 0 和 1 之间（不含 1），收到 {self.smoothing}')
        if not 0 <= self.min_confidence <= 1:
            problems.append(f'min_confidence 要在 0 和 1 之间，收到 {self.min_confidence}')
        if not self.watchdog_timeout > 0:
            problems.append(f'watchdog_timeout 必须大于 0，收到 {self.watchdog_timeout}')
        if problems:
            raise ValueError('行为参数有误：' + '；'.join(problems))
