"""
练习脚本与仓库级测试的代码风格：与 ROS 包相同的 ament 检查（flake8、pep257、mypy）。

各个 ROS 包有自己的 test_flake8.py 等；这里检查不在包里的 Python 代码。需要 ROS 环境。
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.linter
REPO = Path(__file__).resolve().parents[1]
FOLDERS = ['exercises/ros_basics', 'exercises/face_recognition', 'tests']


@pytest.mark.parametrize('folder', FOLDERS)
def test_flake8(folder):
    main_with_errors = pytest.importorskip('ament_flake8.main').main_with_errors
    rc, errors = main_with_errors(argv=[str(REPO / folder)])
    assert rc == 0, f'{len(errors)} 处代码风格问题：\n' + '\n'.join(errors)


@pytest.mark.parametrize('folder', FOLDERS)
def test_pep257(folder):
    main = pytest.importorskip('ament_pep257.main').main
    # 与各包的 test_pep257.py 相同：忽略三条只适用于英文文档字符串的规则
    assert main(argv=[str(REPO / folder), '--add-ignore', 'D400', 'D403', 'D415']) == 0


@pytest.mark.parametrize('folder', [
    'exercises/ros_basics', 'exercises/face_recognition',
    'exercises/face_recognition/tests', 'exercises/ros_basics/tests', 'tests'])
def test_mypy(folder):
    main = pytest.importorskip('ament_mypy.main').main
    paths = [str(p) for p in sorted((REPO / folder).glob('*.py'))]  # 不进子目录：各自检查
    assert main(argv=paths) == 0
