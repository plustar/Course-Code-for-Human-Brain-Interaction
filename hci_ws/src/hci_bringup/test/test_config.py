"""
参数文件与启动参数的规则。

yaml 里的每个键都必须是节点真正声明过的参数（拼错的键会被 ROS 悄悄忽略，这里让它报错）；
robot 与 camera 的组合、录包的话题、跟随模式按 hci_bringup/options.py 的规则检查。
"""
import datetime
from pathlib import Path
from typing import Any, Dict

from hci_behavior.ros.behavior_node import Params as BehaviorParams
from hci_bringup.options import (bag_path, behavior_files, CAMERAS, check_combo,
                                 check_perception_camera, DEMO_BEHAVIOR, follow_mode, follow_note,
                                 image_topics, parse_switch, record_command, record_topics, ROBOTS,
                                 VALID)
from hci_common.identity import OTHERS
from hci_common.params import convert, param_table
from hci_perception.ros.camera_node import Params as CameraParams
from hci_perception.ros.recognizer_node import Params as RecognizerParams
from hci_perception.ros.viewer_node import Params as ViewerParams
from hci_sim.ros.virtual_camera_node import Params as VirtualCameraParams
from hci_sim.world import load_world
import pytest
import yaml

CONFIG = Path(__file__).resolve().parents[1] / 'config'
NODES = {'camera_node': CameraParams, 'recognizer_node': RecognizerParams,
         'viewer_node': ViewerParams, 'behavior_node': BehaviorParams,
         'virtual_camera_node': VirtualCameraParams}
PARAM_FILES = sorted(p for p in CONFIG.rglob('*.yaml') if p.name != 'sim_world.yaml')


def sections(path: Path) -> Dict[str, Dict[str, Any]]:
    """yaml 文件 -> {节点名: {参数名: 值}}；节点写成 /**/节点名，对任何命名空间都生效。"""
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    out = {}
    for key, value in data.items():
        assert key.startswith('/**/'), f'{path.name}：{key} 应写成 /**/节点名'
        out[key[len('/**/'):]] = value['ros__parameters']
    return out


@pytest.mark.parametrize('path', PARAM_FILES, ids=lambda p: p.relative_to(CONFIG).as_posix())
def test_every_key_is_a_declared_parameter(path):
    for node, params in sections(path).items():
        assert node in NODES, f'{path.name}：没有叫 {node} 的节点'
        declared = {name: default for name, default, _ in param_table(NODES[node])}
        unknown = set(params) - set(declared)
        assert not unknown, f'{path.name} 里 {node} 没有这些参数（拼错了？）：{sorted(unknown)}'
        for name, value in params.items():  # 值的类型也要对得上，例如小数参数不能写成字符串
            default = declared[name]
            converted = convert(value, default)
            assert type(converted) is type(default), f'{path.name}：{node}.{name} = {value!r}'
            if isinstance(default, (int, float)) and not isinstance(default, bool):
                assert not isinstance(value, (str, bool)), f'{path.name}：{node}.{name} 应是数字'


def test_perception_yaml_lists_every_parameter():
    found = sections(CONFIG / 'perception.yaml')
    for node in ('camera_node', 'recognizer_node', 'viewer_node'):
        declared = [name for name, _, _ in param_table(NODES[node])]
        assert list(found[node]) == declared, f'perception.yaml 的 {node} 应按声明顺序列出全部参数'


def test_each_robot_has_a_profile():
    assert sorted(p.stem for p in (CONFIG / 'robots').glob('*.yaml')) == sorted(ROBOTS)


def test_sim_world_file_is_valid():
    world = load_world(str(CONFIG / 'sim_world.yaml'))
    assert [(p.name, p.image) for p in world.persons] == [('stranger', 'stranger'), ('me', 'me')]


@pytest.mark.parametrize('camera', CAMERAS)
@pytest.mark.parametrize('robot', sorted(ROBOTS))
def test_robot_and_camera_combinations(robot, camera):
    if robot in VALID[camera]:
        check_combo(robot, camera)
    else:
        with pytest.raises(ValueError, match='只能配合'):
            check_combo(robot, camera)


@pytest.mark.parametrize('robot, camera', [('turtlebot3', 'sim'), ('turtlesim', 'usb')])
def test_unknown_robot_or_camera(robot, camera):
    with pytest.raises(ValueError, match='只能是'):
        check_combo(robot, camera)


