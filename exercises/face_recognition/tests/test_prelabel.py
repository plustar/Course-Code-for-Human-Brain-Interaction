"""第 3 步：用 YuNet 预标注，标签位置与图片对应；只标最大的脸；没有人脸、多张人脸的提醒。"""
from common import from_yolo_line, label_path, read_labels
import cv2
import numpy as np
from prelabel_yunet import main, prelabel
from synthetic import face_frame, write_faces


def test_each_image_gets_a_yolo_label(tmp_path):
    images = write_faces(tmp_path / 'self' / 's1', n=3)
    result = prelabel(tmp_path / 'self', class_id=0, data=tmp_path, largest_only=True)
    assert (result.images, result.boxes, result.no_face, result.many_faces) == (3, 3, [], [])
    for img in images:
        (line,) = read_labels(label_path(img, tmp_path))
        cls_id, (x1, y1, x2, y2) = from_yolo_line(line, 640, 480)
        assert cls_id == 0 and x1 < (x1 + x2) / 2 < x2  # 框在人脸上
        assert 115 <= (y1 + y2) / 2 <= 364
    assert (tmp_path / 'classes.txt').read_text() == 'stu_self\nface\n'


def test_largest_only_and_multiple_faces(tmp_path):
    frame = face_frame(x=20, y=20)
    frame[280:400, 480:600] = cv2.resize(face_frame()[115:364, 195:444], (120, 120))
    folder = tmp_path / 'self' / 's1'
    folder.mkdir(parents=True)
    cv2.imwrite(str(folder / 'two.jpg'), frame)
    cv2.imwrite(str(folder / 'none.jpg'), np.full((480, 640, 3), 128, np.uint8))
    every_face = prelabel(tmp_path / 'self', 1, tmp_path)
    assert every_face.boxes == 2 and len(every_face.many_faces) == 1
    assert every_face.no_face == [str(folder / 'none.jpg')]
    largest = prelabel(tmp_path / 'self', 0, tmp_path, largest_only=True)
    assert largest.boxes == 1  # 画面里偶尔出现的别人不会被标成本人
    assert read_labels(label_path(folder / 'none.jpg', tmp_path)) == []


def test_command_line(tmp_path, capsys):
    write_faces(tmp_path / 'self' / 's1', n=2)
    assert main(['--images', str(tmp_path / 'self'), '--class-id', '0', '--largest-only',
                 '--data', str(tmp_path)]) == 0
    assert '处理 2 张，共 2 个框' in capsys.readouterr().out
