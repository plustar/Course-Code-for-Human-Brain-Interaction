# 测试

本仓库约 480 项自动测试，覆盖从一个函数到整个仿真闭环的各个层次。它们有三个用处：检查你的环境装对了没有；改代码时立刻知道有没有改坏；也是读懂代码的捷径（测试名就是一句话的需求，例如 `test_greets_once_at_the_greet_distance`）。

## 1. 一条命令

```bash
bash tools/run_tests.sh            # ROS 环境：L0–L3，约 7 分钟
bash tools/run_tests.sh --quick    # 只跑 L1 单元测试，约 1 分钟
bash tools/run_tests.sh --cov      # 另外打印覆盖率
bash tools/run_tests.sh --gui      # 连需要弹出窗口的测试一起跑（WSLg 或双系统的桌面）

conda activate hci-train           # 训练环境：另开一个终端（激活时会自动去掉 ROS 的路径）
cd $HCI_ROOT
bash tools/run_tests.sh train      # 感知核心与练习 3 的单元测试，加训练冒烟（L4），约 1 分钟
```

脚本先检查环境（Ubuntu 26.04、Lyrical、没有激活 conda、有 C++ 编译器），再编译工作空间，然后按层运行，最后打印汇总表。有失败就返回非 0。输出大致是这样：

```text
== 环境 ==            Ubuntu 26.04 · Lyrical · Python 3.14.4 · 未激活 conda ✓
== 编译 ==            colcon build --symlink-install（日志：…/hci_ws/log/run_tests/20261004_131140/build.log）
== L0 静态检查 ==
  hci_common       3 passed, 1 skipped, 57 deselected（18 秒）
  ……
== L3 系统 ==
  hci_bringup      9 passed, 2 skipped, 54 deselected（51 秒）
  练习与仓库级     13 passed, 163 deselected（37 秒）
跳过的项目：
  5 项  下载不到 http://download.ros.org/schema/package_format3.xsd（离线或网络受限），联网后再检查 package.xml
  ……
结果：473 项通过，11 项跳过，0 项失败，用时 5 分 8 秒
详细结果：…/hci_ws/log/run_tests/20261004_131140
```

`deselected` 是本层不运行、留给其他层的测试。跳过不等于失败：缺少某个条件（离线、没下载 SFace 模型、没设置自己的照片）的测试会被跳过，并在最后列出原因。每次的完整输出、JUnit 结果和测试时启动的节点日志都在 `hci_ws/log/run_tests/latest/`。

## 2. 测试分层

| 层 | 测什么 | 怎么测 | 在哪个环境 | 标记 |
|---|---|---|---|---|
| L0 静态检查 | 代码风格、文档字符串、类型标注、package.xml、shell 脚本 | ament_flake8、ament_pep257、ament_mypy、ament_xmllint、shellcheck | ROS | `linter` |
| L1 单元 | 纯 Python 部分：相机模型、解码、估计与状态机、渲染、数据集划分…… | pytest；关键不变量用 hypothesis 随机生成成百上千组输入 | 两个环境 | 无 |
| L2 节点 | 单个节点的接线：参数、订阅发布、header、内参、消息类型识别、暂停、退出停车 | 在测试进程里创建节点，注入替身，用探针节点收发 | ROS | `ros` |
| L3 系统 | 真实进程的组合：视频管线、仿真闭环、换平台、练习 2 的脚本 | 子进程里运行 `ros2 launch` 或脚本，像在终端里一样按 Ctrl+C | ROS | `launch` |
| L4 训练冒烟 | 训练 → 评估 → 导出 → 用节点的代码加载 | 合成小数据集，从网络结构训练 1 轮，不下载权重 | 训练 | `train` |
| L5 手工验收 | 真摄像头、usbipd、Gazebo、WSLg 窗口 | docs/VERIFICATION.md 的清单 | 你的笔记本 | — |

## 3. 测试放在哪里

| 位置 | 内容 |
|---|---|
| `hci_ws/src/<包>/test/` | 每个 ROS 包自己的测试：4 个 ament 检查（`test_flake8.py` 等），加上单元、节点、系统测试。按 ROS 惯例，`colcon test` 会逐包运行它们 |
| `exercises/ros_basics/tests/` | 练习 2 的脚本（L3） |
| `exercises/face_recognition/tests/` | 练习 3 各步的函数（L1）与训练冒烟（L4）；合成测试数据的工具在 `synthetic.py` |
| `tests/` | 仓库级检查：分层规则（`test_architecture.py`）、文档与代码一致（`test_docs.py`）、练习与测试代码的风格、环境脚本、仓库卫生 |

