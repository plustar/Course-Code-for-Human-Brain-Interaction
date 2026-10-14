#!/usr/bin/env bash
# 运行测试：先检查环境，再按层运行，最后打印汇总表；有失败就返回非 0。
#
#   bash tools/run_tests.sh           ROS 环境：L0 静态检查、L1 单元、L2 节点、L3 系统（约 7 分钟）
#   bash tools/run_tests.sh --quick   只跑 L1 单元测试（约 1 分钟）
#   bash tools/run_tests.sh --cov     另外打印覆盖率（需要 python3-pytest-cov）
#   bash tools/run_tests.sh --gui     连需要弹出窗口的测试一起跑（WSLg 或双系统的桌面）
#   bash tools/run_tests.sh train     训练环境（先 conda activate hci-train）：感知核心与练习 3 的
#                                     单元测试，加上训练冒烟（L4）
#
# 用自己的照片和模型测试"仿真里认出我"（只在本机读取，不复制、不入库）：
#   HCI_ME_PHOTO=/绝对路径/me.jpg HCI_ME_MODEL=/绝对路径/best.onnx bash tools/run_tests.sh
#
# 每组测试最多跑 5 分钟（环境变量 HCI_TEST_GROUP_LIMIT 可改，单位秒）。超时的组多半是卡住了：
# 脚本记下卡在哪一行，结束它，再自动重跑一次，汇总里会注明。
# L3 系统测试偶发失败（ros2 launch 收到 Ctrl+C 时自身偶尔非 0 退出）同样自动重跑一次：
# 只有连续两次失败才算真失败，真正坏掉的测试照样会报出来。
#
# 每次的结果与节点日志在 hci_ws/log/run_tests/latest/ 里。只想跑某一个文件时：
#   source hci_ws/install/setup.bash
#   cd hci_ws/src/hci_behavior && python3 -m pytest test/test_state_machine.py -k greet
if [ -z "${BASH_VERSION:-}" ]; then echo "请用 bash 运行：bash $0"; (return 0 2> /dev/null) && return 1; exit 1; fi  # sh 不认识数组语法；被 zsh 等 source 时只 return，不关掉终端
# 用 source 运行会把脚本的设置带进你的终端，一出错整个终端窗口都会关掉
if [ "${BASH_SOURCE[0]}" != "$0" ]; then echo "请用 bash 运行，不要 source：bash ${BASH_SOURCE[0]}"; return 1; fi
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
MODE=ros
QUICK=0
COV=0
GUI=0
for arg in "$@"; do
  case "$arg" in
    train) MODE=train ;;
    --quick) QUICK=1 ;;
    --cov) COV=1 ;;
    --gui) GUI=1 ;;
    -h|--help) sed -n '2,/^[^#]/{/^#/s/^# \{0,1\}//p}' "$0"; exit 0 ;;  # 打印开头的说明
    *) echo "未知参数：$arg（可用 train、--quick、--cov、--gui；--help 查看说明）"; exit 2 ;;
  esac
done
if [ -n "${SUDO_USER:-}" ]; then
  echo "[错误] 不要用 sudo 运行这个脚本：它不需要管理员权限，用 root 的身份写下的文件，之后你自己就改不动了。"
  echo "       请直接运行：bash $0"
  exit 1
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
RESULTS="$REPO/hci_ws/log/run_tests/$STAMP"
mkdir -p "$RESULTS"
ln -sfn "$STAMP" "$REPO/hci_ws/log/run_tests/latest"
START=$SECONDS
GROUP_LIMIT="${HCI_TEST_GROUP_LIMIT:-300}"
PACKAGES=(hci_common hci_perception hci_behavior hci_sim hci_bringup)
ROOT_TESTS=(tests exercises/ros_basics/tests exercises/face_recognition/tests)

fail() { echo "[错误] $*"; exit 1; }

display_width() {  # 字符串在终端里占几格：中文占两格，用来对齐汇总表
  $PYTHON -c 'import sys, unicodedata as u
print(sum(2 if u.east_asian_width(c) in "WF" else 1 for c in sys.argv[1]))' "$1"
}

# ---------- 运行一组 pytest，超过 GROUP_LIMIT 秒就结束它 ----------
# 先发 SIGABRT：faulthandler 会把每个线程停在哪一行写进日志（PYTHONFAULTHANDLER 让 pytest
# 结束以后、进程退出时卡住也能写出来）；30 秒后仍未退出就强制结束。超时的返回值是 124（或
# 137）。HCI_TEST_GROUP 标记这一组启动的所有进程（测试里的 ros2 launch 各自成为一个会话），
# 超时后据此清理，不让它们干扰重跑。
# 用法：pytest_group <标记> <目录> <日志> <junit 文件> <标记表达式> [pytest 的其他参数...]
pytest_group() {
  local tag=$1 dir=$2 log=$3 xml=$4 expr=$5
  shift 5
  (cd "$dir" && HCI_TEST_GROUP=$tag PYTHONFAULTHANDLER=1 timeout -s ABRT -k 30 "$GROUP_LIMIT" \
     $PYTHON -m pytest -p no:cacheprovider -q -m "$expr" --junit-xml="$xml" "$@") > "$log" 2>&1
}

