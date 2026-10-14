"""
文档与代码一致：参数表、启动参数表来自代码里的唯一声明；相对链接和章节引用都有效。

改了参数忘了改文档，这里会报出来（参数在节点的 Params 数据类里只声明一次，见 hci_common/params.py）。
"README 第 4.7 节"这样的引用，也要指向 README 里存在的节。
"""
import importlib.util
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, Iterator, List, Tuple

import pytest

REPO = Path(__file__).resolve().parents[1]
LAUNCH = REPO / 'hci_ws' / 'src' / 'hci_bringup' / 'launch'
Row = Tuple[str, str, str]


def table_after(text: str, heading: str) -> List[Row]:
    """heading 之后的第一个 markdown 表格：[(第 1 列, 第 2 列, 第 3 列), ...]，不含表头。"""
    start = text.index(heading)
    rows, started = [], False
    for line in text[start:].splitlines()[1:]:
        if line.startswith('|'):
            started = True
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if not set(cells[0]) <= set('-:') and cells[0] != '参数':
                rows.append((cells[0].strip('`'), cells[1].strip('`'), cells[2]))
        elif started:
            break
    return rows


def load_launch(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name.replace('.', '_'), LAUNCH / name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


NODES = {
    'camera_node': 'hci_perception.ros.camera_node',
    'recognizer_node': 'hci_perception.ros.recognizer_node',
    'viewer_node': 'hci_perception.ros.viewer_node',
    'behavior_node': 'hci_behavior.ros.behavior_node',
    'virtual_camera_node': 'hci_sim.ros.virtual_camera_node',
}


@pytest.mark.parametrize('node', sorted(NODES))
def test_parameter_tables_match_the_code(node):
    pytest.importorskip('rclpy', reason='需要 ROS 环境')
    from hci_common.params import param_table
    params = importlib.import_module(NODES[node]).Params
    text = (REPO / 'hci_ws' / 'README.md').read_text(encoding='utf-8')
    rows = table_after(text, f'### {node}')
    documented = [(name, json.loads(default), doc) for name, default, doc in rows]
    expected = param_table(params)
    assert [r[0] for r in documented] == [e[0] for e in expected], \
        f'hci_ws/README.md 里 {node} 的参数（名字或顺序）与代码不一致'
    for (name, default, doc), (_, code_default, code_doc) in zip(documented, expected):
        assert default == code_default and type(default) is type(code_default), \
            f'{node}.{name} 的默认值：文档 {default!r}，代码 {code_default!r}'
        assert doc == code_doc, f'{node}.{name} 的说明：文档"{doc}"，代码"{code_doc}"'


@pytest.mark.parametrize('launch_file, heading', [
    ('perception.launch.py', '`perception.launch.py` 的启动参数'),
    ('system.launch.py', '`system.launch.py` 的启动参数'),
])
def test_launch_argument_tables_match_the_code(launch_file, heading):
    pytest.importorskip('launch', reason='需要 ROS 环境')
    args: Dict[str, Tuple[str, str]] = load_launch(launch_file).ARGS
    rows = table_after((REPO / 'README.md').read_text(encoding='utf-8'), heading)
    assert [r[0] for r in rows] == list(args), f'README 里 {launch_file} 的启动参数与代码不一致'
    for name, default, doc in rows:
        assert (default, doc) == args[name], f'{launch_file} 的 {name}：{(default, doc)}'


def test_system_launch_passes_the_perception_arguments_through():
    pytest.importorskip('launch', reason='需要 ROS 环境')
    system, perception = load_launch('system.launch.py'), load_launch('perception.launch.py')
    # camera 与 robot 由 system.launch.py 自己决定（仿真时感知部分不启动相机）
    assert set(system.PASSTHROUGH) == set(perception.ARGS) - {'camera', 'robot'}


def test_relative_links_in_documents_exist():
    broken = []
    for doc in sorted(REPO.rglob('*.md')):
        if any(part in ('build', 'install', 'log', '.git') for part in doc.parts):
            continue
        for target in re.findall(r'\]\(([^)#\s]+)(?:#[^)]*)?\)', doc.read_text(encoding='utf-8')):
            if not re.match(r'[a-z]+://', target) and not (doc.parent / target).exists():
                broken.append(f'{doc.relative_to(REPO)} -> {target}')
    assert not broken, '这些链接打不开：\n' + '\n'.join(broken)


def text_files() -> Iterator[Path]:
    """仓库里的文档、代码和脚本（不含编译产物和练习 3 的数据）。"""
    skip = {'.git', 'build', 'install', 'log', 'data', 'dataset', 'runs', 'out', '__pycache__'}
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in skip]
        for name in files:
            if name.endswith(('.md', '.py', '.sh', '.json', '.yml', '.yaml')):
                yield Path(root) / name