## 4. 标记与跳过

标记写在 `pytest.ini` 里，用 `-m` 选择，例如 `-m "not launch"` 跳过系统测试：

| 标记 | 含义 |
|---|---|
| `ros` | 需要 ROS 2 环境（rclpy 与消息包） |
| `launch` | 启动真实的 ROS 进程，较慢 |
| `slow` | 单项超过 10 秒 |
| `gui` | 要弹出窗口；只有 `--gui`（环境变量 `HCI_TEST_GUI=1`）时才运行 |
| `train` | 需要训练环境（ultralytics） |
| `linter` | 静态检查 |

ament 的检查还各自带有 `flake8`、`pep257`、`mypy`、`xmllint` 标记。每项测试最多 60 秒（`pytest-timeout`），慢的系统测试在文件里单独放宽。

pytest-timeout 管不到卡在 C++ 代码里的情况（例如 ROS 的通信库在进程退出时死锁），所以 `run_tests.sh` 另外给每一组（一个包的一层）5 分钟。超时的组多半是卡住了：脚本先发 SIGABRT，让 Python 的 faulthandler 把每个线程停在哪一行写进日志，再结束这一组启动的所有进程（包括测试里 `ros2 launch` 出来的），然后自动重跑一次。上限可以用环境变量 `HCI_TEST_GROUP_LIMIT` 改（单位秒）。此外，**L3 系统测试首次失败也会自动重跑一次**：`ros2 launch` 收到 Ctrl+C 时，偶尔自身以非 0 退出，而节点其实已经干净停下；只有连续两次都失败才算真失败，重跑过的组会在汇总里注明。

训练环境里没有 ROS：`hci_common`、`hci_perception` 的 `test/conftest.py` 会自动略过需要 ROS 的文件，只运行纯 Python 部分，这样同一份核心代码在两个环境里都测过。

## 5. 不用脚本，自己运行

脚本做的事，用 ROS 官方的命令也能做：

```bash
cd $HCI_ROOT/hci_ws
colcon build --symlink-install
colcon test --event-handlers console_direct+ --executor sequential
colcon test-result --verbose
source install/setup.bash
cd $HCI_ROOT
python3 -m pytest -m "not train"          # 练习与仓库级（pytest.ini 里的 testpaths）
```

只跑某个文件或某一项（先 `source hci_ws/install/setup.bash`）：

```bash
cd $HCI_ROOT/hci_ws/src/hci_behavior
python3 -m pytest test/test_state_machine.py -k greet -v
```

各个 ROS 包里都有同名的 `test_flake8.py` 等文件，所以一次只给 pytest 一个包的目录；要跑全部包请用 `colcon test` 或 `run_tests.sh`。

## 6. 测试怎样互不干扰

- **独占的 ROS_DOMAIN_ID**：每个测试进程用 Lyrical 自带的 rmw_test_fixture 分到一个与别人不冲突的 domain，并且只在本机发现（`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`）。局域网里同学的 ROS 程序干扰不到测试，测试也不打扰你正在运行的节点。测试启动的子进程继承同一个 domain。
- **随机命名空间**：节点测试把被测节点放进 `/test_123456789` 这样的命名空间，前一个测试留下的话题不会串进来。
- **不弹窗**：系统测试里的 turtlesim 用 Qt 的 offscreen 模式运行；显示节点在没有 `DISPLAY` 时自动不弹窗。
- **不留进程**：`RosProcess.stop()` 像按 Ctrl+C 一样停止整个进程组，等不及时强制结束，不会留下后台节点。

这些工具都在 `hci_common/ros/testing.py`。

## 7. 给你改过的代码写测试

挑和你的改动同一层的例子照着写。

**纯 Python 的单元测试**（`hci_behavior/test/test_state_machine.py`）：

```python
def test_greets_once_at_the_greet_distance():
    m = machine()
    first, second = (m.step(person(0.0, 0.95), others_seen=False) for _ in range(2))
    assert first.state == second.state == State.GREET
    assert first.greet and not second.greet
```

