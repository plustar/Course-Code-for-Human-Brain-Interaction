"""
仓库卫生：个人数据不进仓库，旧名字不残留，各包的版本与许可证一致，换行统一为 LF。

照片、视频、人脸特征、权重、录包都不进仓库；随仓库发布的二进制文件只有两个，都有明确的许可，
第三方文件的许可全文随仓库提供。
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Iterator, List, Set
import xml.etree.ElementTree as ET

import pytest

REPO = Path(__file__).resolve().parents[1]
ALLOWED_BINARIES = {
    'hci_ws/src/hci_common/hci_common/data/sample_face.jpg',  # NASA 公有领域照片
    'hci_ws/src/hci_perception/hci_perception/models/face_detection_yunet_2023mar.onnx',  # MIT
}
PERSONAL = ('.jpg', '.jpeg', '.png', '.heic', '.heif', '.webp', '.bmp', '.tif', '.tiff', '.gif',
            '.avif', '.mp4', '.m4v', '.avi', '.mov', '.mkv', '.wmv', '.webm', '.3gp', '.npy',
            '.pt', '.pth', '.onnx', '.zip', '.7z', '.rar', '.tar', '.tgz', '.gz', '.mcap', '.db3')
# 学生可能放进仓库的个人数据。手机和 Windows 常用大写扩展名（IMG_0001.JPG、VID_0001.MOV）
PERSONAL_SAMPLES = [
    'exercises/face_recognition/data/self/s1/s1_000001.jpg',
    'exercises/face_recognition/data/notes.txt',
    'exercises/face_recognition/dataset/data.yaml',
    'exercises/face_recognition/runs/me/weights/best.pt',
    'IMG_0001.JPG', 'photos/IMG_0002.HEIC', 'me.jpeg', 'me.png', 'me.webp', 'clip.MP4',
    'VID_0001.MOV', 'clip.mkv', 'clip.3gp', 'me.gif', 'me.avif', 'photos.zip', 'Photos.ZIP',
    'data.7z', 'data.tar.gz', 'best.onnx', 'BEST.ONNX', 'last.pth', 'me_sface.npy',
    'rosbag2_2026_10_04/metadata.yaml', 'bag.mcap', 'hci_ws/build/x', 'hci_ws/install/setup.bash',
]
TEXT_SUFFIXES = ('.py', '.md', '.sh', '.yaml', '.yml', '.xml', '.txt', '.ini', '.cfg', '.json',
                 '.typed', '.gitignore', '.gitattributes')
OLD_NAMES = ['hci_vision', 'yolo_node', 'display_node', 'response_node', 'vision.launch.py',
             'bringup.launch.py', 'models/download_models.sh', 'conf_threshold',
             'target_box_ratio', 'max_linear', '/hci/state']
DESIGN_NOTES = {'docs/ARCHITECTURE.md'}  # 里面有新旧名字的对照表


def tracked_files() -> List[str]:
    if shutil.which('git') is None or not (REPO / '.git').exists():
        pytest.skip('不是 git 仓库（例如下载的 zip）：跳过只对 git 跟踪的文件做的检查')
    out = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard'],
                         cwd=REPO, capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if (REPO / line).is_file()]


def test_no_personal_data_in_the_repository():
    found = [f for f in tracked_files()
             if f.lower().endswith(PERSONAL) and f not in ALLOWED_BINARIES]
    assert not found, f'这些文件看起来是个人数据，不能放进仓库：{found}'


def test_the_two_bundled_files_are_present():
    assert ALLOWED_BINARIES <= set(tracked_files())


def ignored(paths: List[str], tmp: Path) -> Set[str]:
    """按仓库的 .gitignore，这些路径里哪些会被 git 忽略（在临时仓库里检查，压缩包里也能运行）。"""
    if shutil.which('git') is None:
        pytest.skip('没有安装 git')
    subprocess.run(['git', 'init', '-q', str(tmp)], check=True)
    shutil.copy(REPO / '.gitignore', tmp / '.gitignore')
    result = subprocess.run(['git', 'check-ignore', '--no-index', '--stdin'], cwd=tmp,
                            input='\n'.join(paths), capture_output=True, text=True)
    assert result.returncode in (0, 1), result.stderr  # 0：有被忽略的，1：一个也没有
    return set(result.stdout.splitlines())


def test_gitignore_keeps_personal_data_out(tmp_path):
    missed = set(PERSONAL_SAMPLES) - ignored(PERSONAL_SAMPLES, tmp_path)
    assert not missed, f'这些个人数据没有被 .gitignore 挡住：{sorted(missed)}'


def test_gitignore_keeps_the_files_that_belong_to_the_repository(tmp_path):
    keep = sorted(ALLOWED_BINARIES) + ['README.md', 'exercises/face_recognition/train.py']
    assert not ignored(keep, tmp_path)


def repo_text_files() -> Iterator[Path]:
    """仓库里的文本文件（不含编译产物、练习 3 的数据和 git 自己的文件）。"""
    skip = {'.git', 'build', 'install', 'log', 'data', 'dataset', 'runs', 'out', '__pycache__',
            '.pytest_cache', '.hypothesis'}
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in skip]
        yield from (Path(root) / name for name in files if name.endswith(TEXT_SUFFIXES))


def test_line_endings_are_lf():
    # Windows 上的编辑器或 git 设置可能把换行改成 CRLF，脚本在 Ubuntu 里就会出错
    crlf = [str(p.relative_to(REPO)) for p in repo_text_files() if b'\r\n' in p.read_bytes()]
    assert not crlf, f'这些文件的换行是 CRLF，请改成 LF：{crlf}'
    rules = (REPO / '.gitattributes').read_text(encoding='utf-8').splitlines()
    assert '* text=auto eol=lf' in rules  # 在 Windows 上 git clone 也按 LF 检出


def test_scripts_are_executable_in_git():
    if shutil.which('git') is None or not (REPO / '.git').exists():
        pytest.skip('不是 git 仓库（例如下载的 zip）：跳过只对 git 跟踪的文件做的检查')
    out = subprocess.run(['git', 'ls-files', '-s', '--', '*.sh'], cwd=REPO, capture_output=True,
                         text=True, check=True).stdout
    modes = {line.split('\t')[1]: line.split()[0] for line in out.splitlines()}
    assert modes and all(mode == '100755' for mode in modes.values()), modes


def test_no_leftover_old_names():
    hits = []
    for f in tracked_files():
        if f in DESIGN_NOTES or not f.endswith(('.py', '.md', '.sh', '.yaml', '.xml', '.txt',
                                                '.ini', '.cfg', '.yml')):
            continue
        if f == 'tests/test_repo_hygiene.py':
            continue
        text = (REPO / f).read_text(encoding='utf-8')
        hits += [f'{f}：{name.strip()}' for name in OLD_NAMES if name in text]
    assert not hits, '这些地方还在用第 1 版的名字：\n' + '\n'.join(hits)


def test_packages_share_version_and_license():
    versions, licenses = set(), set()
    for xml in sorted((REPO / 'hci_ws' / 'src').glob('*/package.xml')):
        root = ET.parse(xml).getroot()
        versions.add(root.findtext('version'))
        licenses.add(root.findtext('license'))
        email = root.find('maintainer').get('email', '')
        assert email.endswith('@example.com'), f'{xml}：维护者邮箱请用占位地址，不要写个人邮箱'
    assert len(versions) == 1 and len(licenses) == 1
    setups = [p.read_text(encoding='utf-8') for p in (REPO / 'hci_ws' / 'src').glob('*/setup.py')]
    assert {re.search(r"version='([^']+)'", text).group(1) for text in setups} == versions
    emails = {re.search(r"maintainer_email='([^']+)'", text).group(1) for text in setups}
    assert all(email.endswith('@example.com') for email in emails), emails


def test_third_party_files_come_with_their_license_texts():
    # MIT 和 Apache-2.0 都要求随附许可全文；MIT 还要求保留原作者的版权声明
    models = REPO / 'hci_ws/src/hci_perception/hci_perception/models'
    yunet = (models / 'LICENSE-YuNet.txt').read_text(encoding='utf-8')
    assert 'Copyright (c) 2020 Shiqi Yu' in yunet and 'Permission is hereby granted' in yunet
    setup = (REPO / 'hci_ws/src/hci_perception/setup.py').read_text(encoding='utf-8')
    assert "'models/*.txt'" in setup  # 随模型一起安装
    apache = (REPO / 'LICENSES' / 'Apache-2.0.txt').read_text(encoding='utf-8')
    assert 'Apache License' in apache and 'Version 2.0, January 2004' in apache
    templates = [p for p in (REPO / 'hci_ws' / 'src').glob('*/test/test_*.py')
                 if 'Licensed under the Apache License' in p.read_text(encoding='utf-8')]
    assert templates  # 改自 ros2pkg 模板的测试文件，文件头保留了原版权声明


def test_sample_face_source_is_documented():
    text = (REPO / 'hci_ws/src/hci_common/hci_common/data/README.md').read_text(encoding='utf-8')
    assert 'public domain' in text.lower() or '公有领域' in text
