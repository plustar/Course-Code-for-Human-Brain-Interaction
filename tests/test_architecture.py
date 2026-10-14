"""
结构规则（docs/ARCHITECTURE.md）：用代码检查代码，违反即失败。

1. 纯 Python 部分不导入 ROS：只有各包的 ros/ 子目录、launch 文件和测试可以导入 rclpy 与消息包
2. 纯 Python 部分只用标准库、NumPy、OpenCV、Pillow、PyYAML 和下层的包
3. 包之间只按分层依赖：上层依赖下层，同层互不依赖，测试代码也一样
4. 练习 3 只导入 hci_common 与 hci_perception 的纯 Python 部分
5. onnxruntime、ultralytics、torch、onnx 这些重型依赖只在用到的函数里导入
6. ros/ 里的节点只写相对话题名（不以 / 开头），接线交给 launch
7. 代码导入了什么，package.xml 里就要声明什么

只读源码（ast），不导入、不运行，所以在两个 Python 环境里都能跑。
"""
import ast
from pathlib import Path
import sys
from typing import Dict, Iterator, List, Set, Tuple
import xml.etree.ElementTree as ET

import pytest

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / 'hci_ws' / 'src'

# 每个包可以依赖的本仓库的包（docs/ARCHITECTURE.md 第 2 节的分层图）
LAYERS: Dict[str, Set[str]] = {
    'hci_common': set(),
    'hci_perception': {'hci_common', 'hci_interfaces'},
    'hci_behavior': {'hci_common', 'hci_interfaces'},
    'hci_sim': {'hci_common'},
    'hci_bringup': {'hci_common', 'hci_interfaces', 'hci_perception', 'hci_behavior', 'hci_sim'},
}
OURS = set(LAYERS) | {'hci_interfaces'}
ROS = {'rclpy', 'rcl_interfaces', 'builtin_interfaces', 'std_msgs', 'std_srvs', 'sensor_msgs',
       'geometry_msgs', 'turtlesim_msgs', 'hci_interfaces', 'message_filters', 'launch',
       'launch_ros', 'launch_testing', 'ament_index_python', 'rmw_test_fixture_implementation'}
CORE_THIRD_PARTY = {'numpy', 'cv2', 'PIL', 'yaml'}
HEAVY = {'onnxruntime', 'ultralytics', 'torch', 'onnx'}
# 导入名 -> package.xml 里的依赖名
ROSDEP = {'numpy': 'python3-numpy', 'cv2': 'python3-opencv', 'PIL': 'python3-pil',
          'yaml': 'python3-yaml', 'pytest': 'python3-pytest', 'hypothesis': 'python3-hypothesis'}
TOPIC_CALLS = {'create_publisher', 'create_subscription', 'create_client', 'create_service',
               'Subscriber'}


def imports(path: Path) -> Iterator[Tuple[str, int, bool]]:
    """文件里导入的顶层模块：(模块名, 行号, 是否在模块加载时就导入)。"""
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))

    def walk(node: ast.AST, eager: bool) -> Iterator[Tuple[str, int, bool]]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Import):
                for alias in child.names:
                    yield alias.name.split('.')[0], child.lineno, eager
            elif isinstance(child, ast.ImportFrom) and child.module and child.level == 0:
                yield child.module.split('.')[0], child.lineno, eager
            yield from walk(child, eager and not isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)))

    yield from walk(tree, True)


def package_files(package: str, part: str = 'code') -> List[Path]:
    """包里的 Python 文件：code 是包本身（含 launch 文件），test 是 test/ 下的测试。"""
    root = SRC / package
    if part == 'test':
        return sorted((root / 'test').rglob('*.py'))
    return sorted(p for p in root.rglob('*.py') if 'test' not in p.relative_to(root).parts[:1]
                  and p.name != 'setup.py')


def is_core(path: Path, package: str) -> bool:
    """纯 Python 部分：包目录里、不在 ros/ 子目录里的模块。"""
    rel = path.relative_to(SRC / package)
    return rel.parts[0] == package and 'ros' not in rel.parts[1:-1]


