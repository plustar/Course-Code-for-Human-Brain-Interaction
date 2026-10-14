"""
整个系统一键启动：感知 + 行为 + 机器人（期末大作业）。

用法示例
  # 默认：turtlesim + 虚拟相机，没有摄像头也能跑（演示模式：跟随画面里的任何人脸）
  ros2 launch hci_bringup system.launch.py
  # 仿真里认出"我"：自己的模型 + 自己的照片
  ros2 launch hci_bringup system.launch.py model:=/绝对路径/best.onnx \
      id_map:="stu_2023123456=张三" me_image:=/绝对路径/me.jpg
  # 笔记本摄像头；Gazebo 差速小车；同时录包到 ~/hci_bags
  ros2 launch hci_bringup system.launch.py camera:=webcam model:=/绝对路径/best.onnx
  ros2 launch hci_bringup system.launch.py robot:=gazebo camera:=webcam model:=/绝对路径/best.onnx
  ros2 launch hci_bringup system.launch.py record:=true

robot:= 选机器人（turtlesim、gazebo、turtlebot4），camera:= 选图像来源（sim、webcam、video、robot），
合法的组合见 hci_bringup/options.py。Gazebo 要先在另一个终端启动仿真；TurtleBot 4 是 Jazzy 真机，只作案例。
仿真里又没有给自己的模型时，自动进入演示模式（follow:=anyone）：跟随画面里的任何人脸。
"""
import os
from typing import Any, List

from ament_index_python.packages import get_package_share_directory
from hci_bringup.options import (bag_path, behavior_files, check_combo, DEMO_BEHAVIOR, follow_mode,
                                 follow_note, parse_switch, record_command, ROBOTS)
from launch import LaunchContext, LaunchDescription
from launch.actions import (DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription,
                            LogInfo, OpaqueFunction)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

ARGS = {  # 启动参数：(默认值, 说明)
    'robot': ('turtlesim', 'turtlesim、gazebo 或 turtlebot4'),
    'camera': ('sim', 'sim（虚拟相机）、webcam（摄像头）、video（视频文件）或 robot（机器人相机）'),
    'follow': ('', 'me（只跟随本人）或 anyone（任何人脸，演示用）；留空自动决定'),
    'record': ('false', 'true：同时录包到 ~/hci_bags（不录原始图像）'),
    'world': ('', '仿真世界文件（留空用 hci_bringup/config/sim_world.yaml）'),
    'me_image': ('', '仿真里"我"的照片（绝对路径，只在本机读取）'),
    'behavior_params': ('', '自己的行为参数文件，在默认参数和平台参数之后加载（只写要改的参数）'),
    'cmd_vel_topic': ('', '机器人的速度话题（留空用平台的默认话题，如 /cmd_vel）'),
}
PASSTHROUGH = ['source', 'robot_camera_topic', 'model', 'gallery', 'identity', 'id_map',
               'image_reliability', 'show_window', 'blur_others',
               'perception_params']  # 原样交给 perception.launch.py


def launch_setup(context: LaunchContext) -> list:
    def get(name: str) -> str:
        return LaunchConfiguration(name).perform(context).strip()

    robot, camera = get('robot'), get('camera')
    check_combo(robot, camera)
    cmd_vel = get('cmd_vel_topic') or ROBOTS[robot].cmd_vel
    follow = follow_mode(get('follow'), camera, get('model'), get('gallery'))
    share = get_package_share_directory('hci_bringup')
    actions: list = []

    if robot == 'turtlesim':
        actions.append(Node(package='turtlesim', executable='turtlesim_node', name='turtlesim',
                            output='screen'))
    if camera == 'sim':
        world = get('world') or os.path.join(share, 'config', 'sim_world.yaml')
        actions.append(Node(
            package='hci_sim', executable='virtual_camera_node', name='virtual_camera_node',
            output='screen', parameters=[{'world': world, 'me_image': get('me_image')}],
            remappings=[('image_raw', '/camera/image_raw'), ('camera_info', '/camera/camera_info'),
                        ('pose', ROBOTS[robot].pose)]))

    perception = {name: get(name) for name in PASSTHROUGH}
    perception['camera'] = 'none' if camera == 'sim' else camera  # 仿真画面由虚拟相机提供
    perception['robot'] = robot
    if follow == 'anyone' and not perception['blur_others']:
        perception['blur_others'] = 'false'  # 演示模式里要跟随的就是"他人"，不能打码
    actions.append(IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(share, 'launch', 'perception.launch.py')),
        launch_arguments=perception.items()))

    behavior: List[Any] = list(behavior_files(os.path.join(share, 'config'), robot,
                                              get('behavior_params')))
    if follow == 'anyone':
        behavior.append(dict(DEMO_BEHAVIOR))
    note = follow_note(follow, get('model'), get('gallery'))
    if note:
        actions.append(LogInfo(msg=note))
    actions.append(Node(package='hci_behavior', executable='behavior_node', name='behavior_node',
                        namespace='hci', output='screen', parameters=behavior,
                        remappings=[('cmd_vel', cmd_vel)]))

    if parse_switch('record', get('record')):
        path = bag_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        actions.append(LogInfo(msg=f'录包到 {path}（不含原始图像）'))
        actions.append(ExecuteProcess(cmd=record_command(path, robot, cmd_vel), output='screen'))
    return actions


def generate_launch_description() -> LaunchDescription:
    args = [DeclareLaunchArgument(name, default_value=default, description=doc)
            for name, (default, doc) in ARGS.items()]
    args += [DeclareLaunchArgument(name, default_value='', description='见 perception.launch.py')
             for name in PASSTHROUGH]
    return LaunchDescription(args + [OpaqueFunction(function=launch_setup)])
