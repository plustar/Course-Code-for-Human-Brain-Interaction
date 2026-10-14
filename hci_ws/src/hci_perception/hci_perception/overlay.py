"""
在画面上画框、中文标签和状态条，并给他人的脸打码（OpenCV 的 putText 不支持中文，所以用 PIL）。

颜色约定（与课件一致）：本人绿框，他人橙框。
"""
from dataclasses import dataclass
import os
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np
from PIL import Image, ImageDraw, ImageFont

Box = Tuple[int, int, int, int]  # x1, y1, x2, y2
Rect = Tuple[int, int, int, int]
Font = Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]

GREEN = (39, 174, 96)  # RGB：本人
ORANGE = (255, 159, 28)  # RGB：他人

# 常见中文字体位置：Ubuntu 可用 sudo apt install fonts-noto-cjk 安装
FONT_CANDIDATES = [
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
]


@dataclass(frozen=True)
class Label:
    """要画的一个框：位置、标签文字、是不是本人。"""

    box: Box
    text: str
    target: bool


def find_font(path: str = '') -> Optional[str]:
    """返回可用的中文字体文件；都找不到时返回 None。"""
    for candidate in ([path] if path else []) + FONT_CANDIDATES:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


class Painter:
    """用 PIL 在 BGR 图像上画框、中文标签和状态条。"""

    def __init__(self, font_path: str = '', font_size: int = 22) -> None:
        self.font_file = find_font(font_path)
        self.font: Font
        self.small: Font
        if self.font_file:
            self.font = ImageFont.truetype(self.font_file, font_size)
            self.small = ImageFont.truetype(self.font_file, int(font_size * 0.8))
        else:  # 找不到中文字体：英文正常，中文会显示成方块
            self.font = self.small = ImageFont.load_default()

    def draw(self, bgr: np.ndarray, labels: Sequence[Label]) -> np.ndarray:
        """画框和标签，返回新图像；标签自动避让，不出画面。"""
        img = Image.fromarray(np.ascontiguousarray(bgr[:, :, ::-1]))  # BGR -> RGB
        draw = ImageDraw.Draw(img)
        for label in labels:  # 先画所有的框
            draw.rectangle(list(label.box), outline=_color(label), width=3)
        ordered = sorted(labels, key=lambda lb: not lb.target)  # 本人的标签优先占好位置
        text_boxes = [draw.textbbox((0, 0), lb.text, font=self.font) for lb in ordered]
        sizes = [(int(tb[2] - tb[0]) + 8, int(tb[3] - tb[1]) + 6) for tb in text_boxes]
        rects = layout_labels([lb.box for lb in ordered], sizes, img.size[0], img.size[1])
        for label, tb, rect in zip(ordered, text_boxes, rects):
            draw.rectangle(list(rect), fill=_color(label))
            draw.text((rect[0] + 4, rect[1] + 3 - tb[1]), label.text, font=self.font,
                      fill=(255, 255, 255))
        return np.ascontiguousarray(np.asarray(img)[:, :, ::-1])  # RGB -> BGR

    def status_bar(self, bgr: np.ndarray, line1: str, line2: str = '',
                   color: Tuple[int, int, int] = (60, 60, 60)) -> np.ndarray:
        """在画面底部画一条半透明的状态条：第一行状态，第二行问候语（可以为空）。"""
        img = Image.fromarray(np.ascontiguousarray(bgr[:, :, ::-1])).convert('RGBA')
        layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        w, h = img.size
        lines = [t for t in (line1, line2) if t]
        line_h = draw.textbbox((0, 0), '状态', font=self.small)[3] + 8
        top = h - line_h * len(lines) - 8
        draw.rectangle([0, top, w, h], fill=(*color, 190))
        for i, text in enumerate(lines):
            draw.text((10, top + 4 + i * line_h), text, font=self.small, fill=(255, 255, 255, 255))
        out = Image.alpha_composite(img, layer).convert('RGB')
        return np.ascontiguousarray(np.asarray(out)[:, :, ::-1])


def _color(label: Label) -> Tuple[int, int, int]:
    return GREEN if label.target else ORANGE


def pixelate(bgr: np.ndarray, boxes: Sequence[Box], blocks: int = 8) -> np.ndarray:
    """给这些框里的内容打马赛克（每个框缩成约 blocks×blocks 个色块），返回新图像。"""
    import cv2

    out = bgr.copy()
    h, w = out.shape[:2]
    for x1, y1, x2, y2 in boxes:
        x1, y1 = max(int(x1), 0), max(int(y1), 0)
        x2, y2 = min(int(x2), w), min(int(y2), h)
        if x2 - x1 < 2 or y2 - y1 < 2:
            continue
        bw, bh = x2 - x1, y2 - y1
        cell = max(1, max(bw, bh) // blocks)  # 每个色块的边长（像素）
        small = cv2.resize(out[y1:y2, x1:x2], (max(1, bw // cell), max(1, bh // cell)),
                           interpolation=cv2.INTER_AREA)
        out[y1:y2, x1:x2] = cv2.resize(small, (bw, bh), interpolation=cv2.INTER_NEAREST)
    return out


def layout_labels(boxes: Sequence[Box], sizes: Sequence[Tuple[int, int]], width: int,
                  height: int) -> List[Rect]:
    """
    按顺序给每个框安排标签的位置：先试框的上方，再试下方，最后放在框内顶部，避开已放好的标签。

    boxes：[(x1, y1, x2, y2), ...]；sizes：[(标签宽, 标签高), ...]；返回标签矩形的列表。
    """
    placed: List[Rect] = []
    for (x1, y1, _x2, y2), (lw, lh) in zip(boxes, sizes):
        lx = int(min(max(x1, 0), max(width - lw, 0)))  # 不超出左右边界
        rect = (lx, int(y1) + 2, lx + lw, int(y1) + 2 + lh)
        for ly in (y1 - lh - 2, y2 + 2, y1 + 2):
            candidate = (lx, int(ly), lx + lw, int(ly) + lh)
            if (ly >= 0 and ly + lh <= height
                    and not any(overlap(candidate, r) for r in placed)):
                rect = candidate
                break
        placed.append(rect)
    return placed


def overlap(a: Rect, b: Rect) -> bool:
    """两个矩形是否重叠。"""
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
