"""
viewer_node：给人看的反馈界面——画框、姓名与置信度，叠加机器人的状态与问候语。

订阅  image_raw（或 image_raw/compressed）与 detections：按 header.stamp 配对
      behavior_state、greeting：取最新的一条，画在底部的状态条上
发布  overlay  sensor_msgs/Image：有人订阅时才发布（没有图形界面时用 rqt_image_view 查看）
窗口  有图形界面时弹窗显示；在窗口里按空格键暂停或恢复机器人（调用 behavior_node/enable 服务）

- 只有识别节点原样复制了图像的 header，图像与检测结果才能配对（否则回调永远不会触发）。
- 他人的脸默认打码（blur_others），演示视频里常会拍到同学。
"""
from dataclasses import dataclass
import math
import os
import time
from typing import Any, Optional, Tuple, Union

from hci_common.identity import is_target
from hci_common.params import param
from hci_common.ros.image_msgs import bgr_to_imgmsg, compressed_to_bgr, imgmsg_to_bgr
from hci_common.ros.params import declare_params
from hci_common.ros.qos import image_qos
from hci_common.ros.runner import run
from hci_interfaces.msg import BehaviorState, DetectionArray
from hci_perception.overlay import Label, Painter, pixelate
import message_filters
import numpy as np
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage, Image
from std_msgs.msg import String
from std_srvs.srv import SetBool

# 状态 -> (中文名, 状态条底色 RGB)
STATE_STYLE = {
    BehaviorState.STOP: ('停车', (180, 60, 60)),
    BehaviorState.SEARCH: ('寻找', (110, 110, 110)),
    BehaviorState.ALIGN: ('对准', (230, 140, 30)),
    BehaviorState.APPROACH: ('靠近', (47, 128, 237)),
    BehaviorState.GREET: ('问候', (39, 174, 96)),
}
SPACE = 32  # 空格键
SYNC_CHECK_PERIOD = 3.0  # 每隔这么多秒检查一次：图像与检测结果配上对了吗


@dataclass
class Params:
    """viewer_node 的参数。"""

    show_window: bool = param(True, '有图形界面时是否弹窗显示')
    use_compressed: bool = param(False, '订阅 image_raw/compressed（JPEG）')
    image_reliability: str = param('reliable', '图像订阅的可靠性：reliable 或 best_effort（同识别节点）')
    slop: float = param(0.2, '图像与检测结果配对时允许的时间差（秒）')
    blur_others: bool = param(True, '给他人的脸打码')
    status_bar: bool = param(True, '在画面底部显示机器人的状态与问候语')
    greeting_seconds: float = param(5.0, '问候语在状态条上显示多久（秒）')
    font_path: str = param('', '中文字体文件；留空自动查找')


