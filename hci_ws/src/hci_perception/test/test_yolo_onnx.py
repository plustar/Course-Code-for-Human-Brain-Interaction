"""YOLO 的 ONNX 后端：letterbox、NMS、两种输出格式、微型模型的整条链路、类别名元数据。"""
import importlib.util
from itertools import combinations
import os
import sys

from hci_perception.recognition.base import require
from hci_perception.recognition.yolo_onnx import (decode_yolo_output, letterbox, nms_agnostic,
                                                  OnnxYolo, quiet_stderr, unletterbox)
from hypothesis import given, settings
from hypothesis import strategies as st
import numpy as np
import pytest

needs_onnxruntime = pytest.mark.skipif(importlib.util.find_spec('onnxruntime') is None,
                                       reason='需要 ONNX Runtime（bash env/setup_ros_env.sh）')


def iou(a: np.ndarray, b: np.ndarray) -> float:
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = w * h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return float(inter / union)


# ---------- 几何：letterbox 与坐标还原 ----------
def test_letterbox_roundtrip():
    img = np.zeros((480, 640, 3), np.uint8)
    out, r, pad = letterbox(img, 320)
    assert out.shape == (320, 320, 3)
    box = np.array([[100, 50, 300, 250]], np.float32)  # 原图坐标
    lb = box.copy()
    lb[:, [0, 2]] = lb[:, [0, 2]] * r + pad[0]
    lb[:, [1, 3]] = lb[:, [1, 3]] * r + pad[1]
    assert np.allclose(unletterbox(lb, r, pad, 640, 480), box, atol=1)


def test_letterbox_keeps_aspect_ratio_and_pads_with_gray():
    out, r, (left, top) = letterbox(np.zeros((480, 640, 3), np.uint8), 320)
    assert r == 0.5 and (left, top) == (0, 40)
    assert (out[:40] == 114).all() and (out[40:280] == 0).all() and (out[280:] == 114).all()


def test_unletterbox_clips_to_the_image():
    boxes = np.array([[-20, 30, 400, 400]], np.float32)
    assert unletterbox(boxes, 0.5, (0, 40), 640, 480).tolist() == [[0, 0, 639, 479]]


# ---------- NMS ----------
def test_nms_keeps_the_best_box_across_classes():
    boxes = np.array([[0, 0, 10, 10], [1, 1, 10, 10], [50, 50, 60, 60]], np.float32)
    scores = np.array([0.9, 0.8, 0.7])
    assert nms_agnostic(boxes, scores, 0.5) == [0, 2]


box = st.tuples(st.integers(0, 100), st.integers(0, 100), st.integers(1, 60), st.integers(1, 60))


@settings(max_examples=300, deadline=None)
@given(st.lists(box, max_size=15), st.floats(0.1, 0.9))
def test_nms_invariants(raw, iou_thr):
    boxes = np.array([[x, y, x + w, y + h] for x, y, w, h in raw], np.float32).reshape(-1, 4)
    scores = np.linspace(0.9, 0.1, len(raw))[::-1].copy()  # 分数互不相同
    keep = nms_agnostic(boxes, scores, iou_thr)
    assert len(set(keep)) == len(keep)
    if len(raw):
        assert int(np.argmax(scores)) in keep  # 分数最高的一定保留
    for i, j in combinations(keep, 2):  # 保留下来的框两两重叠不超过阈值
        assert iou(boxes[i], boxes[j]) <= iou_thr + 1e-6
    for k in set(range(len(raw))) - set(keep):  # 去掉的框都和一个分数更高的保留框重叠过多
        assert any(scores[j] > scores[k] and iou(boxes[k], boxes[j]) > iou_thr - 1e-6
                   for j in keep)


# ---------- 两种输出格式 ----------
def test_decode_traditional_format():
    out = np.zeros((1, 6, 3), np.float32)  # (1, 4+2 个类别, 3 个候选)
    out[0, :4, 0], out[0, 4, 0] = [50, 50, 20, 20], 0.9  # 类别 0，高分
    out[0, :4, 1], out[0, 5, 1] = [51, 51, 20, 20], 0.8  # 同一位置的类别 1：被 NMS 去掉
    out[0, :4, 2], out[0, 5, 2] = [200, 200, 30, 30], 0.3  # 低于阈值
    boxes, scores, cls = decode_yolo_output(out, conf_thr=0.5)
    assert len(boxes) == 1 and cls[0] == 0 and np.allclose(boxes[0], [40, 40, 60, 60])


