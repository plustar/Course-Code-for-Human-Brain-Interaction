"""
第 2 步：从各场次视频中抽帧（默认每 12 帧取 1 帧），去掉模糊帧和几乎重复的帧。

用法：python extract_frames.py                  # 处理 data/videos/ 里的全部视频
      python extract_frames.py --every 10 --blur 60
输出：data/self/<场次>/<场次>_000123.jpg
目标：所有场次合计 200–400 张。
"""
import argparse
from pathlib import Path
import sys
from typing import Dict, List, Optional

from common import DATA, ensure_dir, VIDEO_EXT
import cv2
import numpy as np


def sharpness(gray: np.ndarray) -> float:
    """清晰度：拉普拉斯方差，越小越模糊。"""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def extract(video: Path, out: Path, every: int = 12, blur: float = 50.0,
            dup: float = 4.0) -> Dict[str, int]:
    """
    从一段视频里每 every 帧取一帧，保存到 out/<场次>_<帧号>.jpg。

    清晰度低于 blur 的丢弃；与上一张保留的画面平均像素差小于 dup 的视为重复，也丢弃。
    返回各项计数：frames（总帧数）、kept、blurry、duplicate。
    """
    session = video.stem
    ensure_dir(out)
    cap = cv2.VideoCapture(str(video))
    counts = {'frames': 0, 'kept': 0, 'blurry': 0, 'duplicate': 0}
    previous: Optional[np.ndarray] = None
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % every == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            small = cv2.resize(gray, (64, 48)).astype(np.float32)  # 缩略图，用来判断重复
            if sharpness(gray) < blur:
                counts['blurry'] += 1
            elif previous is not None and np.abs(small - previous).mean() < dup:
                counts['duplicate'] += 1
            else:
                cv2.imwrite(str(out / f'{session}_{i:06d}.jpg'), frame)
                counts['kept'] += 1
                previous = small
        i += 1
    cap.release()
    counts['frames'] = i
    return counts


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description='从视频中抽帧，去掉模糊和重复的帧')
    ap.add_argument('--data', default=str(DATA), help='数据文件夹（默认 exercises/face_recognition/data）')
    ap.add_argument('--every', type=int, default=12, help='每隔多少帧取一帧')
    ap.add_argument('--blur', type=float, default=50.0, help='清晰度阈值，低于则丢弃')
    ap.add_argument('--dup', type=float, default=4.0, help='与上一张平均像素差低于此值视为重复')
    a = ap.parse_args(argv)

    data = Path(a.data)
    videos = sorted(p for p in ensure_dir(data / 'videos').iterdir()
                    if p.suffix.lower() in VIDEO_EXT)
    if not videos:
        print(f'{data / "videos"} 里没有视频，请先运行 capture_sessions.py')
        return 1
    total = 0
    for video in videos:
        c = extract(video, data / 'self' / video.stem, a.every, a.blur, a.dup)
        total += c['kept']
        print(f'{video.stem}：共 {c["frames"]} 帧，保留 {c["kept"]}，模糊丢弃 {c["blurry"]}，'
              f'重复丢弃 {c["duplicate"]}')
    print(f'合计保留 {total} 张 -> {data / "self"}')
    if total < 200:
        print('提示：少于 200 张，建议再录 1–2 个场次，或把 --every 调小')
    return 0


if __name__ == '__main__':
    sys.exit(main())
