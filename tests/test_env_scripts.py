"""
环境与工具脚本：shellcheck 检查；用错时给出中文提示而不是半途出错；两个环境互不干扰的保护。

这些检查不会真的安装任何东西（不调用 sudo、不联网）。
"""
import hashlib
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
from typing import Dict, List, Optional

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = sorted((REPO / 'env').glob('*.sh')) + sorted((REPO / 'tools').glob('*.sh'))


def run(cmd: List[str], env: Optional[Dict[str, str]] = None,
        timeout: float = 60) -> subprocess.CompletedProcess:
    """在仓库根目录运行命令。超时的话，连同它启动的进程一起结束，不在后台留下任何进程。"""
    full_env = dict(os.environ)
    full_env.update(env or {})
    with subprocess.Popen(cmd, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          stdin=subprocess.DEVNULL, text=True, env=full_env,
                          start_new_session=True) as proc:
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            raise
    return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)


def bash(script: str, *args: str, env: Optional[Dict[str, str]] = None,
         timeout: float = 60) -> subprocess.CompletedProcess:
    return run(['bash', str(REPO / script), *args], env, timeout)


@pytest.fixture
def no_sudo(tmp_path) -> Dict[str, str]:
    """PATH 的最前面放一个总是失败的 sudo：保护万一失效，安装脚本也会在真正安装之前停下。"""
    fake = tmp_path / 'sudo'
    fake.write_text('#!/bin/sh\nexit 1\n')
    fake.chmod(0o755)
    return {'PATH': f'{tmp_path}:{os.environ["PATH"]}'}


