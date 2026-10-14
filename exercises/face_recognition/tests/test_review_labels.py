"""第 4 步：人工检查标注——进度记录不漏看；空格通过、x 删除、b 回退、q 退出。"""
from pathlib import Path
from typing import Iterator

from common import label_path
import numpy as np
from review_labels import draw, load_reviewed, next_unreviewed, rel_key, review, save_reviewed
from synthetic import write_faces


def test_review_progress(tmp_path):
    root = tmp_path / 'self'
    (root / 's1').mkdir(parents=True)
    imgs = []
    for i in range(6):
        f = root / 's1' / f's1_{i:06d}.jpg'
        f.write_bytes(b'x')
        imgs.append(f)
    state = root / '.review_progress.json'
    save_reviewed(state, {rel_key(p, root) for p in imgs[:3]})  # 检查了前 3 张
    imgs[3].unlink()  # 删掉第 4 张
    assert next_unreviewed(imgs, load_reviewed(state), root) == 4  # 从第 5 张继续，不漏看
    # 用绝对路径或相对路径运行都一样
    other = [Path(str(p).replace(str(tmp_path), str(tmp_path.resolve()))) for p in imgs]
    assert next_unreviewed(other, load_reviewed(state), root.resolve()) == 4
    # 全部检查完之后又新增了一个场次：新图片会被显示
    save_reviewed(state, {rel_key(p, root) for p in imgs if p.exists()})
    (root / 's0').mkdir()
    new = root / 's0' / 's0_000000.jpg'
    new.write_bytes(b'x')
    all_imgs = sorted([p for p in imgs if p.exists()] + [new])
    assert all_imgs[next_unreviewed(all_imgs, load_reviewed(state), root)] == new


def press(keys: str) -> Iterator[int]:
    """按预定的顺序"按键"：空格通过，x 删除，b 回退，q 退出。"""
    return iter(ord(k) for k in keys)


def test_keys_pass_delete_back_and_quit(tmp_path):
    root = tmp_path / 'self'
    imgs = write_faces(root / 's1', n=4)
    for img in imgs:
        label = label_path(img, tmp_path)
        label.parent.mkdir(parents=True, exist_ok=True)
        label.write_text('0 0.5 0.5 0.4 0.5\n')
    shown = []
    keys = press(' xb q')  # 通过第 1 张，删除第 2 张，回退到第 1 张，再通过它，然后退出

    def fake_key(img: np.ndarray) -> int:
        shown.append(img.shape)
        return next(keys)

    done, left = review(root, tmp_path, key=fake_key)
    assert (done, left) == (2, 2) and len(shown) == 5
    assert not imgs[1].exists() and (tmp_path / 'rejected' / imgs[1].name).exists()
    assert (tmp_path / 'rejected' / f'{imgs[1].stem}.txt').exists()  # 标签跟着移走
    # 下次从没检查过的第 3 张开始
    seen = []
    review(root, tmp_path, key=lambda img: seen.append(img) or ord('q'))
    assert len(seen) == 1 and load_reviewed(root / '.review_progress.json') == {
        's1/img_000.jpg', 's1/img_001.jpg'}


def test_an_unreadable_image_is_moved_aside(tmp_path):
    root = tmp_path / 'self'
    imgs = write_faces(root / 's1', n=2)
    imgs[0].write_bytes(b'not an image')  # 例如复制时中断
    shown = []
    done, left = review(root, tmp_path, key=lambda img: shown.append(img) or ord(' '))
    assert (done, left) == (2, 0) and len(shown) == 1  # 坏图片不显示，也不让程序崩溃
    assert not imgs[0].exists() and (tmp_path / 'rejected' / imgs[0].name).exists()


def test_draw_boxes_from_the_label(tmp_path):
    label = tmp_path / 'a.txt'
    label.write_text('0 0.5 0.5 0.25 0.25\n1 0.2 0.2 0.1 0.1\n')
    img = np.zeros((100, 100, 3), np.uint8)
    out = draw(img, label)
    assert tuple(out[50, 38]) == (96, 174, 39)  # 本人框的左边是绿色
    assert not img.any() and out.any()
    assert not draw(img, tmp_path / 'missing.txt').any()