def declared(package: str) -> Dict[str, Set[str]]:
    """package.xml 里的依赖：{'exec': {...}, 'test': {...}}（depend 两边都算）。"""
    root = ET.parse(SRC / package / 'package.xml').getroot()

    def names(*tags: str) -> Set[str]:
        return {e.text.strip() for tag in tags for e in root.iter(tag) if e.text}
    common = names('depend')
    return {'exec': common | names('exec_depend', 'build_export_depend'),
            'test': common | names('exec_depend', 'test_depend')}


@pytest.mark.parametrize('package', sorted(LAYERS))
def test_core_does_not_import_ros(package):
    for path in package_files(package):
        if not is_core(path, package):
            continue
        for module, line, _ in imports(path):
            assert module not in ROS, (f'{path.relative_to(REPO)}:{line} 导入了 {module}：'
                                       '用到 ROS 的代码要放进 ros/ 子目录')


@pytest.mark.parametrize('package', sorted(LAYERS))
def test_core_uses_only_light_dependencies(package):
    allowed = set(sys.stdlib_module_names) | CORE_THIRD_PARTY | LAYERS[package] | {package}
    for path in package_files(package):
        if not is_core(path, package):
            continue
        for module, line, eager in imports(path):
            if module in HEAVY and not eager:
                continue  # 重型依赖在函数里导入：允许
            assert module in allowed, f'{path.relative_to(REPO)}:{line} 导入了 {module}'


@pytest.mark.parametrize('package', sorted(LAYERS))
@pytest.mark.parametrize('part', ['code', 'test'])
def test_packages_only_depend_on_lower_layers(package, part):
    for path in package_files(package, part):
        for module, line, _ in imports(path):
            if module in OURS and module != package:
                assert module in LAYERS[package], (
                    f'{path.relative_to(REPO)}:{line}：{package} 不能依赖 {module}'
                    f'（允许：{sorted(LAYERS[package]) or "无"}）')


@pytest.mark.parametrize('package', sorted(LAYERS))
def test_heavy_dependencies_are_imported_lazily(package):
    for path in package_files(package):
        for module, line, eager in imports(path):
            assert not (module in HEAVY and eager), (
                f'{path.relative_to(REPO)}:{line} 在模块加载时导入了 {module}：'
                '请移到用到它的函数里，没装它的环境才能正常导入这个模块')


def test_exercise_3_uses_only_the_pure_python_parts():
    for path in sorted((REPO / 'exercises/face_recognition').rglob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                continue
            for name in names:
                top = name.split('.')[0]
                where = f'{path.relative_to(REPO)}:{node.lineno}'
                assert top not in ROS, f'{where} 导入了 {name}：练习 3 在训练环境里运行，没有 ROS'
                if top in OURS:
                    assert top in ('hci_common', 'hci_perception') and '.ros' not in name, \
                        f'{where} 导入了 {name}：练习 3 只能用感知包与地基包的纯 Python 部分'


@pytest.mark.parametrize('package', sorted(LAYERS))
def test_nodes_use_relative_topic_names(package):
    for path in package_files(package):
        if is_core(path, package) or 'launch' in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else \
                getattr(node.func, 'id', '')
            if name not in TOPIC_CALLS:
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    assert not arg.value.startswith('/'), (
                        f'{path.relative_to(REPO)}:{node.lineno} 用了绝对话题名 {arg.value}：'
                        '节点里写相对名，由 launch 放进命名空间并重映射')


@pytest.mark.parametrize('package', sorted(LAYERS))
@pytest.mark.parametrize('part', ['code', 'test'])
def test_package_xml_declares_what_the_code_imports(package, part):
    for path in package_files(package, part):
        # testing.py 是测试辅助模块，只在测试里用：它的依赖算测试依赖
        kind = 'exec_depend' if part == 'code' and path.name != 'testing.py' else 'test_depend'
        deps = declared(package)['exec' if kind == 'exec_depend' else 'test']
        for module, line, _ in imports(path):
            key = ROSDEP.get(module, module)
            if module in OURS | ROS | set(ROSDEP) and module != package:
                assert key in deps, (f'{path.relative_to(REPO)}:{line} 导入了 {module}：'
                                     f'请在 {package}/package.xml 里加上 <{kind}>{key}</{kind}>')
