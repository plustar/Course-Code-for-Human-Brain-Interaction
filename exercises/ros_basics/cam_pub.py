"""
练习 2-⑥：把摄像头（或视频文件）的画面发布到 /camera/image_raw。

运行：python3 cam_pub.py --source 0
      python3 cam_pub.py --source /绝对路径/me.mp4      # WSL2 摄像头打不开时
验证：ros2 topic hz /camera/image_raw；rqt_image_view 里选择这个话题

摄像头设成 MJPG、640×480（与练习 4 的 camera_node 相同）：默认的 YUYV 不压缩，数据量大好几倍，
WSL2 经 usbipd 转发时画面会发绿、只有上面一部分。
"""
import argparse
import array
from typing import Any, List, Optional

import cv2
import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import Image


def to_msg(frame: np.ndarray, stamp: Any) -> Image:
    """BGR 数组 -> sensor_msgs/Image（与 cv_bridge 的 cv2_to_imgmsg 等价）。"""
    msg = Image()
    msg.header.stamp, msg.header.frame_id = stamp, 'camera'
    msg.height, msg.width = frame.shape[:2]
    msg.encoding, msg.step = 'bgr8', frame.shape[1] * 3
    msg.data = array.array('B', frame.tobytes())
    return msg


def open_source(source: str) -> Any:
    """打开摄像头（编号，设成 MJPG、640×480）或视频文件，返回 cv2.VideoCapture。"""
    if not source.isdigit():
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            raise RuntimeError(f'打不开视频文件 {source}（要写绝对路径）')
        return cap
    cap = cv2.VideoCapture(int(source))
    if not cap.isOpened():
        raise RuntimeError(f'打不开摄像头 {source}：WSL2 要先用 usbipd 把摄像头转发进来'
                           '（README 第 4.7 节），没有权限时把自己加入 video 组')
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    return cap


class CamPub(Node):
    """读取画面并发布。"""

    def __init__(self, source: str, fps: float) -> None:
        super().__init__('cam_pub')
        self.cap = open_source(source)
        self.is_file = not source.isdigit()
        if fps <= 0:  # 默认：摄像头 30 帧/秒，视频文件按它自己的帧率
            fps = (self.cap.get(cv2.CAP_PROP_FPS) if self.is_file else 0) or 30.0
        self.pub = self.create_publisher(Image, '/camera/image_raw', 1)
        self.create_timer(1.0 / fps, self.on_timer)
        self.get_logger().info(f'{source} -> /camera/image_raw，{fps:.0f} 帧/秒')

    def on_timer(self) -> None:
        ok, frame = self.cap.read()
        if not ok and self.is_file:  # 视频播完从头循环
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
        if ok:
            self.pub.publish(to_msg(frame, self.get_clock().now().to_msg()))


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description='把摄像头或视频文件的画面发布到 /camera/image_raw')
    ap.add_argument('--source', default='0')
    ap.add_argument('--fps', type=float, default=0,
                    help='发布频率；默认摄像头 30，视频文件用它自己的帧率')
    a = ap.parse_args(argv)
    rclpy.init()
    node = CamPub(a.source, a.fps)
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):  # Ctrl+C
        pass
    finally:
        node.cap.release()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