kill_group() {  # 结束带有这个 HCI_TEST_GROUP 标记、还没退出的进程
  local f pid pids=()
  for f in /proc/[0-9]*/environ; do
    { tr '\0' '\n' < "$f"; } 2> /dev/null | grep -qxF "HCI_TEST_GROUP=$1" || continue
    pid=${f#/proc/}
    pids+=("${pid%/environ}")
  done
  [ ${#pids[@]} = 0 ] || kill -KILL "${pids[@]}" 2> /dev/null
}

stuck_at() {  # 从 faulthandler 写进日志的调用栈里，找出最里层的位置和本仓库里最近的一处
  $PYTHON - "$1" "$REPO" <<'PY'
import re
import sys

text = open(sys.argv[1], encoding='utf-8', errors='replace').read()
# 每个线程一段，收到信号的线程标为 Current thread；信号落在非 Python 线程上时没有这一段，
# 就看最后一段（通常是主线程）
heads = list(re.finditer(r'^(Current thread|Thread) 0x[0-9a-f]+.*$', text, re.M))
head = next((h for h in heads if h.group(1) == 'Current thread'), heads[-1] if heads else None)
stack = ''
if head:
    after = [h.start() for h in heads if h.start() > head.start()]
    stack = text[head.end():after[0] if after else len(text)]
frames = re.findall(r'File "([^"]+)", line (\d+) in (\S+)', stack)


def short(frame):
    path, line, func = frame
    return f"{'/'.join(path.split('/')[-2:])}:{line} {func}"


ours = next((f for f in frames if f[0].startswith(sys.argv[2])), None)
if frames:
    print(short(frames[0]) + (f' ← {short(ours)}' if ours and ours != frames[0] else ''))
elif '[100%]' in text:
    print('进程退出时，测试都已跑完')
else:
    print('位置未知')
PY
}

# ---------- 在一个目录里运行一层测试，结果写进 junit 文件 ----------
# 用法：run_pytest <层> <名称> <目录> <标记表达式> [pytest 的其他参数...]
# 覆盖率统计哪些代码由调用者放在数组 COV_SRC 里（只在 --cov 时使用）
COV_SRC=()
timed_out() { [ "$1" = 124 ] || [ "$1" = 137 ]; }
run_pytest() {
  local layer=$1 name=$2 dir=$3 expr=$4
  shift 4
  local xml="$RESULTS/$layer--$name.xml" log="$RESULTS/$layer--$name.log" t0=$SECONDS
  local cov_args=() tag="$STAMP-$layer-$name" where pad
  pad=$((16 - $(display_width "$name")))  # 汇总表里名称占 16 格
  [ $pad -gt 0 ] || pad=0
  if [ $COV = 1 ] && [ ${#COV_SRC[@]} -gt 0 ]; then
    cov_args=("${COV_SRC[@]}" --cov-report=)
    export COVERAGE_FILE="$RESULTS/.coverage.$layer.$name"
  fi
  pytest_group "$tag-1" "$dir" "$log" "$xml" "$expr" "${cov_args[@]}" "$@"
  local rc=$?
  if timed_out $rc; then  # 卡住了：记下卡在哪里，清理干净，重跑一次
    kill_group "$tag-1"
    rm -f "$xml"
    mv "$log" "${log%.log}.timeout.log"
    where=$(stuck_at "${log%.log}.timeout.log")
    printf '  %s%*s %s\n' "$name" $pad '' "超过 $GROUP_LIMIT 秒没有结束（卡在 $where），已结束它，重跑一次"
    echo "$layer $name（卡在 $where）" >> "$RESULTS/retried.txt"
    t0=$SECONDS
    pytest_group "$tag-2" "$dir" "$log" "$xml" "$expr" "${cov_args[@]}" "$@"
    rc=$?
    if timed_out $rc; then  # 重跑又卡住了：这一组没有结果
      kill_group "$tag-2"
      rm -f "$xml"
      where=$(stuck_at "$log")
      printf '  %s%*s %s\n' "$name" $pad '' "重跑仍然超时（卡在 $where），这一组测试没有跑完（日志：$log）"
      echo "$layer $name（重跑仍然超时，卡在 $where）" >> "$RESULTS/crashed.txt"
      FAILED=1
      return 0
    fi
  fi
  # L3 系统测试偶发失败：ros2 launch 收到 Ctrl+C 时，偶尔自身以非 0 退出，而节点其实已经
  # 干净停下（见 docs/VERIFICATION.md 更新记录的 2.1.1）。与上面的超时重跑同一策略：失败就自动
  # 重跑一次，只有重跑仍失败才算真失败——真正坏掉的测试会连续两次失败，照样报出来。
  if [ "$layer" = L3 ] && [ $rc = 1 ] && [ -s "$xml" ]; then
    mv "$log" "${log%.log}.flaky.log"
    printf '  %s%*s %s\n' "$name" $pad '' "首次有失败，自动重跑一次"
    echo "$layer $name（首次失败，重跑一次）" >> "$RESULTS/retried.txt"
    t0=$SECONDS
    pytest_group "$tag-r" "$dir" "$log" "$xml" "$expr" "${cov_args[@]}" "$@"
    rc=$?
    timed_out $rc && kill_group "$tag-r"
  fi
  if [ $rc = 5 ]; then  # 这一层在这里没有测试
    rm -f "$xml"
    return 0
  fi
  local summary
  summary="$(grep -E '^(=+ )?[0-9]+ (passed|failed|skipped|deselected|error)' "$log" | tail -1 \
             | sed -e 's/=//g' -e 's/^ *//' -e 's/ in [0-9.]*s.*//')"
  printf '  %s%*s %s（%d 秒）\n' "$name" $pad '' "${summary:-没有输出}" $((SECONDS - t0))
  if [ $rc != 0 ]; then
    echo "  ---- $name 的失败详情（完整输出见 $log）"
    grep -E '^(FAILED|ERROR) ' "$log" | head -20 | sed 's/^/  /'
    if [ $rc != 1 ] || [ ! -s "$xml" ]; then
      # pytest 自己异常退出（崩溃、被中断）：这一组没有跑完，下面汇总的项数里也没有它
      echo "  pytest 异常退出（返回值 $rc），这一组测试没有跑完。日志开头：$(head -c 300 "$log" | head -3 | tr '\n' ' ')"
      echo "$layer $name（返回值 $rc）" >> "$RESULTS/crashed.txt"
    fi
    FAILED=1
  fi
}

run_layer() {  # 用法：run_layer <层> <标题> <标记表达式>
  local layer=$1 title=$2 expr=$3
  echo "== $title =="
  if [ "$MODE" = ros ]; then
    for pkg in "${PACKAGES[@]}"; do
      COV_SRC=(--cov="$pkg")
      run_pytest "$layer" "$pkg" "$REPO/hci_ws/src/$pkg" "$expr"
    done
    local dirs=()
    for d in "${ROOT_TESTS[@]}"; do [ -d "$REPO/$d" ] && dirs+=("$d"); done
    COV_SRC=(--cov="$REPO/exercises/ros_basics" --cov="$REPO/exercises/face_recognition")
    [ ${#dirs[@]} = 0 ] || run_pytest "$layer" 练习与仓库级 "$REPO" "$expr and not train" "${dirs[@]}"
  else
    COV_SRC=(--cov=hci_common --cov=hci_perception --cov="$REPO/exercises/face_recognition")
    run_pytest "$layer" 训练环境 "$REPO" "$expr" \
      hci_ws/src/hci_common/test hci_ws/src/hci_perception/test exercises/face_recognition/tests
  fi
}

FAILED=0
case "$REPO" in  # WSL2 里 /mnt/c 等是 Windows 的磁盘，经网络文件系统访问，很慢
  /mnt/[a-z]/*) echo "[提示] 仓库在 Windows 的磁盘上（$REPO）：测试会慢好几倍，建议移到 Ubuntu 的主目录里" ;;
esac
if [ "$MODE" = ros ]; then
  # ---------- 环境：Ubuntu 26.04 + Lyrical，系统 Python，不在 conda 里 ----------
  # shellcheck source=/dev/null
. /etc/os-release
  [ "${VERSION_ID:-}" = 26.04 ] || fail "本课程使用 Ubuntu 26.04，当前系统是 ${PRETTY_NAME:-未知}"
  if [ -n "${CONDA_PREFIX:-}" ]; then
    echo "[错误] conda 环境（$CONDA_PREFIX）处于激活状态：ROS 要用系统 Python，请先 conda deactivate"
    [ "${TERM_PROGRAM:-}" = vscode ] && echo "       VS Code 的终端：确认打开的文件夹就是 hci-course-code（仓库里的设置会让终端不再自动激活 conda），然后关掉这个终端、新开一个"
    exit 1
  fi
  [ -f /opt/ros/lyrical/setup.bash ] || fail "没有找到 ROS 2 Lyrical：请先按 README 安装"
  command -v c++ > /dev/null || command -v g++ > /dev/null || command -v clang++ > /dev/null \
    || fail "没有 C++ 编译器（编译消息包要用）：sudo apt install -y build-essential"
  set +u  # ROS 的 setup 脚本会读取未定义的变量
  # shellcheck disable=SC1091
  . /opt/ros/lyrical/setup.bash
  set -u
  PYTHON=/usr/bin/python3
  echo "== 环境 ==            Ubuntu $VERSION_ID · Lyrical · Python $($PYTHON -c 'import sys; print(sys.version.split()[0])') · 未激活 conda ✓"

  # ---------- 编译（--symlink-install：测试用的就是仓库里的源码）----------
  echo "== 编译 ==            colcon build --symlink-install（日志：$RESULTS/build.log）"
  (cd "$REPO/hci_ws" && colcon build --symlink-install --event-handlers console_cohesion- \
     > "$RESULTS/build.log" 2>&1) || { tail -30 "$RESULTS/build.log"; fail "编译失败"; }
  set +u
  # shellcheck disable=SC1091
  . "$REPO/hci_ws/install/setup.bash"
  set -u
  export ROS_LOG_DIR="$RESULTS/ros_logs"  # 测试里启动的节点，日志放在这里
  [ $GUI = 1 ] && export HCI_TEST_GUI=1

  if [ $QUICK = 1 ]; then
    run_layer L1 "L1 单元" "not ros and not launch and not linter"
  else
    run_layer L0 "L0 静态检查" "linter"
    run_layer L1 "L1 单元" "not ros and not launch and not linter"
    run_layer L2 "L2 节点" "ros and not launch and not linter"
    run_layer L3 "L3 系统" "launch"
  fi
else
  # ---------- 训练环境：conda 的 hci-train，不 source ROS ----------
  [ "${CONDA_DEFAULT_ENV:-}" = hci-train ] || fail "请先 conda activate hci-train（第一次使用先运行 bash env/setup_conda.sh）"
  [ -z "${AMENT_PREFIX_PATH:-}" ] \
    || fail "这个终端在激活 hci-train 之后又 source 了 ROS：新开一个终端，只执行 conda activate hci-train（仍然出现就重新运行 bash env/setup_conda.sh）"
  PYTHON=python
  $PYTHON -c 'import hci_common, hci_perception' 2> /dev/null \
    || fail "训练环境找不到 hci_common、hci_perception：请重新运行 bash env/setup_conda.sh"
  echo "== 环境 ==            conda hci-train · Python $($PYTHON -c 'import sys; print(sys.version.split()[0])') · 没有 source ROS ✓"
  run_layer L1 "L1 单元" "not ros and not launch and not linter and not train"
  [ $QUICK = 1 ] || run_layer L4 "L4 训练冒烟" "train"
fi

# ---------- 汇总：通过、跳过（及原因）、失败 ----------
$PYTHON - "$RESULTS" $((SECONDS - START)) <<'PY'
import collections
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

results, seconds = Path(sys.argv[1]), int(sys.argv[2])
total = collections.Counter()
reasons = collections.Counter()
for xml in sorted(results.glob('*.xml')):
    for case in ET.parse(xml).getroot().iter('testcase'):
        skipped = case.find('skipped')
        if case.find('failure') is not None or case.find('error') is not None:
            total['failed'] += 1
        elif skipped is not None:
            total['skipped'] += 1
            reason = (skipped.get('message') or '').split(': ', 1)[-1]
            reasons[reason] += 1
        else:
            total['passed'] += 1
if reasons:
    print('跳过的项目：')
    for reason, n in reasons.most_common():
        print(f'  {n} 项  {reason}')
retried = results / 'retried.txt'
if retried.exists():
    print('第一次未通过、自动重跑过的测试组（超时或 L3 偶发失败；项数以重跑的结果为准）：')
    for group in retried.read_text(encoding='utf-8').splitlines():
        print(f'  {group}')
crashed = results / 'crashed.txt'
groups = crashed.read_text(encoding='utf-8').splitlines() if crashed.exists() else []
if groups:
    print(f'没有跑完的测试组（{len(groups)} 组，不在下面的项数里）：')
    for group in groups:
        print(f'  {group}')
print(f"结果：{total['passed']} 项通过，{total['skipped']} 项跳过，{total['failed']} 项失败，"
      + (f'另有 {len(groups)} 组没有跑完，' if groups else '')
      + f'用时 {seconds // 60} 分 {seconds % 60} 秒')
PY

if [ $COV = 1 ]; then
  echo "== 覆盖率（测试进程内执行的语句；ros2 launch 启动的子进程不计）=="
  (cd "$RESULTS" && $PYTHON -m coverage combine .coverage.* > /dev/null 2>&1 \
     && $PYTHON -m coverage report --omit='*/test/*,*/tests/*,*/setup.py,*/conftest.py' 2>&1 \
     | sed "s|$REPO/||")
fi
echo "详细结果：$RESULTS"
exit $FAILED