def test_camera_info_sits_next_to_the_image():
    assert image_topics('webcam', 'turtlesim') == ('/camera/image_raw', '/camera/camera_info')
    assert image_topics('robot', 'turtlebot4') == ('/oakd/rgb/preview/image_raw',
                                                   '/oakd/rgb/preview/camera_info')
    custom = image_topics('robot', 'gazebo', '/my_robot/cam/image')
    assert custom == ('/my_robot/cam/image', '/my_robot/cam/camera_info')
    with pytest.raises(ValueError, match='robot_camera_topic'):
        image_topics('robot', 'turtlesim')


def test_switches_accept_the_same_words_as_node_parameters():
    # 原来 record:=1 不会录包，show_window:=yes 被悄悄忽略：现在与节点参数认同样的写法
    assert parse_switch('record', '1') is True and parse_switch('record', 'Yes') is True
    assert parse_switch('blur_others', 'off') is False and parse_switch('show_window', '') is None
    with pytest.raises(ValueError, match='record 只能是 true 或 false'):
        parse_switch('record', 'ture')


def test_perception_camera_choices():
    for camera in ('webcam', 'video', 'robot', 'none'):
        check_perception_camera(camera)
    with pytest.raises(ValueError, match='camera 只能是'):
        check_perception_camera('sim')  # 仿真画面由 system.launch.py 的虚拟相机提供


def test_demo_mode_follows_the_others_class():
    # YuNet 把每张脸都标成"他人"：演示模式要跟随的就是这一类
    assert DEMO_BEHAVIOR['target_class'] == OTHERS


def test_follow_mode():
    assert follow_mode('', 'sim', '', '') == 'anyone'  # 仿真里又没有自己的模型：演示模式
    assert follow_mode('', 'sim', '/m/best.onnx', '') == 'me'
    assert follow_mode('', 'sim', '', '/m/me_sface.npy') == 'me'
    assert follow_mode('', 'webcam', '', '') == 'me'
    assert follow_mode('anyone', 'webcam', '/m/best.onnx', '') == 'anyone'
    with pytest.raises(ValueError, match='me 或 anyone'):
        follow_mode('everyone', 'sim', '', '')


def test_follow_note_explains_why_the_robot_stands_still():
    assert '演示模式' in follow_note('anyone', '', '')
    # 用摄像头又没有自己的模型：YuNet 把所有人都当作"他人"，只跟随本人时机器人不会动
    assert 'follow:=anyone' in follow_note('me', '', '')
    assert follow_note('me', '/m/best.onnx', '') == '' and follow_note('me', '', '/m/g.npy') == ''


def test_robot_cameras_say_how_to_subscribe():
    # 订阅的可靠性要与相机的发布端相容：OAK-D 是 Best Effort，ros_gz 的图像桥是 Reliable
    assert ROBOTS['turtlebot4'].camera_reliability == 'best_effort'
    assert ROBOTS['gazebo'].camera_reliability == 'reliable'
    for robot in VALID['robot']:
        assert ROBOTS[robot].camera and ROBOTS[robot].camera_reliability


def test_own_behavior_file_is_loaded_after_the_platform_profile():
    # 自己的参数文件只写要改的参数：平台的速度、消息类型仍然来自 robots/<robot>.yaml
    assert behavior_files('/cfg', 'turtlesim', '/home/me/my_behavior.yaml') == [
        '/cfg/behavior.yaml', '/cfg/robots/turtlesim.yaml', '/home/me/my_behavior.yaml']
    assert behavior_files('/cfg', 'gazebo') == ['/cfg/behavior.yaml', '/cfg/robots/gazebo.yaml']


@pytest.mark.parametrize('robot', sorted(ROBOTS))
def test_recording_never_includes_raw_images(robot):
    topics = record_topics(robot)
    assert {'/hci/detections', '/hci/behavior_state', ROBOTS[robot].cmd_vel} <= set(topics)
    assert not [t for t in topics if 'image' in t]  # 人脸属于个人信息：默认不录原始图像
    assert '/model/car/cmd_vel' in record_topics(robot, '/model/car/cmd_vel')  # 自定义速度话题


def test_record_command_puts_topics_after_the_topics_option():
    # Lyrical 的 ros2 bag record 不再接受直接写在后面的话题名，必须写在 --topics 后面
    cmd = record_command('/tmp/bag', 'turtlesim')
    assert cmd[:6] == ['ros2', 'bag', 'record', '-o', '/tmp/bag', '--topics']
    assert cmd[6:] == record_topics('turtlesim')


def test_bags_go_outside_the_repository():
    path = Path(bag_path(datetime.datetime(2026, 12, 1, 14, 30, 5)))
    assert path == Path.home() / 'hci_bags' / '20261201_143005'
