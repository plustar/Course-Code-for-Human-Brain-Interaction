"""
安全：状态机之后的最后一道关。不管上面怎么决策，下面五条规则一定成立（第 7 讲、第 8 讲）。

  1. 暂停（~/enable 服务设为 false）时停车
  2. 看门狗：超过 watchdog_timeout 秒没收到检测结果就停车
  3. 只有 APPROACH 状态可以前进，任何时候都不后退
  4. 目标比 min_distance 还近时绝不前进
  5. 线速度、角速度不超过上限

注意：这里的暂停只是软件层面的。真机的急停必须独立于软件（例如 TurtleBot 4 底盘自带的
急停），不能依赖这个节点还在正常运行。
"""
from dataclasses import replace
import math

from hci_behavior.config import BehaviorConfig
from hci_behavior.state_machine import clamp, Command, State


class SafetyFilter:
    """check() 把状态机的决策变成一定安全的速度指令。"""

    def __init__(self, config: BehaviorConfig) -> None:
        self.c = config

    def check(self, cmd: Command, data_age: float, enabled: bool,
              target_distance: float = math.nan) -> Command:
        """
        检查一次决策。

        data_age：距离上一次收到检测结果的秒数；enabled：是否没有被暂停；
        target_distance：目标的距离（米），没有目标时为 NaN。
        """
        if not enabled:
            return Command(State.STOP, '已暂停（~/enable）', 0.0, 0.0)
        if data_age > self.c.watchdog_timeout:
            return Command(State.STOP, '看门狗：检测结果超时', 0.0, 0.0)
        linear = max(0.0, cmd.linear) if cmd.state == State.APPROACH else 0.0
        reason = cmd.reason
        if linear > 0.0 and not math.isnan(target_distance) \
                and target_distance < self.c.min_distance:
            linear, reason = 0.0, f'{reason}（太近，不再前进）'
        return replace(cmd, reason=reason, linear=min(linear, self.c.max_speed),
                       angular=clamp(cmd.angular, self.c.max_turn_rate))
