#!/usr/bin/env bash
# 下载、校验 OpenCV Zoo 的人脸模型（YuNet 检测：MIT 许可；SFace 识别：Apache-2.0 许可）。
# 模型放在感知包里：hci_ws/src/hci_perception/hci_perception/models/
# 仓库自带 YuNet（约 230 KB）；SFace（约 37 MB）用到两步法时再下载。文件缺失或损坏时也运行本脚本：
#   bash tools/download_models.sh            # 校验 SHA256，只下载缺失或不一致的文件
#   bash tools/download_models.sh --mirror   # 在国内：从 hf-mirror.com（Hugging Face 的国内镜像）下载
if [ -z "${BASH_VERSION:-}" ]; then echo "请用 bash 运行：bash $0"; (return 0 2> /dev/null) && return 1; exit 1; fi  # sh 不认识数组语法；被 zsh 等 source 时只 return，不关掉终端
# 用 source 运行会把脚本的设置带进你的终端，一出错整个终端窗口都会关掉
if [ "${BASH_SOURCE[0]}" != "$0" ]; then echo "请用 bash 运行，不要 source：bash ${BASH_SOURCE[0]}"; return 1; fi
set -u
MIRROR=0
for a in "$@"; do
  case "$a" in
    --mirror) MIRROR=1 ;;
    *) echo "未知参数：$a（可用 --mirror）"; exit 2 ;;
  esac
done
if [ -n "${SUDO_USER:-}" ]; then
  echo "[错误] 不要用 sudo 运行这个脚本：它不需要管理员权限，用 root 的身份写下的文件，之后你自己就改不动了。"
  echo "       请直接运行：bash $0"
  exit 1
fi
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO/hci_ws/src/hci_perception/hci_perception/models" || exit 1

url() {  # 用法：url <模型名> <文件名>。两处发布的是同一个文件，下载后都按 SHA256 校验
  if [ $MIRROR = 1 ]; then
    echo "https://hf-mirror.com/opencv/$1/resolve/main/$2"
  else
    echo "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/$1/$2"
  fi
}

check() { [ -s "$1" ] && echo "$2  $1" | sha256sum --check --status; }

dl() {   # 用法：dl <模型名> <文件名> <sha256>
  if check "$2" "$3"; then echo "✓ $2 完好"; return 0; fi
  echo "下载 $2 ..."
  if ! curl -fL --retry 3 -o "$2.part" "$(url "$1" "$2")"; then
    rm -f "$2.part"
    if [ $MIRROR = 1 ]; then
      echo "✗ $2 下载失败，请检查网络后重试"
    else
      echo "✗ $2 下载失败，请检查网络后重试（在国内加 --mirror）"
    fi
    return 1
  fi
  mv "$2.part" "$2"
  if check "$2" "$3"; then
    echo "✓ $2 下载完成并校验通过"
  else
    echo "✗ $2 校验失败，请检查网络后重试"
    return 1
  fi
}

status=0
dl face_detection_yunet face_detection_yunet_2023mar.onnx \
   8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4 || status=1
dl face_recognition_sface face_recognition_sface_2021dec.onnx \
   0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79 || status=1
echo "模型目录：$PWD"
exit $status
