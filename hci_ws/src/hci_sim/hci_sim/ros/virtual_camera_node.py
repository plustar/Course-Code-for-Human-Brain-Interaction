"""
virtual_camera_node：装在 turtle1 头上的虚拟相机。

订阅  pose         turtlesim_msgs/Pose：机器人的位姿（launch 重映射到 /turtle1/pose）
发布  image_raw    sensor_msgs/Image：按位姿渲染的画面（launch 重映射到 /camera/image_raw）
      camera_info  sensor_msgs/CameraInfo：与渲染所用的相机模型一致
调用  spawn        turtlesim_msgs/Spawn：启动时在 turtlesim 里放一只同名小海龟，标出每个虚拟人的位置

机器人一转，画面就跟着变：识别和行为节点收到的就是普通的图像和内参，不知道自己在仿真里。
"""
from dataclasses import dataclass, replace
import math
import time
from typing import Any, Dict, Optional

from hci_common.camera_model import CameraModel
from hci_common.params import param, require_positive
from hci_common.ros.image_msgs import bgr_to_imgmsg, camera_info_msg
from hci_common.ros.params import declare_params
from hci_common.ros.qos import image_qos
from hci_common.ros.runner import run
from hci_common.samples import sample_face
from hci_sim.renderer import Renderer
from hci_sim.world import default_world, load_world, Person, Pose2D, World
import numpy as np
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image
from turtlesim_msgs.msg import Pose
from turtlesim_msgs.srv import Spawn, TeleportAbsolute


@dataclass
class Params:
    """virtual_camera_node 的参数。"""

    world: str = param('', '世界文件（yaml）的绝对路径；留空则右前方站一位陌生人')
    me_image: str = param('', '"我"的头像：一张正脸照片（像证件照，脸占画面一半左右），只在本机读取')
    me_target_ratio: float = param(0.45, '"我"的照片里，目标（人脸 / 标志物）高度占照片高度的比例')
    width: int = param(640, '画面宽度（像素）')
    height: int = param(480, '画面高度（像素）')
    hfov_deg: float = param(60.0, '虚拟相机的水平视场角（度）')
    rate: float = param(15.0, '发布频率（Hz）')
    frame_id: str = param('camera', '写进 header 的坐标系名')
    spawn_markers: bool = param(True, '是否在 turtlesim 里放小海龟标出虚拟人的位置')
    pose_timeout: float = param(1.0, '超过这么多秒没收到机器人位姿就不再出图（秒）')


class VirtualCameraNode(Node):
    """虚拟相机。world 可以直接传入，测试时不需要 yaml 文件。"""

    def __init__(self, world: Optional[World] = None, **kwargs: Any) -> None:
        super().__init__('virtual_camera_node', **kwargs)
        self.p = declare_params(self, Params)
        require_positive(self.p, 'rate')
        world = world or (load_world(self.p.world) if self.p.world else default_world())
        self.world = World(tuple(self.with_ratio(person) for person in world.persons))
        images: Dict[str, np.ndarray] = {'stranger': sample_face()}
        if self.p.me_image:
            images['me'] = self.load_me()
        self.camera = CameraModel.from_hfov(self.p.width, self.p.height, self.p.hfov_deg)
        self.renderer = Renderer(self.camera, images)
        shown = [p for p in self.world.persons if p.image in images]  # 有头像、会出现在画面里的人
        for person in self.world.persons:
            if person not in shown:
                self.get_logger().info(f'{person.name} 的头像 {person.image} 没有提供，不出现在画面里')

        self.pose: Optional[Pose2D] = None
        self.pose_time = -math.inf
        self.t0 = time.monotonic()
        qos = image_qos('reliable')  # 与 camera_node 相同：Reliable 的发布者能匹配两种订阅者
        self.pub_image = self.create_publisher(Image, 'image_raw', qos)
        self.pub_info = self.create_publisher(CameraInfo, 'camera_info', qos)
        self.create_subscription(Pose, 'pose', self.on_pose, 10)
        self.spawn_client = self.create_client(Spawn, 'spawn')
        self.teleport = {
            p.name: self.create_client(TeleportAbsolute, f'{p.name}/teleport_absolute')
            for p in shown if p.walk > 0}
        self.to_spawn = shown if self.p.spawn_markers else []
        self.create_timer(1.0 / self.p.rate, self.on_timer)
        self.spawn_timer = self.create_timer(0.5, self.on_spawn_timer)
        self.get_logger().info(f'虚拟相机：{self.p.width}x{self.p.height}，水平视场 '
                               f'{self.p.hfov_deg:.0f}°，{len(self.world.persons)} 个虚拟人')

    def load_me(self) -> np.ndarray:
        import cv2

        img = cv2.imread(self.p.me_image)
        if img is None:
            raise FileNotFoundError(f'读不出 me_image：{self.p.me_image}')
        return img

    def with_ratio(self, person: Person) -> Person:
        """对"我"的照片使用参数 me_target_ratio 作为目标（人脸 / 标志物）比例。"""
        if person.image == 'me':
            return replace(person, face_ratio=self.p.me_target_ratio)
        return person

    def on_pose(self, msg: Pose) -> None:
        self.pose = Pose2D(msg.x, msg.y, msg.theta)
        self.pose_time = time.monotonic()

    def on_timer(self) -> None:
        """按最新的位姿渲染一帧，连同相机内参一起发布。"""
        if self.pose is None or time.monotonic() - self.pose_time > self.p.pose_timeout:
            self.get_logger().warning('没有收到机器人位姿：turtlesim 启动了吗？pose 话题对吗？',
                                      throttle_duration_sec=5.0)
            return
        t = time.monotonic() - self.t0
        people = [(person, *person.position(t)) for person in self.world.persons]
        frame = self.renderer.render(self.pose, people)
        msg = bgr_to_imgmsg(frame)
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.p.frame_id
        self.pub_image.publish(msg)
        self.pub_info.publish(camera_info_msg(self.camera, msg.header))
        for person, x, y in people:  # 走动的人：把 turtlesim 里的标记也挪过去
            client = self.teleport.get(person.name)
            if client is not None and client.service_is_ready():
                client.call_async(TeleportAbsolute.Request(x=float(x), y=float(y), theta=math.pi))

    def on_spawn_timer(self) -> None:
        """turtlesim 准备好后，为每个虚拟人放一只小海龟；放好（或不用放）就停掉这个定时器。"""
        if self.to_spawn and not self.spawn_client.service_is_ready():
            return  # turtlesim 还没启动好，0.5 秒后再看
        for person in self.to_spawn:
            x, y = person.position(0.0)
            self.spawn_client.call_async(
                Spawn.Request(x=float(x), y=float(y), theta=math.pi, name=person.name))
        if self.to_spawn:
            self.get_logger().info(f'已在 turtlesim 里标出：{[p.name for p in self.to_spawn]}')
        self.to_spawn = []
        self.spawn_timer.cancel()


def main() -> None:
    run(VirtualCameraNode)


if __name__ == '__main__':
    main()
