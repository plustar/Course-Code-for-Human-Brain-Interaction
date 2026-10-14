"""virtual_camera_node：跟随机器人位姿出图，位姿超时不出图；图像与内参；在 turtlesim 里标出虚拟人。"""
import math
from typing import Any, List

import cv2
from hci_common.camera_model import CameraModel
from hci_common.ros.image_msgs import imgmsg_to_bgr
from hci_common.ros.testing import LogSpy, Probe, spin_for, spin_until
from hci_common.samples import SAMPLE_FACE
from hci_sim.ros.virtual_camera_node import VirtualCameraNode
from hci_sim.world import Person, World
import pytest
from rclpy.parameter import Parameter
from sensor_msgs.msg import CameraInfo, Image
from turtlesim_msgs.msg import Pose
from turtlesim_msgs.srv import Spawn, TeleportAbsolute

pytestmark = pytest.mark.ros

STRANGER_AHEAD = World((Person('stranger', 7.5, 5.5),))  # 机器人在 (5.5, 5.5) 朝右时正前方 2 米


def make_node(namespace: str, world: Any = STRANGER_AHEAD, **params: Any) -> VirtualCameraNode:
    params.setdefault('rate', 20.0)
    overrides = [Parameter(k, value=v) for k, v in params.items()]
    return VirtualCameraNode(world, namespace=namespace, parameter_overrides=overrides)


def pose(theta: float = 0.0) -> Pose:
    return Pose(x=5.5, y=5.5, theta=theta)


def has_face(msg: Image) -> bool:
    """画面中心一列里有没有不是墙面、地面的像素（也就是画了人）。"""
    img = imgmsg_to_bgr(msg)
    column = img[:, msg.width // 2]
    return bool((column != column[0]).any(axis=1)[: int(msg.height * 0.7)].any())


def test_no_images_without_the_robot_pose(ros_context, namespace):
    node, probe = make_node(namespace), Probe(namespace)
    spy = LogSpy.attach(node)
    images = probe.listen(Image, 'image_raw')
    spin_for([node, probe], 0.5)
    assert not images and 'turtlesim 启动了吗' in spy.text('warning')


def test_images_and_camera_info_follow_the_pose(ros_context, namespace):
    node, probe = make_node(namespace), Probe(namespace)
    images, infos = probe.listen(Image, 'image_raw'), probe.listen(CameraInfo, 'camera_info')
    poses = probe.talker(Pose, 'pose')

    def look(theta: float) -> Image:
        images.clear()

        def ready() -> bool:
            poses.publish(pose(theta))
            return len(images) >= 3  # 前一两帧可能还是旧位姿
        assert spin_until([node, probe], ready)
        return images[-1]

    ahead = look(0.0)
    assert (ahead.width, ahead.height, ahead.header.frame_id) == (640, 480, 'camera')
    assert has_face(ahead)  # 面向陌生人
    assert not has_face(look(math.pi))  # 转身背对：画面里没有人
    assert CameraModel.from_camera_info(infos[-1]) == CameraModel.from_hfov(640, 480, 60.0)
    info_stamps = {(i.header.stamp.sec, i.header.stamp.nanosec) for i in infos}
    assert any((m.header.stamp.sec, m.header.stamp.nanosec) in info_stamps for m in images)


def test_stops_when_the_pose_is_stale(ros_context, namespace):
    node, probe = make_node(namespace, pose_timeout=0.3), Probe(namespace)
    images = probe.listen(Image, 'image_raw')
    poses = probe.talker(Pose, 'pose')

    def once() -> bool:
        poses.publish(pose())
        return bool(images)
    assert spin_until([node, probe], once)
    spin_for([node, probe], 0.5)  # 位姿不再更新：超时后停止出图
    images.clear()
    spin_for([node, probe], 0.5)
    assert not images


def test_marks_each_person_in_turtlesim_once(ros_context, namespace):
    walker = Person('walker', 8.0, 4.0, walk=1.0, period=4.0)
    node, probe = make_node(namespace, world=World((walker, Person('stranger', 8.5, 7.0)))), \
        Probe(namespace)
    spawned: List[Spawn.Request] = []
    teleported: List[TeleportAbsolute.Request] = []

    def spawn(request: Spawn.Request, response: Spawn.Response) -> Spawn.Response:
        spawned.append(request)
        response.name = request.name
        return response

    def teleport(request: Any, response: Any) -> Any:
        teleported.append(request)
        return response

    probe.create_service(Spawn, 'spawn', spawn)
    probe.create_service(TeleportAbsolute, 'walker/teleport_absolute', teleport)
    poses = probe.talker(Pose, 'pose')

    def walked() -> bool:
        poses.publish(pose())
        return len(teleported) >= 3
    assert spin_until([node, probe], walked, timeout=8.0)
    spin_for([node, probe], 1.2)
    assert sorted(r.name for r in spawned) == ['stranger', 'walker']  # 只生成一次
    assert {round(r.x, 2) for r in teleported} == {8.0}  # 走动的人沿 y 方向移动
    assert len({round(r.y, 2) for r in teleported}) > 1


def test_me_image_is_read_locally_and_scaled_by_its_face_ratio(ros_context, namespace, tmp_path):
    me_path = tmp_path / 'me.jpg'
    cv2.imwrite(str(me_path), cv2.imread(str(SAMPLE_FACE)))
    me = Person('me', 7.5, 5.5, image='me')
    node = make_node(namespace, world=World((me,)), me_image=str(me_path), me_target_ratio=0.3)
    assert 'me' in node.renderer.images and node.world.persons[0].face_ratio == 0.3


def test_missing_me_image_is_reported(ros_context, namespace):
    with pytest.raises(FileNotFoundError, match='me_image'):
        make_node(namespace, me_image='/no/such/me.jpg')