@pytest.mark.linter
@pytest.mark.skipif(shutil.which('shellcheck') is None, reason='没有安装 shellcheck')
@pytest.mark.parametrize('script', SCRIPTS, ids=lambda p: p.name)
def test_shellcheck(script):
    result = subprocess.run(['shellcheck', str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize('script', ['env/setup_ros_env.sh', 'env/setup_conda.sh',
                                    'tools/run_tests.sh', 'tools/download_models.sh'])
def test_unknown_options_are_rejected_before_doing_anything(script):
    result = bash(script, '--bogus')
    assert result.returncode != 0 and '未知参数' in result.stdout + result.stderr


ALL_SCRIPTS = ['env/setup_ros_env.sh', 'env/setup_conda.sh', 'env/check_env.sh',
               'tools/run_tests.sh', 'tools/download_models.sh']


@pytest.mark.skipif(shutil.which('sh') is None, reason='没有 sh')
@pytest.mark.parametrize('script', ALL_SCRIPTS)
def test_scripts_explain_they_need_bash(script, no_sudo):
    # 用 sh 运行：在数组语法处出错之前就说明；用 source 运行：不把 set -e 带进终端，也不关掉终端
    sh = run(['sh', script], no_sudo)
    assert sh.returncode == 1 and '请用 bash 运行' in sh.stdout
    sourced_by_sh = run(['sh', '-c', f'. ./{script}; echo "终端还在，返回值 $?"'], no_sudo)
    assert '终端还在，返回值 1' in sourced_by_sh.stdout  # 在 zsh 之类的终端里 source：同样不关掉终端
    sourced = run(['bash', '-c', f'source {script}; echo "rc=$? options=$-"'], no_sudo)
    assert '不要 source' in sourced.stdout and 'rc=1' in sourced.stdout
    options = sourced.stdout.split('options=')[1].strip()
    assert 'e' not in options and 'u' not in options


@pytest.mark.parametrize('script', ALL_SCRIPTS)
def test_scripts_refuse_to_run_under_sudo(script, no_sudo):
    # sudo bash ...：设置会写进 root 的主目录，编译产物属于 root，之后自己就改不动了
    result = bash(script, env={'SUDO_USER': 'student', **no_sudo})
    assert result.returncode == 1 and '不要用 sudo 运行' in result.stdout


@pytest.mark.skipif(not Path('/opt/ros/lyrical/setup.bash').exists(), reason='需要 ROS 环境')
def test_failed_installation_says_what_to_do_next(tmp_path):
    # 网络出问题时 apt 失败：最后要有一句中文说明，而不是只有一行英文报错
    fake_sudo = tmp_path / 'sudo'
    fake_sudo.write_text('#!/bin/sh\necho "E: 模拟的网络错误" >&2\nexit 100\n')
    fake_sudo.chmod(0o755)
    env = {'PATH': f'{tmp_path}:{os.environ["PATH"]}', 'CONDA_PREFIX': ''}
    result = bash('env/setup_ros_env.sh', env=env)
    assert result.returncode == 100
    assert '安装没有完成' in result.stdout and '可以重复运行' in result.stdout


def bashrc_writer() -> str:
    """setup_ros_env.sh 里写 ~/.bashrc 的那段 Python。"""
    text = (REPO / 'env' / 'setup_ros_env.sh').read_text(encoding='utf-8')
    found = re.search(r'"\$HOME/\.bashrc" "\$REPO" <<\'PY\'\n(.*?)\nPY\n', text, re.S)
    assert found, 'setup_ros_env.sh 里没有写 ~/.bashrc 的代码'
    return found.group(1)


def test_bashrc_lines_are_written_once_and_follow_the_repository(tmp_path):
    bashrc = tmp_path / '.bashrc'
    bashrc.write_text('alias ll="ls -l"\n', encoding='utf-8')

    def write(repo: str) -> str:
        return subprocess.run([sys.executable, '-c', bashrc_writer(), str(bashrc), repo],
                              capture_output=True, text=True, check=True).stdout

    assert '已写入' in write('/home/me/hci-course-code-main')
    assert write('/home/me/hci-course-code-main') == ''  # 重复运行：不再写
    assert '已更新' in write('/home/me/hci-course-code')  # 改了文件夹名再运行：换成新路径
    text = bashrc.read_text(encoding='utf-8')
    assert text.startswith('alias ll="ls -l"\n') and text.count('# >>> hci-course-code >>>') == 1
    assert '/home/me/hci-course-code/hci_ws/install/setup.bash' in text and '-main' not in text
    sourced = subprocess.run(['bash', '-c', f'source {bashrc} 2>&1; echo ok'],
                             capture_output=True, text=True, env={'PATH': os.environ['PATH']})
    assert sourced.stdout.strip().endswith('ok')  # 写进去的是合法的 bash


def test_bashrc_lines_work_when_the_path_has_spaces(tmp_path):
    # 例如把仓库放在了 "~/my code/" 下面
    repo = tmp_path / 'my code' / 'hci-course-code'
    setup = repo / 'hci_ws' / 'install' / 'setup.bash'
    setup.parent.mkdir(parents=True)
    setup.write_text('echo 工作空间已加载\n', encoding='utf-8')
    bashrc = tmp_path / '.bashrc'
    subprocess.run([sys.executable, '-c', bashrc_writer(), str(bashrc), str(repo)],
                   capture_output=True, check=True)
    sourced = subprocess.run(['bash', '-c', f'source {shlex.quote(str(bashrc))} 2> /dev/null'],
                             capture_output=True, text=True, env={'PATH': os.environ['PATH']})
    assert '工作空间已加载' in sourced.stdout


def test_run_tests_help():
    result = bash('tools/run_tests.sh', '--help')
    assert result.returncode == 0 and 'run_tests.sh --quick' in result.stdout
    assert 'set -u' not in result.stdout  # 只打印开头的说明，不带代码


def test_check_env_catches_an_active_conda_environment():
    result = bash('env/check_env.sh', env={'CONDA_PREFIX': '/home/me/miniforge3/envs/hci-train'},
                  timeout=120)
    assert result.returncode != 0 and 'conda deactivate' in result.stdout


def test_check_env_explains_conda_in_a_vscode_terminal():
    # VS Code 打开的是上一层目录时，仓库的设置不生效，Python 扩展会在终端里激活 conda
    result = bash('env/check_env.sh', env={'CONDA_PREFIX': '/home/me/miniconda3',
                                           'TERM_PROGRAM': 'vscode'}, timeout=120)
    assert result.returncode != 0 and '打开的文件夹就是 hci-course-code' in result.stdout


def test_check_env_train_mode_needs_the_conda_environment():
    result = bash('env/check_env.sh', 'train', env={'CONDA_DEFAULT_ENV': ''}, timeout=120)
    assert result.returncode != 0 and 'conda activate hci-train' in result.stdout


def test_check_env_shows_the_code_version():
    # 向助教反馈问题时要附上 check_env.sh 的输出：第一行写明用的是哪一版代码
    match = re.search(r'<version>(.+)</version>',
                      (REPO / 'hci_ws/src/hci_common/package.xml').read_text(encoding='utf-8'))
    assert match
    out = bash('env/check_env.sh', 'train', env={'CONDA_DEFAULT_ENV': ''}, timeout=120).stdout
    first = out.splitlines()[0]
    assert first.startswith(f'课程代码 v{match.group(1)}')
    if (REPO / '.git').exists() and shutil.which('git'):
        assert '，git ' in first  # 用 git clone 得到的仓库，还显示标签和提交


def test_check_env_catches_another_ros_distribution():
    # 例如从 24.04 升级上来，~/.bashrc 里还 source 着 Jazzy
    result = bash('env/check_env.sh', env={'AMENT_PREFIX_PATH': '/opt/ros/jazzy:/opt/ros/lyrical'},
                  timeout=120)
    assert result.returncode != 0 and '其他版本的 ROS（/opt/ros/jazzy）' in result.stdout


@pytest.mark.skipif(shutil.which('apt-get') is None, reason='没有 apt')
def test_check_env_lists_ros_sources_for_other_ubuntu_releases(tmp_path):
    stanza = 'Types: deb\nURIs: {}\nSuites: {}\nComponents: main\n'
    ros2 = 'http://packages.ros.org/ros2/ubuntu'
    sources = {
        'ros2.sources': stanza.format(ros2, 'resolute'),  # 26.04 的 ROS 源：不算
        'disabled.sources': stanza.format(ros2, 'jammy') + 'Enabled: no\n',  # 已停用：不算
        'ubuntu.sources': stanza.format('http://archive.ubuntu.com/ubuntu', 'noble'),  # 不是 ROS 的
        'old-ros2.list': f'deb {ros2} noble main\n',
        'old-ros1.list': 'deb https://mirrors.tuna.tsinghua.edu.cn/ros/ubuntu focal main\n',
    }
    parts = tmp_path / 'sources.list.d'
    parts.mkdir()
    for name, text in sources.items():
        (parts / name).write_text(text)
    config = tmp_path / 'apt.conf'  # 让 apt 只读这几个文件
    config.write_text(f'Dir::Etc::SourceParts "{parts}";\nDir::Etc::SourceList "/dev/null";\n')
    out = bash('env/check_env.sh', env={'APT_CONFIG': str(config)}, timeout=120).stdout
    assert f'{parts}/old-ros2.list:1（noble）' in out and f'{parts}/old-ros1.list:1（focal）' in out
    assert not any(name in out for name in ('ros2.sources', 'disabled.sources', 'ubuntu.sources'))


@pytest.mark.skipif(shutil.which('cmake') is None, reason='没有 cmake')
def test_building_messages_inside_conda_is_stopped(tmp_path):
    # 编译器设成不存在：没装编译器的电脑上，也要先看到这条提示
    env = dict(os.environ, CONDA_PREFIX='/home/me/miniforge3/envs/hci-train',
               CC='/nonexistent/cc', CXX='/nonexistent/c++', TERM_PROGRAM='vscode')
    result = subprocess.run(['cmake', '-S', str(REPO / 'hci_ws' / 'src' / 'hci_interfaces'),
                             '-B', str(tmp_path)], capture_output=True, text=True, env=env)
    output = ''.join((result.stdout + result.stderr).split())  # CMake 会把长消息折行
    assert result.returncode != 0 and '检测到conda环境' in output
    assert '打开的文件夹就是hci-course-code' in output  # 在 VS Code 的终端里，说明常见的原因


@pytest.mark.skipif(shutil.which('cmake') is None, reason='没有 cmake')
def test_building_messages_with_leftover_empty_conda_prefix_is_allowed(tmp_path):
    # conda deactivate 之后 CONDA_PREFIX 常被留成空字符串。这不是“conda 还激活”，
    # 不能挡住编译（和 run_tests.sh / check_env.sh 的 [ -n "$CONDA_PREFIX" ] 保持一致）。
    # 编译器设成不存在：configure 一定会失败，但失败的原因必须是找不到编译器，而不是这条守卫。
    env = dict(os.environ, CONDA_PREFIX='', CC='/nonexistent/cc', CXX='/nonexistent/c++')
    result = subprocess.run(['cmake', '-S', str(REPO / 'hci_ws' / 'src' / 'hci_interfaces'),
                             '-B', str(tmp_path)], capture_output=True, text=True, env=env)
    output = ''.join((result.stdout + result.stderr).split())  # CMake 会把长消息折行
    assert '检测到conda环境' not in output  # 空字符串不该触发守卫


def test_ros_tests_say_where_to_run_when_ros_is_missing():
    # 例如在训练环境（conda）里直接运行 ROS 包的测试：给出中文提示，而不是 No module named rclpy
    code = ('import sys; sys.modules["rclpy"] = None; import pytest; '
            'sys.exit(pytest.main(["-q", "-p", "no:cacheprovider", "hci_ws/src/hci_sim/test"]))')
    result = subprocess.run([sys.executable, '-c', code], cwd=REPO, capture_output=True,
                            text=True, timeout=120)
    assert result.returncode == 4 and 'conda deactivate' in result.stdout + result.stderr


def test_conda_setup_points_the_training_env_at_the_shared_code():
    text = (REPO / 'env' / 'setup_conda.sh').read_text(encoding='utf-8')
    assert 'hci_course.pth' in text
    assert '$REPO/hci_ws/src/hci_common' in text and '$REPO/hci_ws/src/hci_perception' in text


@pytest.mark.parametrize('script', ['env/setup_conda.sh', 'env/setup_ros_env.sh'])
def test_both_setups_turn_off_conda_base_in_new_terminals(script):
    # 新终端默认不进 conda，ROS 才能正常工作。先装 ROS 的同学还没运行过 setup_conda.sh
    assert 'auto_activate_base false' in (REPO / script).read_text(encoding='utf-8')


def conda_hook(kind: str) -> str:
    """setup_conda.sh 写进训练环境的 activate.d 或 deactivate.d 脚本的内容。"""
    text = (REPO / 'env' / 'setup_conda.sh').read_text(encoding='utf-8')
    found = re.search(rf'/{kind}\.d/hci_isolate_ros\.sh" <<\'EOF\'\n(.*?)\nEOF\n', text, re.S)
    assert found, f'setup_conda.sh 里没有 {kind}.d/hci_isolate_ros.sh'
    return found.group(1)


def test_conda_activation_hides_ros_and_deactivation_restores_it():
    # 学生的终端：~/.bashrc 已经 source 了 ROS（setup_ros_env.sh --bashrc），再 conda activate
    ros = {'PYTHONPATH': '/opt/ros/lyrical/lib/python3.14/site-packages',
           'LD_LIBRARY_PATH': '/opt/ros/lyrical/lib', 'AMENT_PREFIX_PATH': '/opt/ros/lyrical'}
    show = '\n'.join(f'echo "{name}=${{{name}-未设置}}"' for name in ros)
    script = '\n'.join([conda_hook('activate'), show, conda_hook('deactivate'), show])
    lines = subprocess.run(['bash', '-c', script], capture_output=True, text=True, check=True,
                           env=dict(os.environ, **ros)).stdout.splitlines()
    assert lines[:3] == [f'{name}=未设置' for name in ros]  # 激活后：ROS 的路径都去掉了
    assert lines[3:] == [f'{name}={value}' for name, value in ros.items()]  # 退出后原样恢复


def test_ros_setup_installs_the_compiler_and_what_the_tests_need():
    text = (REPO / 'env' / 'setup_ros_env.sh').read_text(encoding='utf-8')
    # build-essential：编译消息包要用的 C++ 编译器，ros-dev-tools 和新装的 Ubuntu 都没有
    for package in ('build-essential', 'python3-pytest-timeout', 'python3-hypothesis',
                    'python3-onnx', 'shellcheck', 'ros-lyrical-ament-mypy', 'python3-typeshed',
                    'python3-onnxruntime', 'fonts-noto-cjk'):
        assert package in text


def test_download_script_knows_the_bundled_model():
    text = (REPO / 'tools' / 'download_models.sh').read_text(encoding='utf-8')
    model = (REPO / 'hci_ws/src/hci_perception/hci_perception/models'
             / 'face_detection_yunet_2023mar.onnx')
    expected = re.search(r'face_detection_yunet_2023mar\.onnx \\\s+([0-9a-f]{64})', text)
    assert expected and hashlib.sha256(model.read_bytes()).hexdigest() == expected.group(1)


def test_training_setup_pins_versions_and_turns_off_analytics():
    setup = (REPO / 'env' / 'setup_conda.sh').read_text(encoding='utf-8')
    requirements = (REPO / 'env' / 'requirements-train.txt').read_text(encoding='utf-8')
    # 锁定在实测过的版本：学期中途上游发布新版本，也不影响学生
    assert '"torch>=2.14,<2.15"' in setup and 'ultralytics>=8.4,<8.5' in requirements
    for pin in ('onnx>=1.23,<1.24', 'onnxslim>=0.1.82,<0.2', 'onnxruntime>=1.30,<1.31'):
        assert pin in requirements
    assert "settings.update({'sync': False})" in setup  # 关掉 Ultralytics 的匿名使用统计


def test_training_requirements_include_the_test_tools():
    lines: List[str] = (REPO / 'env' / 'requirements-train.txt').read_text().splitlines()
    names = {re.split(r'[<>=\s#]', line)[0] for line in lines if line and not line.startswith('#')}
    assert {'ultralytics', 'onnx', 'onnxruntime', 'pytest', 'pytest-timeout',
            'hypothesis'} <= names
