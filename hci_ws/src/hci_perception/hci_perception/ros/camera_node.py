"""
camera_node：从笔记本摄像头或视频文件读取画面，发布图像和相机内参。

发布（相对话题名；launch 把节点放进 /camera 命名空间，于是就是 /camera/image_raw 等）
  image_raw             sensor_msgs/Image（bgr8），header 里是采集时刻
  image_raw/compressed  sensor_msgs/CompressedImage（JPEG），publish_compressed 为 true 时
  camera_info           sensor_msgs/CameraInfo：由 hfov_deg 推出的近似内参，识别节点据此算方位与距离

图像来源的细节（摄像头编号或视频文件、循环播放）在 hci_perception/capture.py。
"""
from dataclasses import dataclass
from typing import Any, Optional

from hci_common.camera_model import CameraModel
from hci_common.params import param, require_positive
from hci_common.ros.image_msgs import bgr_to_compressed, bgr_to_imgmsg, camera_info_msg
from hci_common.ros.params import declare_params
from hci_common.ros.qos import image_qos
from hci_common.ros.runner import run
from hci_perception.capture import FrameSource, VideoSource
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, CompressedImage, Image


@dataclass
class Params:
    """camera_node 的参数。"""

    source: str = param('0', '摄像头编号（0 即 /dev/video0）或视频文件的绝对路径')
    width: int = param(640, '期望的画面宽度（像素），以摄像头实际支持的为准')
    height: int = param(480, '期望的画面高度（像素）')
    fps: float = param(30.0, '摄像头的发布频率（Hz）；视频文件按自身帧率播放')
    fourcc: str = param('MJPG', '摄像头像素格式；MJPG 数据量小，WSL2 转发更稳定；留空则不设置')
    loop_video: bool = param(True, '视频文件播完后是否从头循环')
    hfov_deg: float = param(60.0, '摄像头的水平视场角（度），用来推出内参；笔记本摄像头多在 55–70')
    frame_id: str = param('camera', '写进 header 的坐标系名')
    publish_compressed: bool = param(False, '是否同时发布 JPEG 压缩图像（Wi-Fi 传输时省带宽）')


class CameraNode(Node):
    """读取画面并发布图像与相机内参。source 可以传入替身，测试时不需要真摄像头。"""

    def __init__(self, source: Optional[FrameSource] = None, **kwargs: Any) -> None:
        super().__init__('camera_node', **kwargs)
        self.p = declare_params(self, Params)
        require_positive(self.p, 'fps')
        self.source: FrameSource = source or VideoSource(
            self.p.source, self.p.width, self.p.height, self.p.fourcc, self.p.loop_video)
        self.camera: Optional[CameraModel] = None

        qos = image_qos('reliable')  # Reliable 的发布者能同时匹配两种订阅者
        self.pub_image = self.create_publisher(Image, 'image_raw', qos)
        self.pub_info = self.create_publisher(CameraInfo, 'camera_info', qos)
        self.pub_compressed = None
        if self.p.publish_compressed:
            self.pub_compressed = self.create_publisher(CompressedImage, 'image_raw/compressed',
                                                        qos)

        fps = self.source.native_fps or self.p.fps  # 视频文件按原始帧率播放
        self.timer = self.create_timer(1.0 / fps, self.on_timer)
        self.create_timer(3.0, self.check_topic_conflict)
        self.warned_conflict = False
        w, h = self.source.size
        self.get_logger().info(f'图像源 {self.p.source} 已打开：{w}x{h}，{fps:.0f} 帧/秒 -> '
                               f'{self.pub_image.topic_name}')

    def on_timer(self) -> None:
        """读一帧，连同相机内参一起发布。"""
        frame = self.source.read()
        if frame is None:
            self.get_logger().warning('读取画面失败', throttle_duration_sec=2.0)
            return
        h, w = frame.shape[:2]
        if self.camera is None or (self.camera.width, self.camera.height) != (w, h):
            self.camera = CameraModel.from_hfov(w, h, self.p.hfov_deg)
        msg = bgr_to_imgmsg(frame)
        msg.header.stamp = self.get_clock().now().to_msg()  # 采集时刻：下游据此测延迟、配对
        msg.header.frame_id = self.p.frame_id
        self.pub_image.publish(msg)
        self.pub_info.publish(camera_info_msg(self.camera, msg.header))
        if self.pub_compressed is not None:
            self.pub_compressed.publish(bgr_to_compressed(frame, msg.header))

    def check_topic_conflict(self) -> None:
        """同一个话题上还有别的发布者（例如仿真机器人的相机）时，两路画面会交替出现。"""
        topic = self.pub_image.topic_name
        if not self.warned_conflict and self.count_publishers(topic) > 1:
            self.warned_conflict = True
            self.get_logger().warning(f'还有其他节点也在发布 {topic}，两路画面会交替出现！'
                                      '请检查是不是同时启动了仿真相机或机器人相机')

    def destroy_node(self) -> None:
        """释放摄像头。构造中途失败（例如视频文件不存在）时还没有 source，直接跳过。"""
        source = getattr(self, 'source', None)
        if source is not None:
            source.release()
        super().destroy_node()


def main() -> None:
    run(CameraNode)


if __name__ == '__main__':
    main()