**属性测试**：不写具体例子，而是说明"对任意输入都成立"的性质，由 hypothesis 随机生成 1000 组输入去找反例（`hci_behavior/test/test_safety.py`）：

```python
@settings(max_examples=1000, deadline=None)
@given(commands, ages, st.booleans(), distances)
def test_never_reverses_and_never_exceeds_the_speed_limit(cmd, age, enabled, distance):
    out = SAFETY.check(cmd, age, enabled, distance)
    assert 0.0 <= out.linear <= CONFIG.max_speed
```

**节点测试**：在测试进程里创建节点（可以注入替身），用探针节点 `Probe` 收发消息，`spin_until` 等条件成立（`hci_perception/test/test_recognizer_node.py`）：

```python
def test_header_is_copied_and_image_size_reported(ros_context, namespace):
    node, probe = make_node(namespace), Probe(namespace)
    result = send_until_detected(node, probe, 'image_raw', image_msg(frame_id='my_camera'))
    assert result.header.frame_id == 'my_camera'
```

**系统测试**：在子进程里运行 `ros2 launch`，观察话题，最后像按 Ctrl+C 一样停止（`hci_bringup/test/test_system_sim.py`）。ROS 官方的 launch_testing 写法见 `hci_bringup/test/test_perception_launch.py`，第 8 讲讲集成测试时可以对照它。

## 8. 覆盖率

`bash tools/run_tests.sh --cov` 在最后打印每个文件的语句覆盖率。它只统计测试进程里执行过的代码，`ros2 launch` 启动的子进程不计，所以 `runner.py` 这类主要在子进程里运行的文件数值偏低。覆盖率只作参考，不作为失败条件。

## 9. 在 GitHub 上自动运行

`.github/workflows/tests.yml`：每次推送到 main 和每个 Pull Request，在 GitHub 提供的 Ubuntu 26.04 机器上按学生的步骤装好环境（README 第 4.2 节安装 ROS 2 Lyrical，`env/setup_ros_env.sh --bashrc` 安装课程依赖，`tools/download_models.sh` 下载 SFace 模型），再运行 `bash tools/run_tests.sh` 和 `bash env/check_env.sh`。安装脚本会运行两次，确认重复运行不出错、`~/.bashrc` 里只写一份。`.github/workflows/train.yml`：每周一次（也可以在 Actions 页面手动运行），按 `env/setup_conda.sh` 创建训练环境（同样运行两次），再运行 `bash env/check_env.sh train` 和 `bash tools/run_tests.sh train`。

结果在仓库页面的 Actions 标签里。自动重跑过或没有跑完的测试组会作为警告显示在运行结果的页面上（测试通过时也会显示），`hci_ws/log/run_tests/` 下的完整输出和节点日志作为附件保存，失败时下载下来看。

公开仓库 60 天没有新的提交时，GitHub 会自动停用每周的定时运行：学期开始前到 Actions 页面重新启用（见 [MAINTAINING.md](MAINTAINING.md)）。

## 10. 失败了怎么办

1. 看汇总表指出的层和包，再打开 `hci_ws/log/run_tests/latest/<层>--<包>.log` 看完整输出；测试启动的节点日志在同目录的 `ros_logs/` 里。
2. 只重跑失败的那个文件：见第 5 节。加 `-x` 在第一个失败处停下，加 `-s` 看到 print 输出。
3. 常见原因：在激活了 conda 的终端里运行（VS Code 打开的不是仓库目录本身时也会这样），或者没有装 C++ 编译器（这两种脚本都会直接提示）；mypy 报 `Library stubs not installed for "yaml"`（`sudo apt install python3-typeshed`）；改了代码没重新 `colcon build`（新增文件时需要）；电脑很忙时系统测试超时（关掉其他程序再试）；离线时 xmllint 跳过属于正常现象。
4. 汇总里出现"第一次超时、自动重跑过的测试组"：那一组第一次卡住了，项数以重跑的结果为准。括号里是卡住的位置（最里层的调用 ← 本仓库里最近的一处），完整的调用栈在同目录的 `<层>--<包>.timeout.log`。偶尔一次不要紧；同一处反复出现，说明那里真有问题。
5. 汇总里出现"没有跑完的测试组"：pytest 进程自己崩溃了（例如某个库一导入就出错），或者重跑仍然超时。那一组的测试没有计入项数，脚本同样返回非 0。打开汇总里提到的那个日志，看开头几行和结尾的调用栈。
