#!/usr/bin/env bash
# ROS 环境（练习 2、4 与期末）：系统 Python 3.14 + apt，不用 conda，也不用虚拟环境。
# 先按 README 装好 Ubuntu 26.04 和 ROS 2 Lyrical（ros-lyrical-desktop），再运行：
#   bash env/setup_ros_env.sh                 安装 C++ 编译器、节点用到的 Python 包、中文字体和测试工具
#   bash env/setup_ros_env.sh --gazebo        另外安装 Gazebo 与 TurtleBot 3 仿真（期末可选）
#   bash env/setup_ros_env.sh --bashrc        另外把 source ROS 的几行写进 ~/.bashrc（含仓库根目录
#                                             变量 HCI_ROOT，新终端自动可用），并关掉 conda 自动进入 (base)
if [ -z "${BASH_VERSION:-}" ]; then echo "请用 bash 运行：bash $0"; (return 0 2> /dev/null) && return 1; exit 1; fi  # sh 不认识数组语法；被 zsh 等 source 时只 return，不关掉终端
# 用 source 运行会把脚本的设置带进你的终端，一出错整个终端窗口都会关掉
if [ "${BASH_SOURCE[0]}" != "$0" ]; then echo "请用 bash 运行，不要 source：bash ${BASH_SOURCE[0]}"; return 1; fi
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
GAZEBO=0
BASHRC=0
for a in "$@"; do
  case "$a" in
    --gazebo) GAZEBO=1 ;;
    --bashrc) BASHRC=1 ;;
    *) echo "未知参数：$a（可用 --gazebo、--bashrc）"; exit 1 ;;
  esac
done
if [ -n "${SUDO_USER:-}" ]; then
  echo "[错误] 不要用 sudo 运行这个脚本：需要管理员权限的步骤，脚本会自己调用 sudo（会提示输入密码）。"
  echo "       用 sudo 运行会把设置写到 root 的主目录里。请直接运行：bash $0"
  exit 1
fi

# shellcheck source=/dev/null
. /etc/os-release
if [ "$VERSION_ID" != "26.04" ]; then
  echo "[错误] 本课程使用 Ubuntu 26.04，当前系统是 $PRETTY_NAME"
  echo "       WSL2 用户可在 Windows PowerShell 执行：wsl --install -d Ubuntu-26.04"
  exit 1
fi
if [ -n "$CONDA_PREFIX" ]; then
  echo "[错误] conda 环境（$CONDA_PREFIX）处于激活状态。ROS 要用系统 Python，请先执行 conda deactivate"
  [ "$TERM_PROGRAM" = vscode ] && echo "       VS Code 的终端：确认打开的文件夹就是 hci-course-code（仓库里的设置会让终端不再自动激活 conda），然后关掉这个终端、新开一个"
  exit 1
fi
if [ ! -f /opt/ros/lyrical/setup.bash ]; then
  echo "[错误] 没有找到 ROS 2 Lyrical（/opt/ros/lyrical）。请先按 README 第 4.2 节安装"
  exit 1
fi

# 编译自定义消息要用的 C++ 编译器（ros-dev-tools 里没有，新装的 Ubuntu 也没有），节点运行需要的包
PKGS=(build-essential python3-opencv python3-pil python3-onnxruntime python3-yaml fonts-noto-cjk)
# 测试需要的包（bash tools/run_tests.sh）：pytest 插件、属性测试、生成微型 ONNX 模型、
# 脚本检查、类型检查（python3-typeshed 提供 yaml 等第三方库的类型信息），以及给每个测试进程
# 分配独占 ROS_DOMAIN_ID 的 rmw_test_fixture
PKGS+=(python3-pytest python3-pytest-timeout python3-pytest-cov python3-hypothesis python3-onnx
       shellcheck ros-lyrical-ament-mypy python3-typeshed
       ros-lyrical-rmw-test-fixture-implementation)
