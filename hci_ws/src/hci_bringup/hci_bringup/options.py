"""
启动参数的规则（纯 Python，launch 文件和测试共用）。

机器人（robot:=）和图像来源（camera:=）是两件独立的事，用两个参数组合：
  camera:=sim     虚拟相机按 turtle1 的位姿渲染画面            只能配 turtlesim
  camera:=webcam  笔记本摄像头（人在回路中）                    turtlesim、gazebo
  camera:=video   视频文件，用来复现问题、做回归测试            turtlesim、gazebo
  camera:=robot   机器人自带的相机                             gazebo、turtlebot4
感知部分（perception.launch.py）单独启动时，camera 还可以是 none：不启动相机，图像由别处提供。
"""
from dataclasses import dataclass
import datetime
import os
from typing import Dict, List, Optional, Tuple

from hci_common.identity import OTHERS
from hci_common.params import FALSE_WORDS, TRUE_WORDS


@dataclass(frozen=True)
class Robot:
    """一种机器人平台的话题。"""

    cmd_vel: str  # 速度话题
    pose: str  # 位姿话题（虚拟相机用；没有时为空）
    camera: str  # 机器人自带相机的图像话题（没有时为空）
    camera_reliability: str = ''  # 订阅这台相机用的可靠性，要与相机的发布端相容


ROBOTS: Dict[str, Robot] = {
    'turtlesim': Robot('/turtle1/cmd_vel', '/turtle1/pose', ''),
    # TurtleBot 3 waffle 的相机：ros_gz 的图像桥默认用 Reliable 发布 1920×1080 的画面，
    # 用 Best Effort 订阅时大部分帧在传输中丢掉（实测每秒只剩 1 帧左右）
    'gazebo': Robot('/cmd_vel', '', '/camera/image_raw', 'reliable'),
    # Jazzy 真机，只作案例：OAK-D 按传感器的惯例用 Best Effort 发布，订阅端只能用 Best Effort
    'turtlebot4': Robot('/cmd_vel', '', '/oakd/rgb/preview/image_raw', 'best_effort'),
}
CAMERAS = ('sim', 'webcam', 'video', 'robot')
PERCEPTION_CAMERAS = ('webcam', 'video', 'robot', 'none')
# 演示模式（follow:=anyone）：YuNet 把每张脸都标成"他人"，所以要找的就是这一类
DEMO_BEHAVIOR = {'target_class': OTHERS, 'greeting_template': '你好！'}
VALID = {
    'sim': ('turtlesim',),
    'webcam': ('turtlesim', 'gazebo'),
    'video': ('turtlesim', 'gazebo'),
    'robot': ('gazebo', 'turtlebot4'),
}
WEBCAM_TOPIC = '/camera/image_raw'  # camera_node 和虚拟相机都发布到这里


def check_combo(robot: str, camera: str) -> None:
    """robot 与 camera 的组合不合法时，用中文说明怎么改。"""
    if robot not in ROBOTS:
        raise ValueError(f'robot 只能是 {list(ROBOTS)}，收到 {robot!r}')
    if camera not in CAMERAS:
        raise ValueError(f'camera 只能是 {list(CAMERAS)}，收到 {camera!r}')
    if robot not in VALID[camera]:
        raise ValueError(f'camera:={camera} 只能配合 robot:={"、".join(VALID[camera])}，'
                         f'收到 robot:={robot}')


def check_perception_camera(camera: str) -> None:
    """perception.launch.py 的 camera 不合法时，用中文说明可选的值。"""
    if camera not in PERCEPTION_CAMERAS:
        raise ValueError(f'camera 只能是 {"、".join(PERCEPTION_CAMERAS)}，收到 {camera!r}')


def parse_switch(name: str, value: str) -> Optional[bool]:
    """
    开关类的启动参数（record、show_window、blur_others）：与节点参数认同样的写法。

    true、1、yes、on 为开，false、0、no、off 为关；留空返回 None，表示用参数文件里的值。
    """
    word = value.strip().lower()
    if not word:
        return None
    if word in TRUE_WORDS:
        return True
    if word in FALSE_WORDS:
        return False
    raise ValueError(f'{name} 只能是 true 或 false，收到 {value!r}')


def image_topics(camera: str, robot: str, robot_camera_topic: str = '') -> Tuple[str, str]:
    """识别和显示节点该订阅的 (图像话题, 内参话题)。"""
    if camera == 'robot':
        image = robot_camera_topic or ROBOTS[robot].camera
        if not image:
            raise ValueError(f'{robot} 没有默认的相机话题，请用 robot_camera_topic:= 指定')
    else:
        image = WEBCAM_TOPIC
    return image, image.rsplit('/', 1)[0] + '/camera_info'


def behavior_files(config_dir: str, robot: str, own_file: str = '') -> List[str]:
    """
    行为节点按顺序加载的参数文件，后加载的覆盖前面的同名参数。

    公共参数 behavior.yaml → 平台参数 robots/<robot>.yaml → 自己的文件（behavior_params，只写要改的）。
    """
    files = [os.path.join(config_dir, 'behavior.yaml'),
             os.path.join(config_dir, 'robots', f'{robot}.yaml')]
    return files + [own_file] if own_file else files


def follow_mode(follow: str, camera: str, model: str, gallery: str) -> str:
    """
    跟随谁：me（只跟随本人 stu_*）或 anyone（任何人脸，演示用）。

    留空时自动决定：仿真里又没有自己的模型时用 anyone，这样不训练模型也能看到闭环。
    """
    if follow:
        if follow not in ('me', 'anyone'):
            raise ValueError(f'follow 只能是 me 或 anyone，收到 {follow!r}')
        return follow
    return 'anyone' if camera == 'sim' and not model and not gallery else 'me'


def follow_note(follow: str, model: str, gallery: str) -> str:
    """启动时提醒一句跟随谁；不用提醒时返回空字符串。"""
    if follow == 'anyone':
        return '演示模式：跟随画面里的任何人脸。有了自己的模型后加 model:=/绝对路径/best.onnx'
    if not model and not gallery:  # YuNet 把所有人脸都当作"他人"，本人永远不会出现
        return ('还没有自己的模型（model:=），只会跟随本人：画面里只有"他人"时机器人停着不动。'
                '想先看演示效果，加 follow:=anyone')
    return ''


def record_topics(robot: str, cmd_vel: str = '') -> List[str]:
    """
    录包时录哪些话题：检测、状态、问候、内参、速度、位姿。

    默认不录原始图像（人脸属于个人信息）。cmd_vel：速度话题，留空用平台的默认话题。
    """
    topics = ['/hci/detections', '/hci/behavior_state', '/hci/greeting', '/camera/camera_info',
              cmd_vel or ROBOTS[robot].cmd_vel]
    if ROBOTS[robot].pose:
        topics.append(ROBOTS[robot].pose)
    return topics


def record_command(path: str, robot: str, cmd_vel: str = '') -> List[str]:
    """录包的命令。Lyrical 的 ros2 bag record 只认写在 --topics 后面的话题名。"""
    return ['ros2', 'bag', 'record', '-o', path, '--topics'] + record_topics(robot, cmd_vel)


def bag_path(now: Optional[datetime.datetime] = None) -> str:
    """录包的保存位置：~/hci_bags/日期_时间（放在仓库外面，不会被误提交）。"""
    now = now or datetime.datetime.now()
    return os.path.join(os.path.expanduser('~'), 'hci_bags', now.strftime('%Y%m%d_%H%M%S'))