def test_decode_end_to_end_format():
    out = np.zeros((1, 300, 6), np.float32)
    out[0, 0] = [10, 20, 30, 40, 0.95, 1]
    out[0, 1] = [0, 0, 5, 5, 0.1, 0]
    boxes, scores, cls = decode_yolo_output(out, conf_thr=0.5)
    assert len(boxes) == 1 and cls[0] == 1 and scores[0] > 0.9


def test_decode_nothing_above_threshold():
    boxes, scores, cls = decode_yolo_output(np.zeros((1, 6, 8), np.float32), conf_thr=0.5)
    assert boxes.shape == (0, 4) and len(scores) == len(cls) == 0


# ---------- 微型 ONNX 模型的整条链路 ----------
def two_faces() -> np.ndarray:
    """640×480 的画面 letterbox 到 320 后（缩放 0.5、上边填充 40）的两个检测结果。"""
    raw = np.zeros((1, 6, 3), np.float32)
    raw[0, :4, 0], raw[0, 4, 0] = [100, 115, 100, 100], 0.9  # 本人：原图 (100,50)-(300,250)
    raw[0, :4, 1], raw[0, 5, 1] = [200, 140, 40, 40], 0.8  # 他人：原图 (360,160)-(440,240)
    raw[0, :4, 2], raw[0, 5, 2] = [10, 10, 5, 5], 0.1  # 低分，丢掉
    return raw


@needs_onnxruntime
def test_onnx_backend_end_to_end(tiny_yolo):
    model = OnnxYolo(tiny_yolo(two_faces(), names=['stu_2023123456', 'face']), min_confidence=0.5)
    assert model.backend == 'yolo_onnx' and model.names == ['stu_2023123456', 'face']
    dets = model.detect(np.zeros((480, 640, 3), np.uint8))
    assert [(d.class_name, round(d.confidence, 2), d.x1, d.y1, d.x2, d.y2) for d in dets] == [
        ('stu_2023123456', 0.9, 100, 50, 300, 250), ('face', 0.8, 360, 160, 440, 240)]


@needs_onnxruntime
def test_end_to_end_output_format_model(tiny_yolo):
    raw = np.zeros((1, 300, 6), np.float32)
    raw[0, 0] = [50, 65, 150, 165, 0.95, 0]  # 已经是 x1,y1,x2,y2：原图 (100,50)-(300,250)
    dets = OnnxYolo(tiny_yolo(raw, names=['stu_1'])).detect(np.zeros((480, 640, 3), np.uint8))
    assert [(d.class_name, d.x1, d.y1, d.x2, d.y2) for d in dets] == [('stu_1', 100, 50, 300, 250)]


@needs_onnxruntime
def test_fixed_input_size_wins_over_imgsz(tiny_yolo):
    assert OnnxYolo(tiny_yolo(two_faces(), size=320), imgsz=640).imgsz == 320
    assert OnnxYolo(tiny_yolo(two_faces(), size=None), imgsz=416).imgsz == 416  # 动态尺寸


@needs_onnxruntime
def test_class_names_from_argument_or_numbers(tiny_yolo):
    path = tiny_yolo(two_faces())  # 元数据里没有类别名
    assert OnnxYolo(path).names == []
    assert [d.class_name for d in OnnxYolo(path).detect(np.zeros((480, 640, 3), np.uint8))] == [
        '0', '1']
    assert OnnxYolo(path, names=['stu_1', 'face']).names == ['stu_1', 'face']


def test_quiet_stderr_hides_library_noise_and_restores(capfd):
    with quiet_stderr():
        os.write(2, b'Schema error: already registered\n')
    os.write(2, b'still visible\n')
    err = capfd.readouterr().err
    assert 'Schema error' not in err and 'still visible' in err


def test_missing_onnxruntime_explains_how_to_install(monkeypatch):
    monkeypatch.setitem(sys.modules, 'onnxruntime', None)  # 模拟没装 onnxruntime
    with pytest.raises(RuntimeError, match='python3-onnxruntime'):
        require('onnxruntime')
