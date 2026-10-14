"""图像话题的 QoS：KEEP_LAST 加小深度；可靠性只能是 reliable 或 best_effort。"""
from hci_common.ros.qos import image_qos
import pytest
from rclpy.qos import HistoryPolicy, ReliabilityPolicy

pytestmark = pytest.mark.ros


def test_reliable_and_keep_last_one_by_default():
    qos = image_qos()
    assert (qos.history, qos.depth) == (HistoryPolicy.KEEP_LAST, 1)
    assert qos.reliability == ReliabilityPolicy.RELIABLE


def test_best_effort_and_depth():
    qos = image_qos('best_effort', depth=5)
    assert qos.reliability == ReliabilityPolicy.BEST_EFFORT and qos.depth == 5


def test_unknown_reliability_is_explained():
    with pytest.raises(ValueError, match='reliable 或 best_effort'):
        image_qos('sensor_data')
