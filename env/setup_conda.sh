#!/usr/bin/env bash
# 训练环境（练习 3）：用 Miniforge 创建 conda 环境 hci-train，安装 PyTorch、Ultralytics 等。
# 用法：
#   bash env/setup_conda.sh            官方源
#   bash env/setup_conda.sh --mirror   国内镜像：清华 conda-forge 与 PyPI（PyTorch 官方源失败时再试阿里云）
#   bash env/setup_conda.sh --cuda     有 NVIDIA 显卡时安装 GPU 版 PyTorch（体积数 GB）
# 没有 conda 时会先把 Miniforge 装到 ~/miniforge3。可以重复运行：环境已存在时只补装缺少的包。
# 注意：ROS 节点不用这个环境。运行 ROS（练习 2、4、期末）前先 conda deactivate。
if [ -z "${BASH_VERSION:-}" ]; then echo "请用 bash 运行：bash $0"; (return 0 2> /dev/null) && return 1; exit 1; fi  # sh 不认识数组语法；被 zsh 等 source 时只 return，不关掉终端
# 用 source 运行会把脚本的设置带进你的终端，一出错整个终端窗口都会关掉
if [ "${BASH_SOURCE[0]}" != "$0" ]; then echo "请用 bash 运行，不要 source：bash ${BASH_SOURCE[0]}"; return 1; fi
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
ENV_NAME=hci-train
PY_VERSION=3.14
MIRROR=0
CUDA=0
for a in "$@"; do
  case "$a" in
    --mirror) MIRROR=1 ;;
    --cuda) CUDA=1 ;;
    *) echo "未知参数：$a（可用 --mirror、--cuda）"; exit 1 ;;
  esac
done
if [ -n "${SUDO_USER:-}" ]; then
  echo "[错误] 不要用 sudo 运行这个脚本：需要管理员权限的步骤，脚本会自己调用 sudo（会提示输入密码）。"
  echo "       用 sudo 运行会把设置写到 root 的主目录里。请直接运行：bash $0"
  exit 1
