"""
recognizer_node：订阅图像，认出画面里的人，发布带方位角和距离的检测结果。

订阅  image_raw（use_compressed 为 true 时订阅 image_raw/compressed）、camera_info
发布  detections  hci_interfaces/DetectionArray（header 原样复制自图像）

关键设计（第 6 讲）
1. 只处理最新一帧：图像订阅用 KEEP_LAST + 深度 1。推理比摄像头慢时，没来得及处理的
   旧画面被新画面覆盖，节点每次拿到的都是最新一帧，延迟不会越积越大。可靠性默认 Reliable，
   订阅机器人的相机时按平台设置（launch 自动选择），原因见 hci_common/ros/qos.py。
2. 限制推理频率（max_rate，平均不超过它）：画面来得太快时直接跳过，跳过的帧不解码。
3. 检测消息的 header 原样复制自图像：显示节点靠它配对，ros2 topic delay 靠它算延迟。
4. 方位与距离：按 camera_info 的内参用针孔模型算出（第 3 讲）；没收到内参时按 hfov_deg 近似。
识别后端（YOLO 的 ONNX、YuNet、两步法）见 hci_perception/recognition。
"""
from dataclasses import dataclass
import time
from typing import Any, List, Optional

from hci_common.camera_model import CameraModel, FACE_HEIGHT
from hci_common.identity import display_name, parse_id_map
from hci_common.params import param
from hci_common.rate import RateLimiter
from hci_common.ros.image_msgs import compressed_to_bgr, imgmsg_to_bgr
from hci_common.ros.params import declare_params
from hci_common.ros.qos import image_qos
from hci_common.ros.runner import run
from hci_interfaces.msg import Detection as DetectionMsg
from hci_interfaces.msg import DetectionArray
from hci_perception.recognition.base import Detection, Recognizer
from hci_perception.recognition.factory import create_recognizer
import numpy as np
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, CompressedImage, Image
from std_msgs.msg import Header

REPORT_PERIOD = 5.0  # 每隔这么多秒报告一次推理帧率（收不到图像时提醒）


@dataclass
class Params:
    """recognizer_node 的参数。"""

    model: str = param('', '练习 3 导出的 best.onnx（绝对路径）；留空则用 YuNet 演示模式')
    gallery: str = param('', '两步法的登记文件（sface_verify.py enroll 生成的 .npy）；'
                             '设置后改用 YuNet 检测 + SFace 比对')
    identity: str = param('', '两步法比对成功时使用的类别名，如 stu_2023123456')
    min_confidence: float = param(0.5, '置信度低于它的检测结果丢掉')
    iou_threshold: float = param(0.5, 'NMS 的重叠阈值：同一张脸重叠的框只留一个')
    imgsz: int = param(416, '推理尺寸，与训练时一致；固定尺寸的 .onnx 自动使用导出时的尺寸')
    max_rate: float = param(15.0, '推理频率上限（Hz）')
    use_compressed: bool = param(False, '订阅 image_raw/compressed（JPEG），Wi-Fi 下省带宽')
    image_reliability: str = param('reliable', '图像订阅的可靠性：reliable，或 best_effort'
                                               '（机器人的相机话题用 Best Effort 发布时）')
    id_map: List[str] = param(['stu_2023123456=张三'], '学号与姓名的对应，多人写多项')
    target_height: float = param(FACE_HEIGHT, '目标的实际高度（米）：人脸约 0.22；改测学生证时填卡片高度')
    hfov_deg: float = param(60.0, '没有收到 camera_info 时，按这个水平视场角（度）估计内参')


