#!/usr/bin/env bash
# 一键检查课程环境。本课程有两个 Python 环境，分别检查：
#   bash env/check_env.sh          ROS 环境（练习 2、4、期末）：系统 Python + apt，不要激活 conda
#   bash env/check_env.sh train    训练环境（练习 3）：先 conda activate hci-train
if [ -z "${BASH_VERSION:-}" ]; then echo "请用 bash 运行：bash $0"; (return 0 2> /dev/null) && return 1; exit 1; fi  # sh 不认识数组语法；被 zsh 等 source 时只 return，不关掉终端
# 用 source 运行会把脚本的设置带进你的终端，一出错整个终端窗口都会关掉
if [ "${BASH_SOURCE[0]}" != "$0" ]; then echo "请用 bash 运行，不要 source：bash ${BASH_SOURCE[0]}"; return 1; fi
if [ -n "${SUDO_USER:-}" ]; then
  echo "[错误] 不要用 sudo 运行这个脚本：它不需要管理员权限，用 root 的身份写下的文件，之后你自己就改不动了。"
  echo "       请直接运行：bash $0"
  exit 1
fi
ok()   { echo -e "  \e[32m✓\e[0m $1"; }
bad()  { echo -e "  \e[31m✗\e[0m $1"; FAIL=$((FAIL+1)); }
warn() { echo -e "  \e[33m!\e[0m $1"; }
FAIL=0
REPO="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:-ros}"
export MODEL="$REPO/hci_ws/src/hci_perception/hci_perception/models/face_detection_yunet_2023mar.onnx"

# 代码的版本：向助教反馈问题时附上本脚本的输出，助教据此知道你用的是哪一版。
# 版本号写在各包的 package.xml 里；用 git clone 得到的仓库，再显示 git 的描述（标签、提交、有没有改动）
VERSION="$(sed -n 's:.*<version>\(.*\)</version>.*:\1:p' "$REPO/hci_ws/src/hci_common/package.xml")"
if [ -e "$REPO/.git" ] && command -v git > /dev/null; then
  VERSION="$VERSION，git $(git -C "$REPO" describe --tags --always --dirty 2> /dev/null || echo 未知)"
fi
echo "课程代码 v$VERSION（$REPO）"

echo "== 1. 系统 =="
# shellcheck source=/dev/null
. /etc/os-release
if [ "$VERSION_ID" = "26.04" ]; then ok "Ubuntu 26.04"; else bad "不是 Ubuntu 26.04：$PRETTY_NAME"; fi
if grep -qi microsoft /proc/version; then
  warn "检测到 WSL2：摄像头需要 usbipd 转发，也可以用视频文件代替"
  if [ -n "$DISPLAY$WAYLAND_DISPLAY" ]; then ok "WSLg 图形界面可用"; else bad "没有图形界面变量，请在 Windows 执行 wsl --update"; fi
else
  ok "原生 Linux（双系统）"