def test_section_references_point_to_existing_readme_sections():
    # README 里的"见第 4.7 节"，以及代码、脚本、其他文档里的"README 第 4.7 节"
    readme = REPO / 'README.md'
    sections = set(re.findall(r'^#{2,3} (\d+(?:\.\d+)?)\.?\s', readme.read_text(encoding='utf-8'),
                              re.MULTILINE))
    refs = []
    for path in text_files():
        pattern = r'第 (\d+(?:\.\d+)?) 节' if path == readme else r'README 第 (\d+(?:\.\d+)?) 节'
        refs += [(path.relative_to(REPO), n)
                 for n in re.findall(pattern, path.read_text(encoding='utf-8'))]
    missing = [f'{path}：第 {n} 节' for path, n in refs if n not in sections]
    assert refs and not missing, 'README 里没有这些节：\n' + '\n'.join(missing)


def test_ci_installs_ros_exactly_as_the_readme_says():
    # GitHub Actions 按 README 第 4.2 节的命令安装 ROS：README 里的命令改了，CI 也要跟着改
    readme = (REPO / 'README.md').read_text(encoding='utf-8')
    block = next(b for b in readme.split('```bash\n')[1:] if 'ROS_APT_SOURCE_VERSION' in b)
    commands = [line for line in block.split('```')[0].splitlines()
                if line.startswith(('export ROS_APT_SOURCE_VERSION', 'curl ', 'sudo dpkg',
                                    'sudo apt install -y ros-lyrical'))]
    workflow = (REPO / '.github' / 'workflows' / 'tests.yml').read_text(encoding='utf-8')
    ci = {line.strip() for line in workflow.splitlines()}
    assert len(commands) == 4 and not [c for c in commands if c not in ci], commands


def test_ci_workflows_only_read_the_repository():
    # 工作流只需要读取代码：不申请写权限，检出后也不把 git 凭据留在磁盘上
    for workflow in sorted((REPO / '.github' / 'workflows').glob('*.yml')):
        text = workflow.read_text(encoding='utf-8')
        assert '\npermissions:\n  contents: read' in text, workflow.name
        checkouts = text.count('uses: actions/checkout@')
        assert checkouts and text.count('persist-credentials: false') == checkouts, workflow.name


def test_testing_guide_lists_every_marker():
    markers = re.findall(r'^\s+(\w+):', (REPO / 'pytest.ini').read_text(), re.MULTILINE)
    guide = (REPO / 'docs' / 'TESTING.md').read_text(encoding='utf-8')
    missing = [m for m in markers if f'`{m}`' not in guide]
    assert not missing, f'docs/TESTING.md 没有说明这些标记：{missing}'


def test_architecture_guide_covers_every_package():
    guide = (REPO / 'docs' / 'ARCHITECTURE.md').read_text(encoding='utf-8')
    packages = [p.name for p in (REPO / 'hci_ws' / 'src').iterdir() if p.is_dir()]
    assert all(f'`{p}`' in guide for p in packages)
