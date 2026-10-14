"""
针孔相机模型：像素坐标与方位角、目标像素高度与距离之间的换算（第 3 讲"相机成像模型"）。

坐标约定（REP 103）：机体系 x 向前、y 向左、z 向上；角度用弧度，逆时针为正。
所以目标在画面左侧时方位角为正，机器人向左转（角速度为正）才能对准它。

    方位角  bearing  = atan((cx - u) / fx)      u：目标中心的像素横坐标
    深度    depth    = fy * H / h               H：目标实际高度（米）；h：目标的像素高度
    距离    distance = depth / cos(bearing)      相机到目标的直线距离（米）
"""
from dataclasses import dataclass
import math
from typing import Any, List, Optional

# 人脸框对应的实际高度（米）。仿真按它画人脸，识别节点按它估距离：两边用同一个数，
# 仿真里反算出的距离才准（改测学生证的同学改识别节点的 target_height 即可）
FACE_HEIGHT = 0.22


@dataclass(frozen=True)
class CameraModel:
    """一台理想针孔相机：图像尺寸与内参（焦距 fx、fy 和主点 cx、cy，单位都是像素）。"""

    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float

    @classmethod
    def from_hfov(cls, width: int, height: int, hfov_deg: float) -> 'CameraModel':
        """由水平视场角推出内参：没有标定过的摄像头用它近似（正方形像素，主点在画面中心）。"""
        if not 0.0 < hfov_deg < 180.0:
            raise ValueError(f'水平视场角应在 0° 与 180° 之间，收到 {hfov_deg}')
        if width <= 0 or height <= 0:
            raise ValueError(f'图像尺寸必须为正，收到 {width}x{height}')
        f = (width / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)
        return cls(width, height, f, f, width / 2.0, height / 2.0)

    @classmethod
    def from_camera_info(cls, info: Any) -> Optional['CameraModel']:
        """由 sensor_msgs/CameraInfo 构造；没有标定（K 的第一个元素为 0）时返回 None。"""
        k = [float(v) for v in info.k]
        if len(k) != 9 or k[0] <= 0.0 or k[4] <= 0.0 or info.width <= 0 or info.height <= 0:
            return None
        return cls(int(info.width), int(info.height), k[0], k[4], k[2], k[5])

    def k_matrix(self) -> List[float]:
        """3×3 内参矩阵 K，按行展开成 9 个数，用来填写 CameraInfo.k。"""
        return [self.fx, 0.0, self.cx, 0.0, self.fy, self.cy, 0.0, 0.0, 1.0]

    @property
    def hfov_deg(self) -> float:
        """水平视场角（度）。"""
        return math.degrees(2.0 * math.atan(self.width / (2.0 * self.fx)))

    def bearing(self, u: float) -> float:
        """像素横坐标 -> 方位角（弧度，左正）。"""
        return math.atan2(self.cx - u, self.fx)

    def pixel_u(self, bearing: float) -> float:
        """方位角 -> 像素横坐标（bearing 的反函数）。"""
        return self.cx - self.fx * math.tan(bearing)

    def in_view(self, bearing: float, margin: float = 0.0) -> bool:
        """这个方位角在水平视场之内吗？margin（弧度）：视场两边再放宽这么多。"""
        return abs(bearing) < math.radians(self.hfov_deg) / 2.0 + margin

    def depth(self, pixel_height: float, real_height: float) -> float:
        """目标的像素高度 -> 沿光轴的深度（米）；高度不为正时返回 NaN。"""
        if pixel_height <= 0.0 or real_height <= 0.0:
            return math.nan
        return self.fy * real_height / pixel_height

    def pixel_height(self, depth: float, real_height: float) -> float:
        """沿光轴的深度 -> 目标的像素高度（depth 的反函数）。"""
        return self.fy * real_height / depth

    def distance(self, u: float, pixel_height: float, real_height: float) -> float:
        """目标中心横坐标与像素高度 -> 相机到目标的直线距离（米）。"""
        return self.depth(pixel_height, real_height) / math.cos(self.bearing(u))
