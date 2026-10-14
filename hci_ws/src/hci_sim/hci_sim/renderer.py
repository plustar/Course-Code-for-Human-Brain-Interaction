"""
渲染：画出机器人头上那台相机看到的画面——把第 3 讲的针孔模型反过来用。

对每个虚拟人：换算到机器人坐标（前方 d、左方 l）-> 方位角 atan2(l, d) 决定画在哪一列，
深度 d 决定人脸有多大（像素高度 = fy × 人脸实际高度 / d）-> 按远到近的顺序贴上头像，近的挡住远的。
相机装在和人脸一样高的位置，所以人脸中心画在画面的垂直中线上。
"""
import math
from typing import Dict, List, Sequence, Tuple

from hci_common.camera_model import CameraModel
from hci_sim.world import Person, Pose2D, relative
import numpy as np

WALL = (205, 210, 215)  # BGR：浅灰色墙面
FLOOR = (150, 160, 170)  # BGR：地面
HORIZON = 0.72  # 墙面与地面的分界线（占画面高度的比例）
NEAR = 0.2  # 比这更近（米）的人不画：已经贴到相机上了
EDGE_MARGIN = 0.2  # 视场边缘外这么多（弧度）以内的人也画：只露出一部分


class Renderer:
    """按相机模型渲染画面。images 是 {头像名: BGR 图像}。"""

    def __init__(self, camera: CameraModel, images: Dict[str, np.ndarray]) -> None:
        self.camera = camera
        self.images = images
        h, w = camera.height, camera.width
        self.background = np.empty((h, w, 3), np.uint8)
        self.background[:] = WALL
        self.background[int(h * HORIZON):] = FLOOR

    def visible(self, pose: Pose2D, people: Sequence[Tuple[Person, float, float]]
                ) -> List[Tuple[Person, float, float]]:
        """视野内的人：[(人, 深度, 方位角)]，按从远到近排好（先画远的）。"""
        out = []
        for person, x, y in people:
            depth, left = relative(pose, x, y)
            if depth < NEAR or person.image not in self.images:
                continue
            bearing = math.atan2(left, depth)
            if self.camera.in_view(bearing, EDGE_MARGIN):
                out.append((person, depth, bearing))
        return sorted(out, key=lambda item: -item[1])

    def render(self, pose: Pose2D, people: Sequence[Tuple[Person, float, float]]) -> np.ndarray:
        """
        渲染一帧。

        pose：机器人位姿；people：[(人, 此刻的 x, 此刻的 y)]（走动的人位置会变）。
        """
        img = self.background.copy()
        for person, depth, bearing in self.visible(pose, people):
            self._paste(img, person, depth, bearing)
        return img

    def _paste(self, img: np.ndarray, person: Person, depth: float, bearing: float) -> None:
        import cv2

        sprite = self.images[person.image]
        face_px = self.camera.pixel_height(depth, person.face_height)
        sh = max(4, int(round(face_px / person.face_ratio)))  # 头像的像素高度
        sw = max(4, int(round(sh * sprite.shape[1] / sprite.shape[0])))
        if sh > 4 * img.shape[0]:  # 太近，头像比画面大好几倍，不必再画
            return
        interp = cv2.INTER_AREA if sh < sprite.shape[0] else cv2.INTER_LINEAR
        scaled = cv2.resize(sprite, (sw, sh), interpolation=interp)
        u, v = self.camera.pixel_u(bearing), self.camera.cy
        x0, y0 = int(round(u - sw / 2.0)), int(round(v - sh / 2.0))
        h, w = img.shape[:2]
        xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + sw, w), min(y0 + sh, h)
        if xb > xa and yb > ya:
            img[ya:yb, xa:xb] = scaled[ya - y0:yb - y0, xa - x0:xb - x0]
