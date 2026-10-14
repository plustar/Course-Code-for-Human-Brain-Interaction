"""第 6 步：按录制场次划分训练集与验证集（不泄漏），生成 data.yaml。"""
from pathlib import Path
import shutil

from build_dataset import main, MARKER, split, write
from common import label_path, list_images
import pytest
import yaml


def make_data(root: Path, sessions=('s1', 's2', 's3'), per_session=3, others=10,
              unlabelled=1) -> Path:
    """合成的数据文件夹：每个场次几张本人照片（含没有标注的），加上他人照片。"""
    data = root / 'data'
    for s in sessions:
        for i in range(per_session + unlabelled):
            img = data / 'self' / s / f'{s}_{i:06d}.jpg'
            img.parent.mkdir(parents=True, exist_ok=True)
            img.write_bytes(b'jpg')
            if i < per_session:
                label = label_path(img, data)
                label.parent.mkdir(parents=True, exist_ok=True)
                label.write_text('0 0.5 0.5 0.3 0.4\n')
    for i in range(others):
        img = data / 'others' / 'images' / f'oi_{i:04d}.jpg'
        img.parent.mkdir(parents=True, exist_ok=True)
        img.write_bytes(b'jpg')
        label = label_path(img, data)
        label.parent.mkdir(parents=True, exist_ok=True)
        label.write_text('1 0.5 0.5 0.3 0.4\n1 0.2 0.2 0.1 0.1\n')
    return data


def sessions_in(items):
    return {img.parent.name for img, _ in items if img.parent.parent.name == 'self'}


def test_last_session_is_used_for_validation(tmp_path):
    items, skipped = split(make_data(tmp_path))
    assert sessions_in(items['train']) == {'s1', 's2'} and sessions_in(items['val']) == {'s3'}
    assert skipped == 3  # 每个场次一张没有标注的照片
    others = [img for img, _ in items['val'] if 'others' in img.parts]
    assert len(others) == 2  # 他人照片 20% 做验证


def test_chosen_validation_sessions(tmp_path):
    items, _ = split(make_data(tmp_path), val_sessions=['s1', 's2'])
    assert sessions_in(items['val']) == {'s1', 's2'} and sessions_in(items['train']) == {'s3'}


@pytest.mark.parametrize('sessions, val, hint', [(('s1',), None, '至少需要 2 个场次'),
                                                 (('s1', 's2'), ['s9'], '没有这些场次')])
def test_mistakes_are_explained(tmp_path, sessions, val, hint):
    with pytest.raises(SystemExit, match=hint):
        split(make_data(tmp_path, sessions=sessions), val_sessions=val)


def test_dataset_files_and_yaml(tmp_path):
    items, _ = split(make_data(tmp_path))
    out = tmp_path / 'dataset'
    counts = write(items, out, '2023123456')
    assert counts['train'][0] == 6 and counts['train'][1] == 16  # 本人框、他人框
    assert counts['val'][0] == 3 and counts['val'][1] == 4
    train_images = sorted(p.name for p in (out / 'images' / 'train').iterdir())
    assert not [n for n in train_images if n.startswith('s3_')]  # 验证场次没有混进训练集
    assert len(list((out / 'labels' / 'train').iterdir())) == len(train_images)
    config = yaml.safe_load((out / 'data.yaml').read_text(encoding='utf-8'))
    assert config['names'] == {0: 'stu_2023123456', 1: 'face'}  # Track A 默认
    assert config['train'] == 'images/train' and Path(config['path']) == out.resolve()


def test_other_class_name_is_configurable(tmp_path):
    """Track B 一等公民：--other-class 决定第 1 类名字，核心流程不变。"""
    items, _ = split(make_data(tmp_path))
    out = tmp_path / 'dataset'
    write(items, out, '2023123456', other_class='other')
    config = yaml.safe_load((out / 'data.yaml').read_text(encoding='utf-8'))
    assert config['names'] == {0: 'stu_2023123456', 1: 'other'}


def test_regenerating_replaces_the_previous_dataset(tmp_path):
    items, _ = split(make_data(tmp_path))
    out = tmp_path / 'dataset'
    write(items, out, '2023123456')
    (out / 'images' / 'train' / 'stale.jpg').write_bytes(b'old')
    write(items, out, '2023123456')
    assert not (out / 'images' / 'train' / 'stale.jpg').exists()


def test_a_folder_it_did_not_make_is_never_deleted(tmp_path):
    # --out 写错（例如写成 data 或别的文件夹）：拒绝执行，照片一张不少
    data = make_data(tmp_path)
    items, _ = split(data)
    for out in (data, tmp_path / 'notes'):
        out.mkdir(exist_ok=True)
        (out / 'mine.txt').write_text('mine')
        before = sorted(tmp_path.rglob('*'))
        with pytest.raises(SystemExit, match='不是 build_dataset.py 生成'):
            write(items, out, '2023123456')
        assert sorted(tmp_path.rglob('*')) == before


def test_photos_inside_the_output_folder_are_never_deleted(tmp_path):
    out = tmp_path / 'dataset'
    data = make_data(out)  # 原始照片放在了 dataset/data 里
    (out / 'data.yaml').write_text(MARKER + '\n', encoding='utf-8')
    items, _ = split(data)
    with pytest.raises(SystemExit, match='原始照片'):
        write(items, out, '2023123456')
    assert list_images(data / 'self' / 's1')


def test_an_interrupted_run_can_be_started_again(tmp_path, monkeypatch):
    # 复制到一半中断（Ctrl+C、磁盘满）：再运行一次时照常删掉重来，而不是说"不是它生成的"
    items, _ = split(make_data(tmp_path))
    out = tmp_path / 'dataset'

    def disk_full(src, dst):
        raise OSError('磁盘已满')

    monkeypatch.setattr(shutil, 'copy2', disk_full)
    with pytest.raises(OSError):
        write(items, out, '2023123456')
    assert not yaml.safe_load((out / 'data.yaml').read_text(encoding='utf-8'))  # 只有标记，没有 train
    monkeypatch.undo()
    counts = write(items, out, '2023123456')
    assert counts['train'][0] == 6


def test_command_line_checks_the_student_id(tmp_path, capsys):
    data = make_data(tmp_path)
    with pytest.raises(SystemExit, match='学号'):
        main(['--student-id', '2023 123', '--data', str(data)])
    assert main(['--student-id', '2023123456', '--data', str(data),
                 '--out', str(tmp_path / 'dataset')]) == 0
    out = capsys.readouterr().out
    assert '3 张本人照片没有标注' in out and 'train.py' in out
