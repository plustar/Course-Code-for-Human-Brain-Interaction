"""
练习 3 各步脚本共用的小工具。

人脸检测（YuNet）、ONNX 推理、画框这些与 ROS 节点相同的部分，直接复用感知包和地基包的
纯 Python 代码（hci_perception、hci_common）：训练环境里由 setup_conda.sh 写入的
hci_course.pth 找到它们，不需要安装 ROS。
"""
import importlib
import os
from pathlib import Path
from typing import Any, Iterator, List, Optional, Tuple, Union

import numpy as np

try:  # 感知包的纯 Python 部分（训练环境里由 hci_course.pth 提供）
    from hci_perception.capture import camera_index, VideoSource
    from hci_perception.recognition.yunet import clip_box, YuNet
except ImportError as e:  # 只在环境没配好时出现
    raise SystemExit('找不到 hci_perception：训练环境请重新运行 bash env/setup_conda.sh；'
                     'ROS 环境请先 source hci_ws/install/setup.bash') from e

HERE = Path(__file__).resolve().parent
DATA = HERE / 'data'  # 照片、视频、标注：个人数据，只留在本机
IMG_EXT = {'.jpg', '.jpeg', '.png', '.bmp'}
VIDEO_EXT = {'.mp4', '.avi', '.mov', '.mkv'}
# 类别号：0 = 本人 stu_<学号>，1 = 他人 face（类别名的约定在 hci_common/identity.py）
SELF_ID, OTHERS_ID = 0, 1

PathLike = Union[str, Path]
Box = Tuple[float, float, float, float]
Face = Tuple[Box, float, np.ndarray]  # (像素框, 分数, YuNet 原始结果)


def need(module: str) -> Any:
    """导入训练环境才有的包（ultralytics、torch 等）；找不到时提示先激活 conda 环境。"""
    try:
        return importlib.import_module(module)
    except ImportError:
        raise SystemExit(f'找不到 {module}。练习 3 的这一步要在训练环境里运行：conda activate '
                         'hci-train（第一次使用先运行 bash env/setup_conda.sh）') from None


def ensure_dir(path: PathLike) -> Path:
    """创建文件夹（已存在也没关系），返回 Path。"""
    os.makedirs(path, exist_ok=True)
    return Path(path)


def list_images(folder: PathLike) -> List[Path]:
    """文件夹（含子文件夹）里的全部图片，按路径排序；文件夹不存在时返回空列表。"""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.rglob('*') if p.suffix.lower() in IMG_EXT)


def to_yolo_line(cls_id: int, box: Box, w: int, h: int) -> str:
    """像素框 (x1, y1, x2, y2) -> YOLO 标注行：类别 cx cy bw bh（都归一化到 0–1）。"""
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
    bw, bh = (x2 - x1) / w, (y2 - y1) / h
    return f'{cls_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}'


def from_yolo_line(line: str, w: int, h: int) -> Tuple[int, Box]:
    """YOLO 标注行 -> (类别, 像素框 (x1, y1, x2, y2))，是 to_yolo_line 的逆变换。"""
    c, cx, cy, bw, bh = line.split()
    x, y, half_w, half_h = float(cx) * w, float(cy) * h, float(bw) * w / 2, float(bh) * h / 2
    return int(c), (x - half_w, y - half_h, x + half_w, y + half_h)


def read_labels(label: Path) -> List[str]:
    """标注文件里的非空行；文件不存在时为空列表。"""
    if not label.exists():
        return []
    return [line for line in label.read_text().splitlines() if line.strip()]


def label_path(img: PathLike, data: PathLike = DATA) -> Path:
    """图片对应的标注文件：data/self/s1/a.jpg -> data/labels/self/s1/a.txt。"""
    rel = Path(img).resolve().relative_to(Path(data).resolve())
    return Path(data) / 'labels' / rel.with_suffix('.txt')


def detect_faces(detector: YuNet, img: np.ndarray, min_size: float = 0.0) -> List[Face]:
    """
    检测人脸，返回 [(像素框, 分数, YuNet 原始结果), ...]，按面积从大到小排序。

    min_size：框高度小于图像高度的这个比例就忽略（远处的小脸）。原始结果里有 5 个关键点，
    SFace 对齐人脸时要用。
    """
    h, w = img.shape[:2]
    out = []
    for row in detector.detect_rows(img):
        x1, y1, x2, y2 = clip_box(row, w, h)
        if x2 > x1 and y2 > y1 and (y2 - y1) / h >= min_size:
            out.append(((float(x1), float(y1), float(x2), float(y2)), float(row[14]), row))
    return sorted(out, key=lambda f: -(f[0][2] - f[0][0]) * (f[0][3] - f[0][1]))


def frames(source: str) -> Iterator[Tuple[str, Optional[np.ndarray]]]:
    """
    依次给出 (名字, 画面)：source 可以是摄像头（'0' 或 '/dev/video0'）、视频文件或图片文件夹。

    读不出的图片给出 None，由调用者跳过。
    """
    import cv2

    path = Path(source)
    if path.is_dir():
        for img in list_images(path):
            yield img.name, cv2.imread(str(img))
        return
    if camera_index(source) is None and not path.is_file():
        raise SystemExit(f'找不到 {source}：请给出摄像头编号、视频文件或图片文件夹')
    video = open_video(source)
    i = 0
    try:
        while (frame := video.read()) is not None:
            yield f'frame_{i:06d}.jpg', frame
            i += 1
    finally:
        video.release()


def show_or_save(img: np.ndarray, name: str, save: Optional[Path], show: bool, title: str) -> bool:
    """有 save 时把画好的图片存进这个文件夹，否则在窗口里显示；按了 q 时返回 False（该停下了）。"""
    import cv2

    if save is not None:
        cv2.imwrite(str(ensure_dir(save) / name), img)
    elif show:
        cv2.imshow(title, img)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            return False
    return True


def open_video(source: str) -> VideoSource:
    """
    打开摄像头（编号，如 '0'）或视频文件，与 ROS 的 camera_node 用同一段代码。

    摄像头按 MJPG、640×480 打开：不压缩的默认格式（YUYV）在 WSL2 经 usbipd 转发时传不完整，
    画面下半部分会变成绿色。打不开时按设备的情况说明原因（没转发进来、没有权限……）。
    """
    try:
        return VideoSource(source, loop=False)
    except (FileNotFoundError, RuntimeError) as e:
        raise SystemExit(str(e)) from None


def print_list(title: str, items: List[str], limit: int = 20) -> None:
    """打印一个列表，太长时只列前 limit 项。"""
    if not items:
        return
    print(title + '：')
    for x in items[:limit]:
        print('   ', x)
    if len(items) > limit:
        print(f'    ... 还有 {len(items) - limit} 项')
