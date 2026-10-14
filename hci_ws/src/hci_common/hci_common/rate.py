"""限制处理频率：让处理频率平均不超过上限，又不因为摄像头的时间抖动漏掉画面。"""


class RateLimiter:
    """
    按"时间表"放行的限频器。

    每处理一帧，下一次允许的时刻就往后推 1/max_rate 秒。画面比预定时刻早到不超过
    tolerance（默认 20% 个周期）也放行，所以摄像头帧率与 max_rate 相同时，
    不会因为一点抖动就漏掉一半画面。用法::

        if limiter.ready(now):
            limiter.mark(now)
            ...处理这一帧...
    """

    def __init__(self, max_rate: float, tolerance: float = 0.2) -> None:
        if max_rate <= 0:
            raise ValueError(f'max_rate 必须大于 0，收到 {max_rate}')
        self.interval = 1.0 / max_rate
        self.tol = tolerance * self.interval
        self.next_time = float('-inf')

    def ready(self, now: float) -> bool:
        """现在可以处理一帧吗？"""
        return now >= self.next_time - self.tol

    def mark(self, now: float) -> None:
        """处理了一帧：把下一次允许的时刻往后推一个周期。"""
        self.next_time = max(self.next_time, now - self.tol) + self.interval
