"""
感知系统一键启动：相机 -> 识别 -> 显示（练习 4）。

用法示例
  ros2 launch hci_bringup perception.launch.py                        # 摄像头 + YuNet 演示模式
  ros2 launch hci_bringup perception.launch.py model:=/绝对路径/best.onnx id_map:="stu_2023123456=张三"
  ros2 launch hci_bringup perception.launch.py camera:=video source:=/绝对路径/me.mp4   # 视频代替摄像头
  ros2 launch hci_bringup perception.launch.py perception_params:=/绝对路径/my.yaml    # 自己的参数文件
话题：/camera/image_raw 与 /camera/camera_info -> /hci/detections -> /hci/overlay
命令行没给的参数，使用参数文件（默认 hci_bringup/config/perception.yaml）里的值。
"""
import os

from ament_index_python.packages import get_package_share_directory
from hci_bringup.options import (check_combo, check_perception_camera, image_topics,
                                 parse_switch, ROBOTS)
from launch import LaunchContext, LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

ARGS = {  # 启动参数：(默认值, 说明)
    'camera': ('webcam', 'webcam（摄像头）、video（视频文件）、robot（机器人相机）或 none（不启动相机）'),
    'source': ('', '摄像头编号或视频文件的绝对路径'),
    'robot': ('', 'camera:=robot 时的机器人平台：gazebo 或 turtlebot4'),
    'robot_camera_topic': ('', 'camera:=robot 时的图像话题（留空用平台的默认话题）'),
    'model': ('', '练习 3 导出的 best.onnx（绝对路径）；留空用 YuNet 演示模式'),
    'gallery': ('', '两步法的登记文件（.npy，绝对路径）'),
    'identity': ('', '两步法比对成功时的类别名，如 stu_2023123456'),
    'id_map': ('', '学号与姓名，如 "stu_2023123456=张三"，多人用逗号分隔'),
    'image_reliability': ('', 'reliable 或 best_effort：图像订阅的可靠性（留空时自动选择）'),
    'show_window': ('', 'true 或 false：是否弹窗显示'),
    'blur_others': ('', 'true 或 false：是否给他人的脸打码'),
    'perception_params': ('', '自己的参数文件（留空用 hci_bringup/config/perception.yaml）'),
}


def launch_setup(context: LaunchContext) -> list:
    def get(name: str) -> str:
        return LaunchConfiguration(name).perform(context).strip()

    camera = get('camera')
    check_perception_camera(camera)
    share = get_package_share_directory('hci_bringup')
    params_file = get('perception_params') or os.path.join(share, 'config', 'perception.yaml')
    if not os.path.isfile(params_file):
        raise FileNotFoundError(f'找不到参数文件：{params_file}')
    # 识别和显示订阅哪个图像话题：摄像头、视频、仿真都是 /camera/image_raw，机器人相机另算。
    # 订阅的可靠性要与发布端相容：自己的摄像头和仿真用 Reliable（参数文件里的默认值），
    # 机器人的相机按平台来（TurtleBot 4 是 Best Effort，Gazebo 的图像桥是 Reliable）
    reliability = get('image_reliability')
    if camera == 'robot':
        robot = get('robot') or 'gazebo'
        check_combo(robot, 'robot')  # robot 写错，或者选了没有相机的平台：用中文说明
        image, info = image_topics('robot', robot, get('robot_camera_topic'))
        reliability = reliability or ROBOTS[robot].camera_reliability
    else:
        image, info = image_topics('webcam', 'turtlesim')
    remaps = [('image_raw', image), ('image_raw/compressed', image + '/compressed'),
              ('camera_info', info)]

    def given(**kv: object) -> dict:  # 只覆盖命令行里真正给了值的参数
        return {k: v for k, v in kv.items() if v not in ('', None, [])}

    nodes = []
    if camera in ('webcam', 'video'):
        if camera == 'video' and not get('source'):
            raise ValueError('camera:=video 需要视频文件：source:=/绝对路径/视频.mp4')
        source = {'source': ParameterValue(get('source'), value_type=str)} if get('source') else {}
        nodes.append(Node(package='hci_perception', executable='camera_node', name='camera_node',
                          namespace='camera', output='screen', parameters=[params_file, source]))
    id_map = [x.strip() for x in get('id_map').split(',') if x.strip()]
    nodes.append(Node(package='hci_perception', executable='recognizer_node',
                      name='recognizer_node', namespace='hci', output='screen',
                      parameters=[params_file, given(model=get('model'), gallery=get('gallery'),
                                                     identity=get('identity'), id_map=id_map,
                                                     image_reliability=reliability)],
                      remappings=remaps))
    switches = {name: parse_switch(name, get(name)) for name in ('show_window', 'blur_others')}
    nodes.append(Node(package='hci_perception', executable='viewer_node', name='viewer_node',
                      namespace='hci', output='screen',
                      parameters=[params_file, given(image_reliability=reliability, **switches)],
                      remappings=remaps))
    return nodes


def generate_launch_description() -> LaunchDescription:
    args = [DeclareLaunchArgument(name, default_value=default, description=doc)
            for name, (default, doc) in ARGS.items()]
    return LaunchDescription(args + [OpaqueFunction(function=launch_setup)])