class ViewerNode(Node):
    """显示节点：配对、画图、叠加状态；窗口里空格键暂停/恢复机器人。"""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__('viewer_node', **kwargs)
        self.p = declare_params(self, Params)
        self.painter = Painter(self.p.font_path)
        if self.painter.font_file is None:
            self.get_logger().warning('没找到中文字体，中文会显示成方块：sudo apt install '
                                      'fonts-noto-cjk')
        self.show = self.p.show_window
        if self.show and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
            # 没有图形界面时 cv2.imshow 会让进程崩溃：提前关掉窗口，只发布话题
            self.show = False
            self.get_logger().warning('没有图形界面（DISPLAY 为空），不弹窗；可用 rqt_image_view '
                                      '查看 overlay 话题。WSL2 请先执行 wsl --update 启用 WSLg')
        self.state: Optional[BehaviorState] = None
        self.greeting: Tuple[str, float] = ('', 0.0)

        qos = image_qos(self.p.image_reliability, depth=5)  # 配对要在最近几帧里找
        image_type, image_topic = ((CompressedImage, 'image_raw/compressed')
                                   if self.p.use_compressed else (Image, 'image_raw'))
        self.sub_image = message_filters.Subscriber(self, image_type, image_topic,
                                                    qos_profile=qos)
        self.sub_detections = message_filters.Subscriber(self, DetectionArray, 'detections',
                                                         qos_profile=qos)
        self.sync = message_filters.ApproximateTimeSynchronizer(
            [self.sub_image, self.sub_detections], queue_size=10, slop=self.p.slop)
        self.sync.registerCallback(self.on_pair)
        self.create_subscription(BehaviorState, 'behavior_state', self.on_state, 10)
        self.create_subscription(String, 'greeting', self.on_greeting, 10)
        self.enable_client = self.create_client(SetBool, 'behavior_node/enable')
        self.pub = self.create_publisher(Image, 'overlay', 1)
        self.last_pair = time.monotonic()
        self.create_timer(SYNC_CHECK_PERIOD, self.check_sync)

    def on_state(self, msg: BehaviorState) -> None:
        self.state = msg

    def on_greeting(self, msg: String) -> None:
        self.greeting = (msg.data, time.monotonic())

    def on_pair(self, image_msg: Union[Image, CompressedImage],
                detections: DetectionArray) -> None:
        """收到一对图像与检测结果：画好后发布和显示。"""
        self.last_pair = time.monotonic()
        publish = self.pub.get_subscription_count() > 0  # 有人订阅才发布，省 CPU
        if not (self.show or publish):
            return
        bgr = (compressed_to_bgr(image_msg) if self.p.use_compressed
               else imgmsg_to_bgr(image_msg))
        out = self.render(bgr, detections)
        if publish:
            self.pub.publish(bgr_to_imgmsg(out, image_msg.header))
        if self.show:
            self.display(out)

    def render(self, bgr: np.ndarray, detections: DetectionArray) -> np.ndarray:
        """打码、画框与标签、画状态条。"""
        labels = [Label((d.x_min, d.y_min, d.x_max, d.y_max),
                        f'{d.display_name} {d.confidence:.2f}', is_target(d.class_name))
                  for d in detections.detections]
        if self.p.blur_others:
            bgr = pixelate(bgr, [lb.box for lb in labels if not lb.target])
        out = self.painter.draw(bgr, labels)
        if self.p.status_bar and self.state is not None:
            line1, color = self.status_text(self.state)
            text, t = self.greeting
            line2 = text if text and time.monotonic() - t < self.p.greeting_seconds else ''
            out = self.painter.status_bar(out, line1, line2, color)
        return out

    @staticmethod
    def status_text(s: BehaviorState) -> Tuple[str, Tuple[int, int, int]]:
        """状态条的文字与底色，例如"靠近：已对准  目标 张三 2023123456 1.6 m +4°"。"""
        name, color = STATE_STYLE.get(s.state, ('未知', (60, 60, 60)))
        text = f'{name}：{s.reason}'
        if s.target_name and not math.isnan(s.target_distance):
            text += (f'  目标 {s.target_name} {s.target_distance:.1f} m '
                     f'{math.degrees(s.target_bearing):+.0f}°')
        if not s.enabled:
            text += '  （已暂停，按空格键恢复）'
        return text, color

    def display(self, img: np.ndarray) -> None:
        """显示画面；空格键暂停或恢复机器人。"""
        import cv2

        cv2.imshow('HCI Viewer', img)
        if cv2.waitKey(1) & 0xFF == SPACE:
            enabled = self.state.enabled if self.state is not None else True
            self.request_enable(not enabled)

    def request_enable(self, enable: bool) -> None:
        """调用 behavior_node 的 enable 服务（异步，不阻塞画面）。"""
        if not self.enable_client.service_is_ready():
            self.get_logger().warning('behavior_node 还没启动，无法暂停或恢复')
            return
        self.enable_client.call_async(SetBool.Request(data=enable))
        self.get_logger().info('请求恢复机器人' if enable else '请求暂停机器人')

    def check_sync(self) -> None:
        if time.monotonic() - self.last_pair > SYNC_CHECK_PERIOD:
            self.get_logger().warning(
                f'{SYNC_CHECK_PERIOD:.0f} 秒内没有配对成功：检查 recognizer_node 是否在运行、检测消息'
                '是否复制了图像的 header、话题名是否正确（ros2 topic list、ros2 topic hz）')

    def destroy_node(self) -> None:
        """关闭窗口（构造中途失败时还没有 show 属性）。"""
        if getattr(self, 'show', False):
            import cv2

            cv2.destroyAllWindows()
        super().destroy_node()


def main() -> None:
    run(ViewerNode)


if __name__ == '__main__':
    main()