# 从这里开始要联网下载、安装。任何一步失败时（set -e 会让脚本停下），最后用中文说明怎么办
explain_failure() {
  local rc=$?
  [ "$rc" = 0 ] || echo "[错误] 安装没有完成：上面最后一条命令失败了（返回值 $rc）。多半是网络或软件源的问题，在国内先按 README 第 4.5 节换源；修好后重新运行 bash env/setup_ros_env.sh 即可（可以重复运行）"
}
trap explain_failure EXIT
echo ">>> sudo apt install ${PKGS[*]}"
sudo apt update
sudo apt install -y "${PKGS[@]}"
if [ $GAZEBO = 1 ]; then
  echo ">>> 安装 Gazebo（ros_gz）与 TurtleBot 3 仿真"
  sudo apt install -y ros-lyrical-ros-gz
  sudo apt install -y ros-lyrical-turtlebot3-gazebo || \
    echo "[提示] TurtleBot 3 仿真包没装上，可以先用 ros_gz 官方演示：ros2 launch ros_gz_sim_demos diff_drive.launch.xml"
fi

MODEL="$REPO/hci_ws/src/hci_perception/hci_perception/models/face_detection_yunet_2023mar.onnx" \
  /usr/bin/python3 - <<'PY'
import os, sys
import cv2, numpy, PIL, onnxruntime
print(f"系统 Python {sys.version.split()[0]} | numpy {numpy.__version__} | opencv {cv2.__version__} | "
      f"Pillow {PIL.__version__} | onnxruntime {onnxruntime.__version__}")
det = cv2.FaceDetectorYN.create(os.environ["MODEL"], "", (320, 320), 0.6, 0.3, 50)
det.detect(numpy.zeros((320, 320, 3), numpy.uint8))
print("YuNet 人脸检测可以运行")
PY

# 在 ~/.bashrc 里写入（或更新）本课程的几行（含仓库根目录变量 HCI_ROOT）。重复运行不会重复写入；
# 仓库换了位置（例如解压后改了文件夹名）再运行一次，就换成新的路径
if [ $BASHRC = 1 ]; then
  /usr/bin/python3 - "$HOME/.bashrc" "$REPO" <<'PY'
import re
import shlex
import sys
from pathlib import Path

bashrc, repo = Path(sys.argv[1]), sys.argv[2]
setup = shlex.quote(f'{repo}/hci_ws/install/setup.bash')
repo_q = shlex.quote(repo)
block = ('# >>> hci-course-code >>>\n'
         f'export HCI_ROOT={repo_q}\n'          # 仓库根目录；文档里的命令用 $HCI_ROOT，放哪都行
         'source /opt/ros/lyrical/setup.bash\n'
         f'[ -f {setup} ] && source {setup}\n'
         '# <<< hci-course-code <<<\n')
old = bashrc.read_text(encoding='utf-8') if bashrc.exists() else ''
new, found = re.subn(r'# >>> hci-course-code >>>\n.*?# <<< hci-course-code <<<\n?',
                     lambda _: block, old, flags=re.S)
if not found:
    new = old + ('\n' if old and not old.endswith('\n') else '') + block
if new != old:
    bashrc.write_text(new, encoding='utf-8')
    print('>>> 已更新 ~/.bashrc 里的仓库路径' if found else '>>> 已写入 ~/.bashrc', '（新开的终端生效）')
PY
fi

# conda 设成新终端自动进入 (base) 时，在里面编译或运行 ROS 都会用错 Python
CONDA_BIN="${CONDA_EXE:-$(command -v conda || true)}"
if [ -n "$CONDA_BIN" ] && "$CONDA_BIN" config --show auto_activate_base 2> /dev/null | grep -qi true; then
  if [ $BASHRC = 1 ] && "$CONDA_BIN" config --set auto_activate_base false 2> /dev/null; then
    echo ">>> 已关掉 conda 在新终端里自动进入 (base)；训练时照常 conda activate hci-train"
    echo "    （想恢复：conda config --set auto_activate_base true）"
  else
    echo "[提示] 每个新终端都会自动进入 conda 的 (base)，ROS 在 (base) 里用不了。关掉它："
    echo "       conda config --set auto_activate_base false"
  fi
fi
echo
if [ $GAZEBO = 1 ]; then
  echo "Gazebo 刚装好：新开一个终端再启动它。这个终端还找不到刚装的 gz 命令，"
  echo "直接启动会报 'NoneType' object has no attribute 'lower'"
fi
echo "完成。下一步编译工作空间并运行测试："
echo "  source /opt/ros/lyrical/setup.bash && cd $REPO/hci_ws && colcon build --symlink-install"
echo "  bash $REPO/tools/run_tests.sh"
