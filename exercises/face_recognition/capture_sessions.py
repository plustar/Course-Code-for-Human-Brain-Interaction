"""
第 1 步：分场次录制自己的人脸视频（每次换光照、背景、角度、表情、眼镜）。

用法：python capture_sessions.py --session s1 --seconds 20
      python capture_sessions.py --session s2 --seconds 20 --source 0
输出：data/videos/s1.mp4 ……
建议：录 4–6 次，每次 15–30 秒；录制时慢慢转头、抬头低头、换表情，偶尔离镜头远一点。
WSL2 摄像头打不开时：用手机或 Windows 自带的"相机"应用录制，把视频复制到 data/videos/，
按场次命名为 s1.mp4、s2.mp4……
隐私：视频只保存在本机，不要上传到网上。
"""
import argparse
from pathlib import Path
import sys
import time
from typing import List, Optional

from common import DATA, ensure_dir, open_video
import cv2

TIPS = ['慢慢向左转头', '慢慢向右转头', '抬头 / 低头', '换个表情', '离镜头远一点', '再靠近一点']


def record(source: str, path: Path, seconds: float, fps: float, show: bool = True) -> int:
    """从摄像头（也可以是视频文件）录制 seconds 秒，保存到 path，返回录到的帧数。"""
    video = open_video(source)  # 摄像头打不开时，提示里会说明原因
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), fps, video.size)
    if not writer.isOpened():  # 否则每一帧都写不进去，最后却报告"已保存"
        video.release()
        raise SystemExit(f'无法写入 {path}：文件夹不能写，或者 OpenCV 不支持 mp4v 编码'
                         '（训练环境里重新运行 bash env/setup_conda.sh）')
    n, t0 = 0, time.monotonic()
    try:
        while time.monotonic() - t0 < seconds:
            frame = video.read()
            if frame is None:
                break
            writer.write(frame)
            n += 1
            if show:
                elapsed = time.monotonic() - t0
                preview = frame.copy()
                cv2.putText(preview, f'REC {seconds - elapsed:4.1f}s', (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                cv2.imshow('capture (q to stop)', preview)
                tip = TIPS[int(elapsed // 4) % len(TIPS)]
                print(f'\r剩余 {seconds - elapsed:4.1f} s  提示：{tip}      ', end='')
                if cv2.waitKey(int(1000 / fps)) & 0xFF == ord('q'):
                    break
    finally:
        video.release()
        writer.release()
        if show:
            cv2.destroyAllWindows()
    return n


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description='分场次录制自己的人脸视频')
    ap.add_argument('--session', required=True, help='场次名，如 s1')
    ap.add_argument('--seconds', type=float, default=20)
    ap.add_argument('--source', default='0', help='摄像头编号')
    ap.add_argument('--fps', type=float, default=15)
    ap.add_argument('--data', default=str(DATA), help='数据文件夹（默认 exercises/face_recognition/data）')
    a = ap.parse_args(argv)

    path = ensure_dir(Path(a.data) / 'videos') / f'{a.session}.mp4'
    n = record(a.source, path, a.seconds, a.fps)
    print(f'\n已保存 {path}（{n} 帧）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
