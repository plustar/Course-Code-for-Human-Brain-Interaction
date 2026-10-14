"""
图像来源：笔记本摄像头或视频文件（WSL2 摄像头打不开时，用视频文件完成全部流程）。

摄像头按参数设置分辨率和像素格式，默认 MJPG：不压缩的 YUYV 数据量大好几倍，WSL2 经 usbipd
转发时画面传不完整，缺的部分显示成绿色。视频文件按它自身的帧率播放，播完可以从头循环。
camera_node 只认 FrameSource 这个接口，测试时可以换成不需要真摄像头的替身；练习 3 的脚本
打开摄像头也用这里的 VideoSource，两边的行为完全一致。
"""
import os
import re
from typing import Optional, Protocol, Tuple

import numpy as np


class FrameSource(Protocol):
    """图像来源的接口：VideoSource 与测试替身都满足它。"""

    @property
    def size(self) -> Tuple[int, int]:
        """画面的 (宽, 高)。"""
        ...

    @property
    def native_fps(self) -> float:
        """视频文件自身的帧率；摄像头为 0。"""
        ...

    def read(self) -> Optional[np.ndarray]:
        """读下一帧，读不到时返回 None。"""
        ...

    def release(self) -> None:
        """释放设备或文件。"""
        ...


def camera_index(source: str) -> Optional[int]:
    """摄像头的编号：'0' 和 '/dev/video0' 都是 0；其他写法（视频文件的路径）返回 None。"""
    found = re.fullmatch(r'(?:/dev/video)?(\d+)', str(source))
    return int(found.group(1)) if found else None


def camera_problem(index: int, dev: str = '/dev') -> str:
    """摄像头打不开时，按设备文件 /dev/video<编号> 的情况说明最可能的原因和解决办法。"""
    path = os.path.join(dev, f'video{index}')
    if not os.path.exists(path):
        return (f'没有 {path}。WSL2 要先用 usbipd 把摄像头转发进来（README 第 4.7 节），'
                '也可以改用视频文件')
    if not os.access(path, os.R_OK | os.W_OK):
        return (f'没有权限使用 {path}。执行 sudo usermod -aG video $USER，然后重新登录'
                '（WSL2：在 PowerShell 里执行 wsl --shutdown，重新打开终端，再 usbipd attach）')
    return f'{path} 存在但打不开：可能正被别的程序占用，或者它不是彩色摄像头（换个编号试试）'


class VideoSource:
    """摄像头（source 是编号如 '0'，或设备文件如 '/dev/video0'）或视频文件（文件路径）。"""

    def __init__(self, source: str, width: int = 640, height: int = 480,
                 fourcc: str = 'MJPG', loop: bool = True) -> None:
        import cv2

        index = camera_index(source)  # /dev/video0 与 0 是同一个摄像头
        self.is_file = index is None
        self.loop = loop
        if index is None and not os.path.isfile(source):
            raise FileNotFoundError(f'找不到视频文件：{source}（请使用绝对路径）')
        self.cap = cv2.VideoCapture(source if index is None else index)
        if not self.is_file:
            if len(fourcc) == 4:  # 如 MJPG、YUYV；其他写法忽略
                self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if not self.cap.isOpened():
            if index is None:
                raise RuntimeError(f'无法读取视频文件 {source}：格式不支持或文件已损坏')
            raise RuntimeError(f'无法打开摄像头 {index}：{camera_problem(index)}')

    @property
    def size(self) -> Tuple[int, int]:
        """画面的 (宽, 高)，以设备或文件实际给出的为准。"""
        import cv2

        return (int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))

    @property
    def native_fps(self) -> float:
        """视频文件自身的帧率；摄像头或读不到时为 0。"""
        import cv2

        fps = float(self.cap.get(cv2.CAP_PROP_FPS)) if self.is_file else 0.0
        return fps if fps > 0 else 0.0

    def read(self) -> Optional[np.ndarray]:
        """读下一帧；视频播完且允许循环时从头再来；读不到时返回 None。"""
        import cv2

        ok, frame = self.cap.read()
        if not ok and self.is_file and self.loop:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
        return frame if ok else None

    def release(self) -> None:
        """释放摄像头或文件。"""
        self.cap.release()