fi
# 从这里开始要联网下载、安装。任何一步失败时（set -e 会让脚本停下），最后用中文说明怎么办
explain_failure() {
  local rc=$?
  [ "$rc" = 0 ] || echo "[错误] 安装没有完成：上面最后一条命令失败了（返回值 $rc）。多半是网络问题，在国内加 --mirror；修好后重新运行 bash env/setup_conda.sh 即可（可以重复运行，装好的部分会跳过）"
}
trap explain_failure EXIT
PIP_INDEX=()
[ $MIRROR = 1 ] && PIP_INDEX=(-i https://pypi.tuna.tsinghua.edu.cn/simple)

# 0) 找到 conda；没有就安装 Miniforge（conda-forge 社区维护，不受 Anaconda 商业条款限制）
find_conda() {
  for c in "${CONDA_EXE:-}" "$HOME/miniforge3/bin/conda" "$HOME/miniconda3/bin/conda" \
           "$HOME/anaconda3/bin/conda" "$(command -v conda 2>/dev/null)"; do
    if [ -n "$c" ] && [ -x "$c" ]; then echo "$c"; return 0; fi
  done
  return 1
}
NEW_CONDA=0
if ! CONDA=$(find_conda); then
  NEW_CONDA=1
  NAME="Miniforge3-Linux-$(uname -m).sh"
  URL="https://github.com/conda-forge/miniforge/releases/latest/download/$NAME"
  [ $MIRROR = 1 ] && URL="https://mirrors.tuna.tsinghua.edu.cn/github-release/conda-forge/miniforge/LatestRelease/$NAME"
  echo ">>> 没有找到 conda，安装 Miniforge 到 ~/miniforge3"
  echo "    下载：$URL"
  curl -fL --retry 3 -o "/tmp/$NAME" "$URL"
  bash "/tmp/$NAME" -b -u -p "$HOME/miniforge3"      # -u：上次没装完时可以直接覆盖
  rm -f "/tmp/$NAME"
  CONDA="$HOME/miniforge3/bin/conda"
  "$CONDA" init bash > /dev/null
  echo "    已在 ~/.bashrc 中加入 conda 的初始化代码（新开的终端才生效）"
fi
echo ">>> 使用 $("$CONDA" --version)：$CONDA"
# 新终端默认不激活任何 conda 环境：这样打开终端就是系统 Python，ROS 才能正常工作。
# conda 26.7 起把 auto_activate_base 改名为 auto_activate（旧名仍生效，只是会打印一句 WARNING）；
# 屏蔽这句无害的提示，与 setup_ros_env.sh 的写法一致。
"$CONDA" config --set auto_activate_base false 2> /dev/null
if [ $MIRROR = 1 ]; then
  "$CONDA" config --set show_channel_urls true
  "$CONDA" config --set custom_channels.conda-forge https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
fi

# 1) 创建环境（只用 conda-forge 频道）
if "$CONDA" env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  echo ">>> 环境 $ENV_NAME 已存在，只补装缺少的包"
else
  echo ">>> 创建环境 $ENV_NAME（Python $PY_VERSION）"
  "$CONDA" create -y -n "$ENV_NAME" --override-channels -c conda-forge "python=$PY_VERSION" pip
fi
PREFIX=$("$CONDA" env list | awk -v n="$ENV_NAME" '$1 == n {print $NF}')

# 2) 激活训练环境时，暂时去掉 source ROS 时设置的 PYTHONPATH、LD_LIBRARY_PATH、AMENT_PREFIX_PATH，
#    退出时恢复。否则系统 Python 的 ROS 包会混进训练环境（~/.bashrc 里 source 了 ROS 也没关系）。
mkdir -p "$PREFIX/etc/conda/activate.d" "$PREFIX/etc/conda/deactivate.d"
cat > "$PREFIX/etc/conda/activate.d/hci_isolate_ros.sh" <<'EOF'
# hci-course-code：训练环境不使用 ROS，暂时去掉 ROS 设置的路径
[ -n "${PYTHONPATH+x}" ] && export _HCI_OLD_PYTHONPATH="$PYTHONPATH"
[ -n "${LD_LIBRARY_PATH+x}" ] && export _HCI_OLD_LD_LIBRARY_PATH="$LD_LIBRARY_PATH"
[ -n "${AMENT_PREFIX_PATH+x}" ] && export _HCI_OLD_AMENT_PREFIX_PATH="$AMENT_PREFIX_PATH"
unset PYTHONPATH LD_LIBRARY_PATH AMENT_PREFIX_PATH
EOF
cat > "$PREFIX/etc/conda/deactivate.d/hci_isolate_ros.sh" <<'EOF'
# hci-course-code：退出训练环境时恢复 ROS 的路径
[ -n "${_HCI_OLD_PYTHONPATH+x}" ] && export PYTHONPATH="$_HCI_OLD_PYTHONPATH"
[ -n "${_HCI_OLD_LD_LIBRARY_PATH+x}" ] && export LD_LIBRARY_PATH="$_HCI_OLD_LD_LIBRARY_PATH"
[ -n "${_HCI_OLD_AMENT_PREFIX_PATH+x}" ] && export AMENT_PREFIX_PATH="$_HCI_OLD_AMENT_PREFIX_PATH"
unset _HCI_OLD_PYTHONPATH _HCI_OLD_LD_LIBRARY_PATH _HCI_OLD_AMENT_PREFIX_PATH
EOF
# 本脚本里直接调用环境中的 python，同样去掉 ROS 的路径
PY=(env -u PYTHONPATH -u LD_LIBRARY_PATH "$PREFIX/bin/python")

# 3) PyTorch：默认 CPU 版（约 200 MB）；直接 pip install torch 会装 CUDA 版（数 GB）。
#    锁定在实测过的 2.14.x，学期中途上游发布新版本也不影响学生。
#    已经装了 CPU 版、又加了 --cuda 时，换成 GPU 版
TORCH=("torch>=2.14,<2.15" "torchvision>=0.29,<0.30")
if "${PY[@]}" -c "import sys, torch
sys.exit(0 if torch.__version__.startswith('2.14.') and not ($CUDA and not torch.version.cuda) else 1)" 2> /dev/null; then
  echo ">>> 已安装 PyTorch $("${PY[@]}" -c 'import torch; print(torch.__version__)')，跳过"
elif [ $CUDA = 1 ]; then
  echo ">>> 安装 GPU 版 PyTorch（已有的 CPU 版会被替换）"
  "${PY[@]}" -m pip uninstall -y torch torchvision > /dev/null 2>&1 || true
  "${PY[@]}" -m pip install "${TORCH[@]}" "${PIP_INDEX[@]}"
else
  echo ">>> 安装 CPU 版 PyTorch"
  if ! "${PY[@]}" -m pip install "${TORCH[@]}" --index-url https://download.pytorch.org/whl/cpu --timeout 60; then
    TORCH_OK=0
    if [ $MIRROR = 1 ]; then
      echo "[提示] PyTorch 官方源失败，改试阿里云镜像（只含 CPU 版 wheel）"
      # 阿里云镜像只是文件列表：先从 PyPI 装好 torch 的纯 Python 依赖，再 --no-index 安装
      "${PY[@]}" -m pip install filelock typing-extensions setuptools sympy networkx jinja2 fsspec numpy pillow \
        "${PIP_INDEX[@]}" \
        && "${PY[@]}" -m pip install --no-index -f https://mirrors.aliyun.com/pytorch-wheels/cpu/ "${TORCH[@]}" \
        && TORCH_OK=1
    fi
    if [ $TORCH_OK = 0 ]; then
      echo "[提示] CPU 版 PyTorch 下载失败，改用默认源（含 CUDA，体积数 GB，请耐心等待）"
      "${PY[@]}" -m pip install "${TORCH[@]}" "${PIP_INDEX[@]}"
    fi
  fi
fi

# 4) 其余依赖
echo ">>> 安装 Ultralytics、ONNX、OpenCV 等"
"${PY[@]}" -m pip install -r "$HERE/requirements-train.txt" "${PIP_INDEX[@]}"
# Ultralytics 默认开着匿名使用统计（sync），会把使用情况发到它的服务器。课程强调隐私：关掉。
# 设置保存在 ~/.config/Ultralytics/settings.json，对这台电脑上的所有环境都有效
"${PY[@]}" -c "from ultralytics import settings; settings.update({'sync': False})" > /dev/null
echo ">>> 已关闭 Ultralytics 的匿名使用统计"

# 5) 练习 3 复用感知包与地基包的纯 Python 部分（YOLO 解码、YuNet、SFace、画框……）：
#    在环境的 site-packages 里放一个 .pth 文件，指向这两个包的源码目录。
#    激活环境、conda run、VS Code 选解释器都能找到它们，训练环境不需要安装 ROS。
SITE=$("${PY[@]}" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
printf '%s\n' "$REPO/hci_ws/src/hci_common" "$REPO/hci_ws/src/hci_perception" > "$SITE/hci_course.pth"
echo ">>> 已写入 $SITE/hci_course.pth（仓库移动位置后重新运行本脚本即可）"

# 6) 检查
MODEL="$REPO/hci_ws/src/hci_perception/hci_perception/models/face_detection_yunet_2023mar.onnx" \
  "${PY[@]}" - <<'PY'
import os, sys
import cv2, numpy, onnx, onnxruntime, torch, ultralytics
import hci_common, hci_perception  # 来自 hci_course.pth
print(f"Python {sys.version.split()[0]} | torch {torch.__version__} | ultralytics {ultralytics.__version__} | "
      f"opencv {cv2.__version__} | numpy {numpy.__version__} | onnxruntime {onnxruntime.__version__}")
det = cv2.FaceDetectorYN.create(os.environ["MODEL"], "", (320, 320), 0.6, 0.3, 50)
det.detect(numpy.zeros((320, 320, 3), numpy.uint8))
print("YuNet 人脸检测可以运行；GPU 可用：", torch.cuda.is_available())
PY
echo
echo "完成。练习 3 的命令都在训练环境里运行：conda activate $ENV_NAME"
[ $NEW_CONDA = 1 ] && echo "（刚装好 Miniforge：请先新开一个终端，或执行 source ~/.bashrc，才能使用 conda 命令）"
echo "运行 ROS（练习 2、4、期末）之前先 conda deactivate"