class RecognizerNode(Node):
    """识别节点。recognizer 可以传入替身，测试时不需要真模型。"""

    def __init__(self, recognizer: Optional[Recognizer] = None, **kwargs: Any) -> None:
        super().__init__('recognizer_node', **kwargs)
        self.p = declare_params(self, Params)
        self.id_map = parse_id_map(self.p.id_map)
        self.recognizer = recognizer or create_recognizer(
            self.p.model, self.p.min_confidence, self.p.imgsz, self.p.iou_threshold,
            gallery=self.p.gallery, identity=self.p.identity)
        self.get_logger().info(f'识别后端：{self.recognizer.backend}')
        self.limiter = RateLimiter(self.p.max_rate)
        self.camera_info: Optional[CameraModel] = None
        self.reset_stats()

        # 图像"最新的最重要"：KEEP_LAST + 深度 1；内参与图像来自同一个相机，QoS 相同
        qos = image_qos(self.p.image_reliability, depth=1)
        if self.p.use_compressed:
            self.create_subscription(CompressedImage, 'image_raw/compressed', self.on_compressed,
                                     qos)
        else:
            self.create_subscription(Image, 'image_raw', self.on_image, qos)
        self.create_subscription(CameraInfo, 'camera_info', self.on_camera_info, qos)
        self.pub = self.create_publisher(DetectionArray, 'detections', 10)
        self.create_timer(REPORT_PERIOD, self.report)

    # ---------- 收消息 ----------
    def on_camera_info(self, msg: CameraInfo) -> None:
        self.camera_info = CameraModel.from_camera_info(msg)

    def on_image(self, msg: Image) -> None:
        if self.limiter.ready(time.monotonic()):  # 先判断再解码，跳过的帧不花 CPU
            self.process(msg.header, imgmsg_to_bgr(msg))

    def on_compressed(self, msg: CompressedImage) -> None:
        if self.limiter.ready(time.monotonic()):
            self.process(msg.header, compressed_to_bgr(msg))

    # ---------- 识别并发布 ----------
    def process(self, header: Header, bgr: np.ndarray) -> None:
        """识别一帧，算出每个目标的方位与距离，发布检测结果。"""
        t0 = time.monotonic()
        self.limiter.mark(t0)
        detections = self.recognizer.detect(bgr)
        self.infer_seconds += time.monotonic() - t0
        self.frames += 1

        h, w = bgr.shape[:2]
        camera = self.camera_for(w, h)
        out = DetectionArray()
        out.header = header  # 关键：原样复制图像的 header
        out.image_width, out.image_height = int(w), int(h)
        out.detections = [self.to_msg(d, camera) for d in detections]
        self.pub.publish(out)

    def camera_for(self, w: int, h: int) -> CameraModel:
        """优先用 camera_info 的内参；没有收到或尺寸对不上时按 hfov_deg 近似。"""
        info = self.camera_info
        if info is not None and (info.width, info.height) == (w, h):
            return info
        return CameraModel.from_hfov(w, h, self.p.hfov_deg)

    def to_msg(self, d: Detection, camera: CameraModel) -> DetectionMsg:
        """一个检测结果 -> 消息，附上方位角与距离。"""
        m = DetectionMsg()
        m.class_name, m.confidence = d.class_name, float(d.confidence)
        m.display_name = display_name(d.class_name, self.id_map)
        m.x_min, m.y_min, m.x_max, m.y_max = d.x1, d.y1, d.x2, d.y2
        m.bearing = float(camera.bearing(d.center_x))
        m.distance = float(camera.distance(d.center_x, d.height, self.p.target_height))
        return m

    def reset_stats(self) -> None:
        """开始新一段统计：帧数、推理总耗时、起始时刻。"""
        self.frames, self.infer_seconds, self.stats_start = 0, 0.0, time.monotonic()

    def report(self) -> None:
        """每 REPORT_PERIOD 秒报告一次推理帧率与耗时；收不到图像时提醒检查话题。"""
        if self.frames:
            fps = self.frames / (time.monotonic() - self.stats_start)
            self.get_logger().info(f'推理 {fps:.1f} 帧/秒，平均推理耗时 '
                                   f'{1000 * self.infer_seconds / self.frames:.1f} ms')
        else:
            self.get_logger().warning(f'{REPORT_PERIOD:.0f} 秒内没有收到图像：请检查相机节点和'
                                      '图像话题（ros2 topic list、ros2 topic hz）')
        self.reset_stats()


def main() -> None:
    run(RecognizerNode)


if __name__ == '__main__':
    main()