fi
case "$REPO" in  # WSL2 里 /mnt/c 等是 Windows 的磁盘，经网络文件系统访问，很慢
  /mnt/[a-z]/*) warn "仓库在 Windows 的磁盘上（$REPO）：编译和测试会慢好几倍，测试可能被误判为卡住。请移到 Ubuntu 的主目录里，例如 mv \"$REPO\" ~/" ;;
esac

if [ "$MODE" = "train" ]; then
  echo "== 2. 训练环境（conda）=="
  if [ "$CONDA_DEFAULT_ENV" = "hci-train" ]; then
    ok "已激活 conda 环境 hci-train"
  else
    bad "当前不在 hci-train 环境：先 conda activate hci-train（还没有这个环境就运行 bash env/setup_conda.sh）"
  fi
  case ":${PYTHONPATH-}:" in
    *"/opt/ros/"*) warn "PYTHONPATH 里有 ROS 的路径，可能干扰训练环境（用 setup_conda.sh 创建的环境会自动去掉）" ;;
  esac
  python - <<'PY' || FAIL=$((FAIL+1))
import importlib, os, sys
fail = 0
def chk(name, must=None, why=""):
    global fail
    try:
        m = importlib.import_module(name)
        v = getattr(m, "__version__", "?")
        if must and not must(v):
            print(f"  \033[31m✗\033[0m {name} {v}：{why}"); fail += 1; return m
        print(f"  \033[32m✓\033[0m {name} {v}"); return m
    except Exception as e:
        print(f"  \033[31m✗\033[0m {name} 导入失败：{e}"); fail += 1
print(f"     python = {sys.executable}（{sys.version.split()[0]}）")
torch = chk("torch")
if torch is not None:
    print("  \033[32m✓\033[0m GPU 可用" if torch.cuda.is_available() else "  \033[33m!\033[0m 没有可用 GPU，将用 CPU 训练（课程默认）")
if chk("ultralytics") is not None:
    from ultralytics import settings as ultralytics_settings
    if ultralytics_settings.get("sync", True):
        print("  \033[33m!\033[0m Ultralytics 的匿名使用统计开着：yolo settings sync=False（setup_conda.sh 会关掉）")
    else:
        print("  \033[32m✓\033[0m Ultralytics 的匿名使用统计已关闭")
cv2 = chk("cv2", must=lambda v: v.startswith("4."), why="需要 OpenCV 4.x（pip install \"opencv-python<5\"）")
chk("numpy"); chk("onnx"); chk("onnxruntime"); chk("PIL")
try:
    import hci_common, hci_perception  # noqa: F401  来自 setup_conda.sh 写入的 hci_course.pth
    print("  \033[32m✓\033[0m 能导入感知包与地基包的纯 Python 部分（hci_course.pth）")
except ImportError:
    print("  \033[31m✗\033[0m 找不到 hci_common、hci_perception：重新运行 bash env/setup_conda.sh"); fail += 1
try:
    import numpy as np
    det = cv2.FaceDetectorYN.create(os.environ["MODEL"], "", (320, 320), 0.6, 0.3, 50)
    det.detect(np.zeros((320, 320, 3), np.uint8))
    print("  \033[32m✓\033[0m YuNet 人脸检测可以运行")
except Exception as e:
    print(f"  \033[31m✗\033[0m YuNet 无法运行：{(str(e).strip().splitlines() or [repr(e)])[-1][:100]}"); fail += 1
sys.exit(1 if fail else 0)
PY
else
  echo "== 2. ROS 2 =="
  if [ -n "$CONDA_PREFIX" ]; then
    bad "conda 环境（$CONDA_PREFIX）处于激活状态：ROS 要用系统 Python，请先 conda deactivate"
    [ "$TERM_PROGRAM" = vscode ] && echo "     VS Code 的终端：确认打开的文件夹就是 hci-course-code（仓库里的设置会让终端不再自动激活 conda），然后关掉这个终端、新开一个"
  fi
  if [ "$ROS_DISTRO" = "lyrical" ]; then ok "ROS_DISTRO=lyrical"; else bad "ROS 2 Lyrical 未加载：执行 source /opt/ros/lyrical/setup.bash"; fi
  if command -v ros2 > /dev/null; then ok "ros2 命令可用"; else bad "找不到 ros2 命令"; fi
  echo "     ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0（默认）}  ROS_AUTOMATIC_DISCOVERY_RANGE=${ROS_AUTOMATIC_DISCOVERY_RANGE:-未设置}"
  if ros2 pkg prefix turtlesim > /dev/null 2>&1; then ok "turtlesim 已安装"; else bad "缺少 turtlesim：sudo apt install ros-lyrical-turtlesim"; fi
  if command -v colcon > /dev/null; then ok "colcon 可用"; else bad "缺少 colcon：sudo apt install ros-dev-tools"; fi
  if command -v c++ > /dev/null || command -v g++ > /dev/null || command -v clang++ > /dev/null; then
    ok "C++ 编译器可用"
  else
    bad "没有 C++ 编译器，编译消息包时会报 No CMAKE_CXX_COMPILER：sudo apt install build-essential"
  fi
  # 例如从 24.04 升级上来，~/.bashrc 里还 source 着 Jazzy：两个版本混在一起会出各种怪错
  OTHER_ROS=$(echo "${AMENT_PREFIX_PATH-}:${PYTHONPATH-}" | tr ':' '\n' | grep -o '^/opt/ros/[^/]*' \
    | grep -vx /opt/ros/lyrical | sort -u | tr '\n' ' ')
  [ -z "$OTHER_ROS" ] || bad "还加载了其他版本的 ROS（${OTHER_ROS% }）：在 ~/.bashrc 里删掉 source 它的那一行，新开终端"
  # 以前给其他 Ubuntu 版本加的 ROS 软件源（例如 24.04 的 noble）会混进不匹配的包。
  # apt 列出每个启用的源：地址、版本代号（26.04 是 resolute）、所在的文件和行号
  # shellcheck disable=SC2016  # $(SITE) 这些由 apt 展开
  STALE=$(apt-get indextargets --no-release-info --format '$(SITE) $(RELEASE) $(SOURCESENTRY)' 2> /dev/null \
    | awk '$1 ~ /\/ros[0-9]*(-testing)?\/ubuntu\/?$/ && $2 != "resolute" { print "       " $3 "（" $2 "）" }' \
    | sort -u)
  if [ -n "$STALE" ]; then
    warn "下面的 ROS 软件源是给其他 Ubuntu 版本的，会混进不匹配的包。删掉它们（冒号后面是行号），再 sudo apt update："
    echo "$STALE"
  fi

  echo "== 3. 系统 Python 与依赖 =="
  /usr/bin/python3 - <<'PY' || FAIL=$((FAIL+1))
import importlib, os, sys
fail = 0
def chk(name, hint):
    global fail
    try:
        m = importlib.import_module(name)
        print(f"  \033[32m✓\033[0m {name} {getattr(m, '__version__', '')}"); return m
    except Exception as e:
        print(f"  \033[31m✗\033[0m {name} 导入失败（{e}）：{hint}"); fail += 1
print(f"     python = {sys.executable}（{sys.version.split()[0]}）")
chk("rclpy", "先 source /opt/ros/lyrical/setup.bash")
np = chk("numpy", "sudo apt install python3-numpy")
cv2 = chk("cv2", "sudo apt install python3-opencv")
chk("PIL", "sudo apt install python3-pil")
chk("onnxruntime", "sudo apt install python3-onnxruntime")
chk("yaml", "sudo apt install python3-yaml")
for name in ("pytest", "hypothesis", "pytest_timeout"):  # 测试工具：没有时只影响 run_tests.sh
    try:
        importlib.import_module(name)
    except ImportError:
        print(f"  \033[33m!\033[0m 测试工具 {name} 没装：bash env/setup_ros_env.sh 会安装")
if cv2 is not None and np is not None:
    try:
        det = cv2.FaceDetectorYN.create(os.environ["MODEL"], "", (320, 320), 0.6, 0.3, 50)
        det.detect(np.zeros((320, 320, 3), np.uint8))
        print("  \033[32m✓\033[0m YuNet 人脸检测可以运行")
    except Exception as e:
        print(f"  \033[31m✗\033[0m YuNet 无法运行：{(str(e).strip().splitlines() or [repr(e)])[-1][:100]}"); fail += 1
sys.exit(1 if fail else 0)
PY

  echo "== 4. 摄像头与字体 =="
  VIDEOS=(/dev/video*)
  if [ ! -e "${VIDEOS[0]}" ]; then
    warn "没有 /dev/video*：WSL2 请用 usbipd 挂载摄像头（README 第 4.7 节），或改用视频文件（source:=视频绝对路径）"
  elif [ -r "${VIDEOS[0]}" ] && [ -w "${VIDEOS[0]}" ]; then
    ok "发现摄像头设备：${VIDEOS[*]}"
  else
    warn "有摄像头设备，但没有权限使用：sudo usermod -aG video \$USER，然后重新登录（WSL2：在 PowerShell 执行 wsl --shutdown）"
  fi
  if fc-list :lang=zh 2> /dev/null | grep -q .; then ok "已安装中文字体"; else warn "没有中文字体：sudo apt install fonts-noto-cjk"; fi

  echo "== 5. 工作空间 =="
  WS="$REPO/hci_ws"
  if [ -d "$WS/install" ]; then
    if ros2 pkg prefix hci_bringup > /dev/null 2>&1; then ok "hci_ws 已编译并加载"
    else warn "hci_ws 已编译但未加载：source $WS/install/setup.bash"; fi
    EXE="$WS/install/hci_perception/lib/hci_perception/recognizer_node"
    if [ -f "$EXE" ]; then
      SHEBANG=$(head -1 "$EXE")
      case "$SHEBANG" in
        "#!/usr/bin/python3"*) ok "节点使用系统 Python（${SHEBANG#\#!}）" ;;
        *) bad "节点的解释器是 ${SHEBANG#\#!}，不是系统 Python：conda deactivate 后删除 build install log 重新编译" ;;
      esac
    fi
  else
    warn "hci_ws 尚未编译：cd $WS && colcon build --symlink-install"
  fi
fi

echo
if [ $FAIL -eq 0 ]; then echo -e "\e[32m环境检查通过\e[0m"; else echo -e "\e[31m有 $FAIL 项未通过，请按提示处理\e[0m"; fi
[ $FAIL -eq 0 ]
