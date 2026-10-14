"""画框、中文标签、状态条与打码：配色、没有中文字体时的退路、标签避让、马赛克。"""
from typing import Tuple

from hci_perception import overlay
from hci_perception.overlay import (find_font, GREEN, Label, layout_labels, ORANGE, overlap,
                                    Painter, pixelate)
from hypothesis import given, settings
from hypothesis import strategies as st
import numpy as np
import pytest


def rgb_at(bgr: np.ndarray, x: int, y: int) -> Tuple[int, ...]:
    return tuple(int(v) for v in bgr[y, x, ::-1])


def test_target_is_green_and_others_are_orange():
    img = np.zeros((120, 200, 3), np.uint8)
    out = Painter().draw(img, [Label((20, 40, 80, 100), '张三 0.90', True),
                               Label((120, 40, 180, 100), '他人 0.80', False)])
    assert rgb_at(out, 20, 70) == GREEN and rgb_at(out, 120, 70) == ORANGE  # 两个框的左边
    assert out.shape == img.shape and not img.any()  # 画在新图上，不改原图


def test_without_a_chinese_font_it_still_draws(monkeypatch):
    monkeypatch.setattr(overlay, 'FONT_CANDIDATES', [])
    painter = Painter()
    assert painter.font_file is None  # 中文会显示成方块，但不会出错
    labels = [Label((5, 20, 40, 50), 'face 0.9', False)]
    out = painter.draw(np.zeros((60, 80, 3), np.uint8), labels)
    assert out.any()


def test_find_font_prefers_the_given_file(tmp_path):
    font = tmp_path / 'my_font.ttf'
    font.write_bytes(b'x')
    assert find_font(str(font)) == str(font)
    assert find_font('/no/such/font.ttf') in overlay.FONT_CANDIDATES + [None]


def test_labels_of_nearby_boxes_do_not_overlap():
    boxes = [(100, 60, 150, 120), (130, 55, 180, 110), (600, 2, 639, 40)]  # 前两个框挨得很近
    rects = layout_labels(boxes, [(120, 26)] * 3, 640, 360)
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            assert not overlap(rects[i], rects[j])
    assert all(0 <= r[0] and r[2] <= 640 and 0 <= r[1] and r[3] <= 360 for r in rects)  # 不出画面


box = st.tuples(st.integers(0, 600), st.integers(0, 440),  # 左上角
                st.integers(10, 200), st.integers(10, 200))  # 宽、高


@settings(max_examples=200, deadline=None)
@given(st.lists(box, min_size=1, max_size=8))
def test_label_layout_invariants(raw):
    boxes = [(x, y, min(x + w, 639), min(y + h, 479)) for x, y, w, h in raw]
    rects = layout_labels(boxes, [(90, 24)] * len(boxes), 640, 480)
    for i, (rect, (x1, y1, x2, y2)) in enumerate(zip(rects, boxes)):
        assert rect[2] - rect[0] == 90 and rect[3] - rect[1] == 24
        assert 0 <= rect[0] and rect[2] <= 640  # 左右不出画面
        # 要么与先放好的标签都不重叠，要么是实在放不下时的退路：框内顶部
        assert (not any(overlap(rect, r) for r in rects[:i])) or rect[1] == y1 + 2


def test_status_bar_tints_the_bottom_only():
    img = np.full((240, 320, 3), 255, np.uint8)
    out = Painter().status_bar(img, '靠近：已对准', '你好，张三！', color=(47, 128, 237))
    assert (out[:120] == 255).all()
    r, g, b = rgb_at(out, 318, 238)
    assert b > r and b > g  # 底色是蓝色的半透明叠加


def test_status_bar_is_shorter_with_one_line():
    painter = Painter()
    white = np.full((240, 320, 3), 255, np.uint8)
    one = painter.status_bar(white, '停车：没有确认看到本人')
    two = painter.status_bar(white, '问候：到达问候距离', '你好，张三！')
    rows_tinted = [int((img[:, 5] != 255).any(axis=1).sum()) for img in (one, two)]
    assert 0 < rows_tinted[0] < rows_tinted[1]


def test_pixelate_makes_blocks_only_inside_the_box():
    img = np.random.default_rng(0).integers(0, 256, (100, 120, 3), np.uint8)
    out = pixelate(img, [(10, 10, 74, 74)], blocks=8)
    region = out[10:74, 10:74].reshape(8, 8, 8, 8, 3)  # 8×8 个色块，每块 8×8 像素
    assert (region == region[:, :1, :, :1]).all()  # 每个色块内部颜色相同
    outside = np.ones(img.shape[:2], bool)
    outside[10:74, 10:74] = False
    assert np.array_equal(out[outside], img[outside]) and not np.array_equal(out, img)


@pytest.mark.parametrize('boxes', [[(5, 5, 6, 6)], [(-30, -30, -1, -1)], []])
def test_pixelate_ignores_tiny_or_outside_boxes(boxes):
    img = np.random.default_rng(1).integers(0, 256, (50, 60, 3), np.uint8)
    assert np.array_equal(pixelate(img, boxes), img)


def test_pixelate_clips_boxes_at_the_border():
    img = np.random.default_rng(2).integers(0, 256, (50, 60, 3), np.uint8)
    out = pixelate(img, [(40, 30, 90, 80)])
    assert out.shape == img.shape and not np.array_equal(out[30:, 40:], img[30:, 40:])
