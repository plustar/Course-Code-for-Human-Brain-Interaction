"""
图像消息与 NumPy 数组互相转换（不依赖 cv_bridge），以及由相机模型生成 CameraInfo。

ROS 里通常用 cv_bridge 做图像转换。这里用几行 NumPy 自己实现，原因有两个：少一个依赖；
更重要的是能看清 sensor_msgs/Image 的内存布局——height 行，每行 step 个字节（行尾可能有
填充），像素按 encoding（如 bgr8）排列。效果等价于 cv_bridge 的 imgmsg_to_cv2 / cv2_to_imgmsg。
"""
import array
from typing import Any, Optional

from hci_common.camera_model import CameraModel
import numpy as np
from sensor_msgs.msg import CameraInfo, CompressedImage, Image
from std_msgs.msg import Header

# 支持的编码 -> 每个像素的通道数
CHANNELS = {'bgr8': 3, 'rgb8': 3, 'bgra8': 4, 'rgba8': 4, 'mono8': 1, '8uc1': 1, '8uc3': 3}


def imgmsg_to_bgr(msg: Any) -> np.ndarray:
    """sensor_msgs/Image -> OpenCV 使用的 BGR 数组 (H, W, 3)，dtype=uint8。"""
    enc = msg.encoding.lower()
    if enc not in CHANNELS:
        raise ValueError(f'不支持的图像编码：{msg.encoding}（支持 {list(CHANNELS)}）')
    ch = CHANNELS[enc]
    buf = np.frombuffer(msg.data, dtype=np.uint8)
    rows = buf.reshape(msg.height, msg.step)  # 每行 step 个字节，行尾可能有填充
    img = rows[:, : msg.width * ch].reshape(msg.height, msg.width, ch)
    if enc in ('bgr8', '8uc3'):
        out = img
    elif enc == 'rgb8':
        out = img[:, :, ::-1]
    elif enc == 'bgra8':
        out = img[:, :, :3]
    elif enc == 'rgba8':
        out = img[:, :, 2::-1]
    else:  # 单通道灰度 -> 复制成三通道
        out = np.repeat(img, 3, axis=2)
    # np.frombuffer 得到的数组是只读的；返回可写的副本，后面画框才不会报错
    return np.array(out, dtype=np.uint8, order='C', copy=True)


def bgr_to_imgmsg(img: np.ndarray, header: Optional[Header] = None) -> Image:
    """BGR 数组 -> sensor_msgs/Image（bgr8）。header 一般复制自输入图像。"""
    if img.dtype != np.uint8 or img.ndim != 3 or img.shape[2] != 3:
        raise ValueError('需要 uint8 的 (H, W, 3) BGR 图像')
    msg = Image()
    if header is not None:
        msg.header = header
    msg.height, msg.width = int(img.shape[0]), int(img.shape[1])
    msg.encoding = 'bgr8'
    msg.is_bigendian = 0
    msg.step = msg.width * 3
    # array('B', bytes) 走 frombytes()，比逐个元素赋值快几个数量级
    msg.data = array.array('B', np.ascontiguousarray(img).tobytes())
    return msg


def compressed_to_bgr(msg: Any) -> np.ndarray:
    """sensor_msgs/CompressedImage（jpeg 或 png）-> BGR 数组。"""
    import cv2

    img = cv2.imdecode(np.frombuffer(msg.data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f'无法解码压缩图像，format={msg.format}')
    return img


def bgr_to_compressed(img: np.ndarray, header: Optional[Header] = None,
                      quality: int = 80) -> CompressedImage:
    """BGR 数组 -> sensor_msgs/CompressedImage（jpeg）。"""
    import cv2

    ok, enc = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise ValueError('JPEG 编码失败')
    msg = CompressedImage()
    if header is not None:
        msg.header = header
    msg.format = 'jpeg'
    msg.data = array.array('B', enc.tobytes())
    return msg


def camera_info_msg(model: CameraModel, header: Optional[Header] = None) -> CameraInfo:
    """由相机模型生成 sensor_msgs/CameraInfo（无畸变的理想针孔相机）。"""
    msg = CameraInfo()
    if header is not None:
        msg.header = header
    msg.width, msg.height = int(model.width), int(model.height)
    msg.distortion_model = 'plumb_bob'
    msg.d = [0.0] * 5
    msg.k = model.k_matrix()
    msg.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
    msg.p = [model.fx, 0.0, model.cx, 0.0, 0.0, model.fy, model.cy, 0.0, 0.0, 0.0, 1.0, 0.0]
    return msg
