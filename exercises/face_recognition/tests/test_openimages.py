"""第 5 步：他人人脸——解析 Open Images 的框标注 CSV（不联网），以及从文件夹导入已获同意的照片。"""
import csv

from common import OTHERS_ID, read_labels
from get_openimages_faces import candidates, from_folder, load_face_boxes, yolo_lines
import numpy as np
from synthetic import write_faces

FACE, CAR = '/m/0dzct', '/m/0k4j'
FIELDS = ['ImageID', 'Source', 'LabelName', 'Confidence', 'XMin', 'XMax', 'YMin', 'YMax',
          'IsOccluded', 'IsTruncated', 'IsGroupOf', 'IsDepiction', 'IsInside']


def write_csv(path, rows):
    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, FIELDS)
        writer.writeheader()
        for image_id, label, (x1, y1, x2, y2), group in rows:
            writer.writerow({'ImageID': image_id, 'Source': 'human', 'LabelName': label,
                             'Confidence': 1, 'XMin': x1, 'XMax': x2, 'YMin': y1, 'YMax': y2,
                             'IsOccluded': 0, 'IsTruncated': 0, 'IsGroupOf': group,
                             'IsDepiction': 0, 'IsInside': 0})


def test_only_suitable_face_images_are_chosen(tmp_path):
    path = tmp_path / 'boxes.csv'
    big, small = (0.1, 0.1, 0.3, 0.4), (0.5, 0.5, 0.52, 0.53)
    write_csv(path, [
        ('good', FACE, big, 0),
        ('good', CAR, (0.0, 0.0, 1.0, 1.0), 0),  # 别的类别：忽略
        ('crowd', FACE, big, 1),  # "一群脸"用一个大框标注：整张图不用
        ('tiny', FACE, small, 0),  # 脸太小
        ('many', FACE, big, 0), *[('many', FACE, small, 0)] * 4,  # 脸太多
        ('car_only', CAR, big, 0),
    ])
    boxes, group = load_face_boxes(path)
    assert set(boxes) == {'good', 'crowd', 'tiny', 'many'} and group == {'crowd'}
    assert boxes['good'] == [big]
    assert candidates(boxes, group, min_face=0.12, max_faces=4) == ['good']


def test_candidates_are_shuffled_reproducibly():
    boxes = {f'img{i}': [(0.1, 0.1, 0.3, 0.4)] for i in range(20)}
    first = candidates(boxes, set(), seed=1)
    assert sorted(first) == sorted(boxes) and first == candidates(boxes, set(), seed=1)
    assert first != candidates(boxes, set(), seed=2)


def test_boxes_become_face_labels():
    line = yolo_lines([(0.1, 0.2, 0.3, 0.6)])
    cls_id, cx, cy, w, h = line.split()
    assert int(cls_id) == OTHERS_ID
    assert np.allclose([float(v) for v in (cx, cy, w, h)], [0.2, 0.4, 0.2, 0.4])


def test_photos_from_a_folder_are_labelled_as_others(tmp_path):
    write_faces(tmp_path / 'friends', n=2)
    (tmp_path / 'friends' / 'empty.jpg').write_bytes(b'not an image')
    out_img, out_lab = tmp_path / 'images', tmp_path / 'labels'
    out_img.mkdir()
    out_lab.mkdir()
    assert from_folder(tmp_path / 'friends', out_img, out_lab) == 2
    for label in sorted(out_lab.iterdir()):
        assert [line.split()[0] for line in read_labels(label)] == [str(OTHERS_ID)]
    # 同一个文件夹再导入一次：已经导入过的不重复加入（重复的照片可能同时进训练集和验证集）
    assert from_folder(tmp_path / 'friends', out_img, out_lab) == 0
    # 再从另一个文件夹导入一批：不覆盖前一批
    write_faces(tmp_path / 'classmates', n=2, flip=True)
    assert from_folder(tmp_path / 'classmates', out_img, out_lab) == 2
    assert len(list(out_img.iterdir())) == len(list(out_lab.iterdir())) == 4
