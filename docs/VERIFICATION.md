# 验证记录

第 2 版，2026-10-04 更新。本文件说明这份代码**在哪里测过、结果如何**，以及**哪些部分还要在真实的笔记本上确认**。第 1–4 节是在云端沙盒里的结果；第 5 节是在一台 WSL2 笔记本上按 README 从零安装、逐项试用的结果和据此做的修改；第 6 节是手工验收清单（[测试分层](TESTING.md#2-测试分层)里的 L5）和每一项的状态，助教或同学可以照着在 WSL2 或双系统上逐项确认。

## 1. 测试环境（云端沙盒，不是真实笔记本）

| 项目 | 版本与说明 |
|---|---|
| 系统 | Ubuntu 26.04 LTS 的根文件系统（chroot），2 核 CPU，无 GPU，无摄像头 |
| ROS 2 | Lyrical，**从源码编译**（157 个包，含 rclpy、launch_testing、turtlesim、rmw_test_fixture）。沙盒访问不了 packages.ros.org，所以没有用 apt 的二进制版本；源码编译里没有 rosbag2、Gazebo、rqt 和 RViz2 |
| ROS 环境 | 系统 Python 3.14.4，下列包全部来自 Ubuntu 26.04 官方 apt 源：numpy 2.3.5、OpenCV 4.10.0、Pillow 12.1.1、ONNX Runtime 1.23.2、onnx 1.20.0、PyYAML 6.0.3、pytest 9.0.2、pytest-timeout 2.4.0、pytest-cov 5.0.0、hypothesis 6.151.5、shellcheck 0.11.0；CMake 4.2.3 |
| 训练环境 | Miniforge（conda 26.7.2）的 `hci-train`：Python 3.14.7、PyTorch 2.14.0、Ultralytics 8.4.166、opencv-python 4.14.0、numpy 2.5.3、onnx 1.23.1、onnxslim 0.1.97、ONNX Runtime 1.30.0、pytest 9.1.1、hypothesis 6.168.3。沙盒访问不了 PyTorch 的 CPU 专用源，装的是 PyPI 上的 CUDA 版（在 CPU 上运行）。训练环境在沙盒的宿主系统上测试：conda 自带 Python 和全部依赖，与系统版本无关 |
| 图形界面 | Xvfb 虚拟显示器（`--gui` 的测试会打开 OpenCV 窗口和 turtlesim 窗口） |
| 摄像头 | 用合成的图片和视频代替 |

## 2. 自动测试

### 2.1 ROS 环境

把交付的压缩包解压到一个新目录，编译后运行 `bash tools/run_tests.sh --gui`：**473 项通过，11 项跳过，0 项失败**，用时约 5 分 10 秒。

| 层 | 通过 | 跳过 |
|---|---|---|
| L0 静态检查 | 31 | 5 |
| L1 单元 | 344 | 4 |
| L2 节点 | 76 | 0 |
| L3 系统 | 22 | 2 |

跳过的 11 项都是沙盒的条件所限，各自另外做了确认：

| 项数 | 跳过的原因 | 另外怎样确认 |
|---|---|---|
| 5 | xmllint 要从 download.ros.org 下载 package.xml 的格式定义，沙盒访问不了 | 从 GitHub 上 ROS 官方的 rep 仓库取得同一份格式定义，用 xmllint 校验 6 个 package.xml：全部有效；在 WSL2 笔记本上联网运行，这 5 项通过（第 5 节） |
| 4 | 只对 git 跟踪的文件做的仓库卫生检查（沙盒里测试的副本不是 git 仓库） | 在 git 仓库里单独运行 `tests/test_repo_hygiene.py`：10 项全部通过 |
| 1 | 录包：源码编译的 ROS 里没有 rosbag2 | 在 WSL2 笔记本上（apt 安装的 ROS 带 rosbag2）运行并通过，见第 5 节 |
| 1 | 用自己的照片和模型在仿真里认出"我"：要设置 `HCI_ME_PHOTO`、`HCI_ME_MODEL` | 用测试视频里截取的一张正脸和按练习 3 流程训练的模型运行过一次：通过（截图随后删除） |

覆盖率（`--cov`，语句覆盖，只统计测试进程里执行过的代码），合计 78%：

- 五个包的纯 Python 部分 91–100%；`ultralytics_pt.py` 53%，它只能在训练环境里运行。
- ROS 节点 90–98%。
- `hci_common/ros/runner.py` 33%、练习 2 的脚本 0%：它们主要在 `ros2 launch` 或 `python3 talker.py` 这样的子进程里运行（L3 测试按学生的用法启动它们），子进程不计入覆盖率。

### 2.2 训练环境

`conda activate hci-train && bash tools/run_tests.sh train`：**134 项通过，0 项跳过，0 项失败**，第一次运行约 1 分 20 秒（大部分是训练冒烟），再次运行约 15 秒。

- L1 单元 130 项：`hci_common`、`hci_perception` 的纯 Python 部分与练习 3 的函数。它们在 ROS 环境里也运行，两个环境测的是同一份核心代码。
- L4 训练冒烟 4 项：用合成的小数据集从网络结构（`yolo26n.yaml`，不下载权重）训练 1 轮 → 评估 → 导出 opset 18 的 ONNX，并用识别节点的代码加载、对比 → 用导出的模型预测。

### 2.3 测试能发现错误吗

在一份干净的副本上每次故意改坏一处，运行结构、文档、配置三个检查文件（共 80 项），看测试能不能报出来：

| 改坏的地方 | 失败的项数 |
|---|---|
| 删掉 `camera_node` 的一个参数（`fourcc`） | 3 |
| 把 `config/robots/turtlesim.yaml` 的 `max_speed` 写成 `max_sped` | 1 |
| 在 `hci_behavior/state_machine.py` 里导入 rclpy | 2 |
| 让 `hci_sim` 导入 `hci_perception` | 3 |
| README 参数表里的一个默认值与代码不一致 | 1 |
| 不改（对照） | 0 |

第 5 节的每一处修改也这样检查过：把修改改回去（或者改坏），对应的测试就失败。

| 改回去的修改 | 由哪个测试发现 | 失败的项数 |
|---|---|---|
| Gazebo 的相机改回 Best Effort 订阅 | `test_config.py`、`test_platform_wiring.py` | 2 |
| YuNet 不缩小大画面 | `test_yunet_sface.py` | 1 |
| 练习 3 用默认格式（YUYV）打开摄像头 | `exercises/face_recognition/tests/test_common.py` | 1 |
| 练习 2 的 `cam_pub.py` 用默认格式打开摄像头 | `exercises/ros_basics/tests/test_scripts.py` | 1 |
| 没有权限使用摄像头时不说明原因 | `test_capture.py` | 1 |
| 录包命令不写 `--topics` | `test_config.py` | 1 |
| 没有模型时不提示 `follow:=anyone` | `test_config.py` | 1 |
| 在 conda 里运行 ROS 包的测试时不给提示 | `tests/test_env_scripts.py` | 1 |
| README 里删掉第 4.7 节（代码的提示还在引用它） | `tests/test_docs.py` | 1 |

第 4 节第 11–23 条（最后一轮复查）的修改同样逐一改回去检查，36 处全部被发现：

| 改回去的修改 | 由哪个测试发现 | 失败的项数 |
|---|---|---|
| `.gitignore` 只挡小写的 `.jpg`（手机照片 `IMG_0001.JPG` 漏过）；不挡 GIF；不挡压缩包；把随仓库提供的 YuNet 模型也挡住；`.gitattributes` 不指定 LF | `tests/test_repo_hygiene.py` | 各 1 |
| `build_dataset.py` 删除不是自己生成的文件夹 | `exercises/face_recognition/tests/test_build_dataset.py` | 2 |
| `build_dataset.py` 中断以后，再运行时不认得自己生成的文件夹 | 同上 | 1 |
| 脚本可以被 source；被 sh 或 zsh source 时关掉终端；可以用 sudo 运行；安装失败时不说明下一步；`--bashrc` 每次都追加一份 | `tests/test_env_scripts.py` | 各 1 |
| `turtle_spawn.py` 名字被占用时不说明；`turtle_rotate.py` 目标被拒绝时不说明；`turtle_circle.py` 角速度为 0 时除以 0 | `exercises/ros_basics/tests/test_scripts.py` | 各 1 |
| 暂停期间进入 GREET，恢复后不再问候；不检查 `control_rate`；停车指令发不出去时不警告 | `test_behavior_node.py` | 各 1 |
| 不检查 `smoothing` 的范围 | `test_behavior_config.py` | 1 |
| 布尔参数接受任意字符串；整数参数接受小数 | `test_params.py` | 各 1 |
| 视频写不进去也报告"已保存"；读不出的图片让检查程序崩溃；从文件夹导入时覆盖已有的负样本；同一张照片可以导入两次 | 练习 3 对应的测试文件 | 各 1 |
| `source:=/dev/video0` 被当作文件路径（ROS 节点；练习 3 的脚本） | `test_capture.py`；`exercises/face_recognition/tests/test_common.py` | 1、2；1 |
| 开关参数写错不报错；`perception.launch.py` 的 `camera` 写错不报错；演示模式跟随错误的类别 | `test_config.py` | 各 1 |
| `check_env.sh` 不显示代码版本；onnxruntime 不锁版本；GitHub Actions 申请写权限；YuNet 的版权声明丢失；`setup.py` 里写了私人邮箱 | `tests/test_env_scripts.py`、`tests/test_docs.py`、`tests/test_repo_hygiene.py` | 各 1 |
| 不改（对照） | — | 0 |

## 3. 专项测量

| 项目 | 做法 | 结果 |
|---|---|---|
| 仿真闭环是否稳定 | 连续 5 次运行 `ros2 launch hci_bringup system.launch.py`（默认世界、YuNet 演示模式），记录进入 GREET 的时间、最终距离、问候次数、端到端延迟和退出码 | 启动后 5.2–7.9 s 进入 GREET；与"陌生人"的最终距离 0.976–1.008 m（目标 1.0 m）；每次只问候一次；最大延迟不超过 0.37 s；Ctrl+C 后退出码都是 0 |
| 图像话题的可靠性（QoS） | 虚拟相机以 15 帧/秒发布 640×480 的画面，同一台电脑上的订阅者（只保留最新一帧）分别用 Best Effort 和 Reliable，各统计 10 秒；另外模拟每帧 50 ms 的推理 | Best Effort 只收到 5–7 帧/秒，Reliable 收到 11–14.4 帧/秒。所以图像订阅默认用 Reliable；`camera:=robot` 时按平台选择（见 [ARCHITECTURE.md](ARCHITECTURE.md) 第 5 节） |
| Gazebo 相机的检测频率（模拟） | 按 Gazebo 里 TurtleBot 3 waffle 的相机发布：1920×1080、Reliable、10 Hz，画面里一张人脸；运行 `perception.launch.py camera:=robot robot:=gazebo`，用 `ros2 topic hz /hci/detections` 统计 20 秒 | 新的默认设置（Reliable 订阅、YuNet 先缩小）10.0 Hz，等于相机的帧率；改成 Best Effort 订阅只有 0.26 Hz；Reliable 但不缩小 4.7 Hz。与 WSL2 笔记本上的现象一致（第 5.3 节第 9 条） |
| YuNet 处理大画面的耗时 | 一张人脸，各连续检测 30 帧取平均，重复 3 次 | 1920×1080 直接检测 160–175 ms/帧；先缩到 640×360 再检测（含缩小）15–18 ms/帧，框换算回原图后与小画面的结果一致 |
| 自己训练的模型接入 ROS | 训练环境导出的 best.onnx（opset 18，输入 320×320）加一段 640×360、15 帧/秒的视频，运行 `perception.launch.py camera:=video` | 训练环境导出的模型在 apt 的 ONNX Runtime 1.23 里直接加载；检测 14.6 帧/秒（视频的每一帧），每帧推理 34–41 ms；`stu_2023123456` 显示为"张三 2023123456" |
| 测试组卡住时的处理 | 把每组的时间上限临时设成 3 秒（`HCI_TEST_GROUP_LIMIT=3 bash tools/run_tests.sh --quick`），让各组都超时 | 每个超时的组都写明卡在哪一行（或"进程退出时，测试都已跑完"），结束这一组的全部进程后重跑一次；重跑通过的组照常计数，重跑仍超时的组列为"没有跑完"，脚本返回非 0 |
| GitHub Actions 工作流 | 用 actionlint 1.7.12 检查两个工作流，包括用 shellcheck 检查每一步的命令 | 通过（actionlint 还不认识 `ubuntu-26.04` 这个机器标签，忽略了这一条）。**没有在 GitHub 上实际运行过**，见第 6 节 |

## 4. 测试中发现并已修复的问题

第 2 版在沙盒里和独立复查时发现的（真实笔记本上发现的见第 5.3 节）：

1. **Best Effort 丢帧**：图像订阅原来用 Best Effort（传感器数据的常见设置），同一台电脑上 640×480 的画面丢掉一大半，看门狗频繁停车。改为 Reliable、只保留最新一帧；订阅机器人自带的相机时由 launch 按平台设置（参数 `image_reliability`）。
2. **短暂中断后重复问候**：看门狗停车时把状态机也复位了，检测一恢复，人还在原地，机器人却又问候一遍。改为安全层只改输出、不改状态机。
3. **两个人时目标来回跳**：原来每帧选置信度最高的人，两人置信度接近时交替选中。改为已经在跟的人优先（方位最接近上一次估计的那个）。
4. **默认世界里认不出"我"**：两个虚拟人原来站在约 3.2 m 外，人脸在画面里太小，输入 320×320 的小模型认不出来。移到约 2.2 m。
5. **节点构造失败时的连锁报错**：构造函数出错后，`destroy_node()` 访问还没创建的属性，又抛出一个异常，把真正的原因盖住了。三个节点都改为先检查属性是否存在。
6. **apt 的 onnx 与 onnxruntime 不能在同一个进程里导入**：Ubuntu 26.04 的这两个包注册同一份 protobuf 描述，进程直接崩溃。节点只用 onnxruntime，不受影响；测试要临时生成小模型时改在子进程里做（`hci_perception/testing.py`），README 常见问题里也写了这一条。
7. **练习 2 的官方模板按 Ctrl+C 偶尔以 1 退出**：talker、cam_pub 这类用 rclpy 默认 Ctrl+C 处理的脚本，Ctrl+C 恰好落在执行器建立等待集的瞬间时，rclpy 抛出以 `rcl_shutdown() was called` 结尾的 `RCLError`。这是 rclpy 自身的时序问题，脚本保持官方写法；测试只放过这一种情况，并且先停掉所有进程再判断，不留后台进程；练习 2 的 README 写了这个现象。
8. **用 apt 的 pytest-cov 统计覆盖率时系统测试变慢**：Ubuntu 26.04 的 pytest-cov 5 会在测试启动的子进程里也开启统计，节点变慢，按 Ctrl+C 的时机也跟着变。改为子进程不继承覆盖率设置（`RosProcess`），有无 `--cov` 行为一致。同时发现 turtle_circle 的测试在探针还没发现脚本时就按了 Ctrl+C，偶尔收不到最后那条零速度，改为先等探针收到速度指令。
9. **在 source 过 ROS 的终端里，训练环境的测试被拦下**（独立复查发现）：按 README 用了 `--bashrc` 的电脑，每个终端都带着 ROS 的 `AMENT_PREFIX_PATH`，激活 `hci-train` 后 `run_tests.sh train` 认为 ROS 混了进来。训练环境的激活脚本改为同时清掉它（退出时恢复），测试检查激活和退出脚本的效果，GitHub Actions 的训练任务也先设置这些变量再激活环境。
10. **自己的行为参数文件把平台参数整个替换掉**（独立复查发现）：照 README 复制 `behavior.yaml` 改好、用 `behavior_params:=` 加载后，turtlesim 的速度和消息类型全部丢失，海龟慢了约 5 倍。改为自己的文件在默认参数和平台参数之后加载，只写要改的参数即可。

发布前最后一轮复查（两个独立的复查代理通读全部代码，加上静态检查工具）发现的：

11. **手机照片的大写扩展名漏过 `.gitignore`**：`IMG_0001.JPG`、`.HEIC`、`VID_0001.MOV` 不会被挡住，可能被提交到公开仓库。改为不分大小写，并补上 HEIC、WebP、GIF、MKV、3GP 等格式和压缩包（常用来打包照片）；测试按 `.gitignore` 检查一组典型的文件名，不需要仓库里真有这些文件。
12. **在 Windows 上 git clone 以后脚本无法运行**：git 的 `core.autocrlf` 会把换行改成 CRLF，bash 报 `$'\r': command not found`。新增 `.gitattributes`，一律按 LF 检出；测试检查所有文本文件。
13. **脚本的误用**：用 `sh` 运行，在数组语法处报出看不懂的错；用 `source` 运行（包括在 zsh 里），出错时会关掉整个终端窗口；用 `sudo` 运行，编译产物和设置都属于 root。现在五个脚本都先说明正确的用法。安装脚本中途失败（多半是网络问题）时，最后用中文说明下一步怎么做。
14. **ROS 官方的安装命令在机房里可能失败**：官方文档调用 GitHub 的 API 查 ros2-apt-source 的最新版本，每个 IP 每小时只能调用 60 次，很多人共用一个出口 IP 时会失败；失败时版本号为空，下一步会把一个错误网页当作安装包下载。README 改为从"最新发布"页面的跳转地址里取版本号，两个 `curl` 加 `-f`；GitHub Actions 逐行执行同样的命令。**沙盒访问不了 GitHub 的网页，这几行还没有实际运行过**，要在笔记本上确认（第 5.4 节）。
15. **改了仓库文件夹的名字以后 `--bashrc`**：原来发现已经写过就跳过，`~/.bashrc` 里留着旧路径；现在换成新路径（只保留一份），路径里有空格也能正确加载。
16. **离线时 xmllint 测试可能一直等**：Lyrical 的 ament_xmllint 下载格式定义时没有设超时，在网络不通又不报错的环境里会一直等下去。测试改为 20 秒后放弃，跳过并说明原因。
17. **`build_dataset.py --out` 写错会删掉照片**：重新生成数据集时它会先删除整个输出文件夹，`--out` 误写成 `data` 时原始照片会一起被删。现在只删除自己生成的文件夹（`data.yaml` 的第一行有标记，复制图片之前就先写下），原始照片在里面时拒绝执行；中途中断的文件夹下次照常删掉重来，没写完的 `data.yaml` 也不能拿去训练。
18. **练习 2 的三个脚本**：名字已被占用时 turtlesim 应答一个空名字，`turtle_spawn.py` 却报告成功；`turtle_rotate.py` 的目标被拒绝或没有答复时说不清原因；`turtle_circle.py` 的角速度为 0 时除以 0。都改为中文说明。
19. **暂停期间的问候会丢失**：在暂停（或看门狗停车）时进入 GREET，恢复以后机器人站在人面前却不问候。现在恢复后补上这一次。
20. **参数写错时的表现**：`smoothing: 1`、`confirm_min` 大于 `confirm_window`、`control_rate: 0` 这类值原来在运行中才出错，或者悄悄表现异常；布尔参数把拼错的单词（例如 `ture`）当作 true；整数参数接受 2.5。现在节点启动时就逐项说明哪个参数不对、默认值是多少。
21. **练习 3 与摄像头的边界情况**：`capture_sessions.py` 视频写不进去时仍报告"已保存"；`review_labels.py` 遇到读不出的图片会崩溃；`get_openimages_faces.py` 从文件夹导入时会覆盖上一次导入的负样本（现在按照片内容命名：不覆盖，同一张照片导入两次也只留一份，免得它同时进训练集和验证集）；`/dev/video0` 被当作视频文件的路径（ROS 节点和练习 3 的脚本现在用同一个函数判断）。都已修复，各有测试。
22. **退出时停车指令发不出去，没有任何提示**：现在提示"请确认机器人已经停下"。
23. **脚本的保护失效时，测试会在后台留下进程**（检查测试能否发现错误时发现）：去掉 `run_tests.sh` 的 sudo 保护后，测试真的运行了整套测试，60 秒超时后，它启动的进程还在后台运行。现在测试在单独的进程组里运行脚本，超时时一起结束，并在 PATH 的最前面放一个总是失败的 `sudo`，安装脚本即使保护失效也不会真的安装。

改完以后，又请一个没有参与修改的复查代理通读这一轮的全部改动，它指出的问题已经补进上面第 11、13、17、21 条。

这一轮还做了代码整理和发布准备，不改变用法：共用的常量只定义一处，补全类型标注，删掉没有用到的选项，包的依赖与代码实际导入的一致；`check_env.sh` 的第一行显示代码的版本，README 第 11 节写明怎样提问；新增给助教的 [MAINTAINING.md](MAINTAINING.md)（包括提交时用课程统一的 git 身份，不暴露私人邮箱）；随仓库分发的第三方文件附上许可全文；训练环境再锁定 onnx、onnxslim、onnxruntime 的小版本；GitHub Actions 只申请读取代码的权限，安装脚本各运行两次，检查重复运行不出错。

第 1 版验证时发现、在第 2 版里仍然有效的处理：

- Lyrical 删除了 `get_logger().warn()`，一律用 `.warning()`。
- 26.04 的 CMake 是 4.2，`cmake_minimum_required` 写 3.20（与 Lyrical 的 `ros2 pkg create` 模板一致），否则有弃用警告。
- apt 的 ONNX Runtime 1.23 第一次创建会话时打印约 600 行无害的 `Schema error`，创建会话时屏蔽。
- pip 默认会装 OpenCV 5，训练环境锁定 `opencv-python<5`，与 ROS 环境的 4.10 保持同一大版本；ONNX 导出固定为 opset 18，保证 apt 的 ONNX Runtime 能加载。
- 按 Ctrl+C 时要先发出零速度再退出：关闭 rclpy 默认的信号处理，由 `hci_common/ros/runner.py` 统一处理（L3 测试检查最后一条速度是零）。
- 播放视频文件按原始帧率，不加速；参数只在启动时读取，所以设成只读，避免 `ros2 param set` 显示成功却不生效；问候距离附近加迟滞，不会反复问候。

## 5. 真实笔记本上的试装（WSL2）

### 5.1 机器与做法

2026-10-04，一台 ThinkPad X1 笔记本：Windows 上的 WSL2，Ubuntu 26.04，按 README 第 4.2 节用 apt 安装 `ros-lyrical-desktop`；训练环境用电脑上原有的 Miniconda（`setup_conda.sh` 直接使用它）；用 VS Code 打开仓库。按 README 从零开始，一项一项跑通，遇到问题当场查清原因，修好以后再继续。

### 5.2 结果

| 项目 | 结果 |
|---|---|
| ROS 环境的自动测试（`run_tests.sh --gui`） | 补上 `python3-typeshed`、修好录包命令以后：**416 项通过，4 项跳过，0 项失败**（更新前的版本）。联网时 xmllint 的 5 项、apt 版 ROS 才有的录包测试都运行并通过；跳过的 4 项是仓库卫生检查（解压的副本不是 git 仓库，3 项）和"仿真里认出我"（没有设置自己的照片和模型）。这一版共有 484 项测试，笔记本上应是 **479 项通过、5 项跳过**（只对 git 仓库做的卫生检查多了一项） |
| 训练环境的自动测试（`run_tests.sh train`） | **114 项通过，0 项跳过，0 项失败**（更新前的版本；这一版是 134 项） |
| 系统测试反复运行 | 仿真闭环的系统测试连续运行 5 次，每次 9 项通过、1 项跳过（"认出我"）；此前完整运行时有一次卡在 rclpy 关闭的阶段（第 5.3 节第 4 条） |
| 仿真闭环 | turtlesim 和显示窗口都弹出（WSLg）；海龟转向"陌生人"，停在约 1.0 m 处问候；空格键暂停、恢复正常 |
| rqt | `ros2 run rqt_graph rqt_graph` 显示节点关系；`ros2 run rqt_plot rqt_plot` 加上 `/hci/behavior_state/target_distance` 后画出约 1 m 的距离曲线 |
| 笔记本摄像头（usbipd） | 转发并加入 video 组以后，`perception.launch.py` 把人脸框出、标为"他人"（YuNet 只检测、不认人） |
| Gazebo + 笔记本摄像头 | burger 加 `camera:=webcam follow:=anyone`：人左右移动时小车跟着转向 |
| Gazebo + 机器人相机 | waffle 加 `camera:=robot`：显示窗口里是小车相机的画面，接线正确；但检测只有约 1.1 Hz，查明原因并修复（第 5.3 节第 9 条），修复后的帧率在沙盒里模拟过（第 3 节），还要在笔记本上复测 |

### 5.3 发现并已修复的问题

1. **新装的 Ubuntu 26.04 上编译失败**：`ros-dev-tools` 只带 cmake 和 colcon，不带 C++ 编译器，新装的 Ubuntu 也没有，编译消息包时 CMake 报 `No CMAKE_CXX_COMPILER could be found`。沙盒和 GitHub 的测试机都自带编译器，所以自动测试发现不了。现在 `setup_ros_env.sh` 会安装 `build-essential`，README 第 4.2 节也加上了；`check_env.sh` 和 `run_tests.sh` 会先检查有没有编译器。在沙盒里拿掉编译器重现了同样的报错，确认这两处检查都能拦住。
2. **`source ~/.bashrc` 之后又回到 conda 的 `(base)`**：conda 默认让每个新终端自动激活 base，按 README 执行 `source ~/.bashrc` 时 base 又被激活，接下来的编译就在 conda 里进行。现在 `setup_ros_env.sh --bashrc` 会顺便关掉 conda 的自动激活（不加 `--bashrc` 时提示这条命令）。hci_interfaces 的 conda 保护移到了 `project()` 之前：原来放在后面，找不到编译器的报错会先出现，把这条中文提示挡住。那台电脑上还留着一个给 24.04（noble）的 ROS 软件源，`check_env.sh` 现在会列出这类源。
3. **VS Code 的终端里悄悄激活了 conda**：VS Code 打开的是仓库的上一层目录，仓库里让终端不激活 conda 的设置没有生效，Python 扩展给终端注入了 conda 的环境变量（提示符前面却没有 `(base)`），编译被拦下。现在编译保护、`check_env.sh`、`run_tests.sh`、`setup_ros_env.sh` 发现自己在 VS Code 的终端里时，都会说明"确认打开的文件夹就是 hci-course-code"；README 第 4.6 节写明了这一点。
4. **系统测试偶尔卡住不动**：L3 的一组测试在退出阶段卡住，faulthandler 的调用栈停在 Fast DDS 注销定时器（`ResourceEvent::unregister_timer`）的地方，是 rclpy 关闭时 ROS 通信库里的死锁，原因不在本仓库的代码里；这台笔记本上运行了约 9 次 L3，出现过 1 次。pytest-timeout 打断不了卡在 C++ 里的线程，所以 `run_tests.sh` 给每一组 5 分钟：超时就发 SIGABRT 记下卡住的位置（`PYTHONFAULTHANDLER` 让退出阶段卡住也能记下来），按环境变量标记结束这一组启动的所有进程，然后重跑一次，汇总里注明；README 常见问题和 TESTING.md 第 10 节有说明。
5. **mypy 缺少 PyYAML 的类型存根**：Lyrical 的 ament_mypy 对 `import yaml` 报 `Library stubs not installed for "yaml"`（mypy 对这类"曾经内置存根"的包不理会 `ignore_missing_imports`）。沙盒里碰巧已经装着 `python3-typeshed`，所以没有发现。`setup_ros_env.sh` 现在安装它。
6. **录包命令在 Lyrical 里失败**：Lyrical 的 `ros2 bag record` 要求话题写在 `--topics` 之后。沙盒没有 rosbag2，这项测试一直是跳过的；在笔记本上第一次运行就发现了。`system.launch.py` 改用 `--topics`，笔记本上的录包测试通过。
7. **Lyrical 里没有 `rqt_graph` 命令**：rqt 的工具没有放进命令行，要用 `ros2 run rqt_graph rqt_graph`；`rqt_plot` 写在命令行上的话题常常加不上，要在窗口的 Topic 框里添加。README、练习 2 的 README 和第 6 节的清单都改了写法。
8. **WSL2 里摄像头没有权限**：`/dev/video0` 属于 video 组，WSL2 没有桌面登录会话，不会像原生 Ubuntu 那样自动给当前用户授权，要把自己加入 video 组再重新登录（`wsl --shutdown`）。原来的报错只说"无法打开图像源"，现在 `camera_node` 和练习 3 的脚本会说明是没有转发（没有 `/dev/videoN`）、没有权限，还是被占用，练习 2 的 `cam_pub.py` 也提示这几种可能；`check_env.sh` 分别提示。README 新增第 4.7 节，写全了 usbipd 的步骤。
9. **Gazebo 里 waffle 的相机只有约 1 帧/秒**：在笔记本上测了三个数：相机话题本身约 9.8 Hz（WSL2 上 Gazebo 的渲染速度），用 Best Effort 订阅只收到 1.3 Hz，改用 Reliable 订阅后检测 4.9 Hz。原因有两层：ros_gz 桥接按 Reliable 发布 1920×1080 的图像，原来按"机器人相机都用 Best Effort"的惯例订阅，6 MB 一帧的分片丢一片就整帧作废；改成 Reliable 以后，YuNet 处理 1080p 一帧要约 160 ms，又成了瓶颈。现在每个平台写明自己相机的可靠性（Gazebo 用 Reliable，TurtleBot 4 用 Best Effort），launch 照此设置，命令行也可以用 `image_reliability:=` 指定；YuNet 把长边超过 640 的画面先缩小再检测。沙盒里模拟同样的相机，检测频率从 0.26 Hz 提高到 10 Hz（第 3 节）。
10. **Gazebo 小车不动**：用笔记本摄像头、还没有自己的模型时，系统默认只跟随本人，而 YuNet 把每张脸都当作"他人"，所以小车停着。这是设计如此（只有仿真里才自动进入演示模式），但没有任何提示。现在 `system.launch.py` 启动时在日志里说明原因和 `follow:=anyone`；README 的 Gazebo 示例也加上了。
11. **刚装完 Gazebo 就启动报错**：在安装 Gazebo 的同一个终端里启动，`ros_gz_sim` 找不到 `gz` 命令，报 `'NoneType' object has no attribute 'lower'`。新开终端就好了。`setup_ros_env.sh --gazebo` 装完会提示新开终端，README 也写了。
12. **练习 3 录制的画面发绿**：`capture_sessions.py` 用 OpenCV 的默认格式（YUYV）打开摄像头，经 usbipd 转发时 30 帧全部只有上面一部分有图像、下面是绿的；同样的摄像头用 MJPG 打开，30 帧都正常。ROS 的 `camera_node` 一直用 MJPG，所以练习 4 没有这个问题。练习 3 改为通过 `hci_perception` 的 `VideoSource` 打开摄像头（与 `camera_node` 相同：MJPG、640×480）；复查时发现练习 2 的 `cam_pub.py` 也是默认格式，一并改成 MJPG。
13. **在训练环境的终端里运行 ROS 包的测试**：报 `ModuleNotFoundError: No module named 'rclpy'`，看不出该怎么办。现在各 ROS 包的测试发现没有 ROS 时直接说明"先 conda deactivate，再 source hci_ws/install/setup.bash"。

另外按这次试用的体会做了两项调整：训练环境的 PyTorch（2.14.x）和 Ultralytics（8.4.x）锁定在测试过的版本，学期中途上游更新也不影响学生；关掉 Ultralytics 默认开启的匿名使用统计。

### 5.4 这次更新以后，还要在笔记本上复测的

- README 第 4.2 节取 ros2-apt-source 版本号的新写法（第 4 节第 14 条）：第 4 行打印出一个版本号，`curl -fL` 下载到一个 deb 文件。
- `bash env/check_env.sh` 的第一行显示代码的版本（`课程代码 v2.0.0`）；两个环境的自动测试分别是 479 项通过、5 项跳过和 134 项通过。
- Gazebo 的 waffle 加 `camera:=robot`：`ros2 topic hz /hci/detections` 应接近相机的帧率（这台笔记本上约 10 Hz）。
- 练习 3 的 `capture_sessions.py`、练习 2 的 `cam_pub.py`：画面不再发绿。
- 按 README 第 4.7 节的顺序重新走一遍摄像头转发，确认文字和实际操作一致。

## 6. 手工验收清单（L5）

下面这些沙盒里做不了，请在 WSL2 或双系统的笔记本上确认。按顺序做约 1 小时（不含第 7 项的训练）。"状态"一列是第 5 节那台 WSL2 笔记本上的结果；双系统（原生 Ubuntu 26.04）还没有试过。

| # | 项目 | 怎么做 | 通过的标志 | 状态 |
|---|---|---|---|---|
| 1 | 安装 Ubuntu 26.04（WSL2） | Windows PowerShell：`wsl --install -d Ubuntu-26.04`（课程附录 A） | 能进入 Ubuntu 终端 | ✓ |
| 2 | apt 安装的 ROS 2 Lyrical 与全部自动测试 | [README](../README.md) 第 4.2、4.3 节，最后 `bash tools/run_tests.sh --gui` | 0 项失败；联网时 xmllint 的 5 项不再跳过；`ros-lyrical-desktop` 自带 rosbag2，录包测试也会运行 | ✓ 416 项通过、4 项跳过（更新前的版本） |
| 3 | 窗口与工具（WSLg 或桌面） | `ros2 launch hci_bringup system.launch.py`；另开终端运行 `ros2 run rqt_graph rqt_graph`、`ros2 run rqt_plot rqt_plot`（在 Topic 框里加 `/hci/behavior_state/target_distance`） | turtlesim 和显示窗口都弹出；海龟转向"陌生人"、靠近、停在约 1 m 处，状态条出现"你好！"；在显示窗口按空格键后 `ros2 topic echo /hci/behavior_state --field reason` 显示"已暂停（~/enable）"，再按一次恢复；rqt 能显示节点关系和距离曲线 | ✓ |
| 4 | 录包 | `ros2 launch hci_bringup system.launch.py record:=true`，Ctrl+C 后 `ros2 bag info ~/hci_bags/<最新的目录>` | 有 `/hci/detections`、`/hci/behavior_state`、`/hci/greeting`、`/camera/camera_info`、`/turtle1/cmd_vel`、`/turtle1/pose`，没有图像话题 | ✓ 由第 2 项里的录包测试确认 |
| 5 | 摄像头 | 双系统直接用；WSL2 先按 README 第 4.7 节用 usbipd 转发。然后 `ros2 launch hci_bringup perception.launch.py blur_others:=false` | 窗口里自己的脸被框出（YuNet 只检测、不认人，所以标为"他人"）；`ros2 topic hz /hci/detections` 约 10–15 Hz | ✓ 框出并标为"他人" |
| 6 | 训练环境（清华镜像） | `bash env/setup_conda.sh --mirror`；新开终端 `conda activate hci-train && cd $HCI_ROOT && bash env/check_env.sh train && bash tools/run_tests.sh train` | 环境检查全部 ✓（没有 GPU 时那一项为 !）；134 项通过（没有运行过 `bash tools/download_models.sh` 时，SFace 的几项显示为跳过） | ✓ 114 项通过（更新前的版本） |
| 7 | 练习 3 全流程（真实数据） | [exercises/face_recognition/README.md](../exercises/face_recognition/README.md) 的 9 步，包括要摄像头和窗口的 `capture_sessions.py`、`review_labels.py`，以及要访问 Google 和 AWS 存储的 `get_openimages_faces.py --num 50` | `export_onnx.py` 报告 PyTorch 与 ONNX 的结果一致；`python predict.py --model runs/me/weights/best.onnx --source 0` 认出自己 | 交给助教（录制一步发现画面发绿，已修复，第 5.3 节第 12 条） |
| 8 | 在仿真里认出"我" | `cd $HCI_ROOT/hci_ws/src/hci_bringup`，然后 `HCI_ME_PHOTO=$HOME/me.jpg HCI_ME_MODEL=<best.onnx 的绝对路径> HCI_ME_ID_MAP="stu_学号=姓名" python3 -m pytest test/test_system_sim.py -k recognizes_me -v` | 测试通过；用同样的照片和模型运行 README 第 8 节的第一条命令，机器人走向"我"并说出你的名字 | 交给助教（要用第 7 项的模型） |
| 9 | 人在回路 | `ros2 launch hci_bringup system.launch.py camera:=webcam model:=<best.onnx> id_map:="stu_学号=姓名"` | 你左右移动时海龟转向你；离摄像头远于 1 m 时海龟前进（APPROACH），走近到约 1 m 时 GREET 并问候一次；离开画面后海龟停下（STOP） | 交给助教（要用第 7 项的模型） |
| 10 | Gazebo（可选） | `bash env/setup_ros_env.sh --gazebo`，**新开终端**，按 README 第 8 节启动 TurtleBot 3：先用没有相机的 burger 试 `robot:=gazebo camera:=webcam`（还没有模型时加 `follow:=anyone`），再换带相机的 waffle 试 `camera:=robot` | 小车随你的移动转向、前进，速度消息的类型被自动识别；`camera:=robot` 时识别节点收到机器人相机的画面，`ros2 topic hz /hci/detections` 接近相机的帧率（WSL2 上约 10 Hz），没有 QoS 不兼容的警告 | ✓ burger；waffle 的帧率待复测（第 5.4 节） |
| 11 | GitHub Actions | 把仓库推到 GitHub | `tests` 工作流通过；在 Actions 页面手动运行 `train` 工作流，也通过 | 未做 |
| 12 | GPU 训练（可选） | `bash env/setup_conda.sh --cuda`；`python train.py --device 0` | `check_env.sh train` 显示"GPU 可用"；训练明显快于 CPU | 未做 |
| 13 | 国内网络 | 在国内的网络里按 README 第 4.5 节换源，再做第 2、6 项，并运行 `bash tools/download_models.sh --mirror` | `sudo apt update` 不报错，ROS 包从镜像下载；训练环境装好；SFace 下载后校验通过（沙盒访问不了这些国内镜像，都没有测过） | 未做 |

## 开发历程（到首个公开版 1.0.0）

首个公开发布为 **1.0.0**。下面的 2.0.x / 2.1.x 是 1.0.0 之前的内部迭代（从未公开发布），保留作演进说明；**1.0.0 的内容就是下述 2.1.1 的最终状态，只是版本号改成面向公开的 1.0.0**。上面第 1–6 节是其中 2.0.x 的基线验证记录（沙盒 + WSL2 实装），核心代码与测试方式此后未变。

### 2.1.0 — Track B 在代码层面与 Track A 平权（target / other）

把“第 1 类一定是人脸”的假设从核心代码里去掉，Track A（本人人脸）与 Track B（学生证 / 标志物）完全平权：

- `hci_common.identity` 按角色判断（`stu_` 开头 = 本人，其余 = 他人、显示“他人”）；`DEFAULT_OTHER_CLASS='face'`，保留 `OTHERS` 别名供人脸后端使用。
- `build_dataset.py` 新增 `--other-class`（默认 `face`，Track B 用 `other`），写入 `data.yaml`。
- 行为参数按角色改名：`stop_on_other_face` → `stop_on_other`、`me_face_ratio` → `me_target_ratio`。
- YuNet / SFace / `get_openimages_faces.py` / `prelabel_yunet.py` 仍是 Track A（人脸）专用助手，保持人脸命名；Track B 用 X-AnyLabeling 手工标注。

**验证**：全量回归在 Ubuntu 26.04 + ROS 2 Lyrical 上通过（2026-10-05）——ROS 环境 473 通过 / 12 跳过，训练环境 130 通过 / 5 跳过（缺 SFace 模型），0 失败。（`test_system_sim` 的 `pause`/`record` 偶发失败卡在 `ros2 launch` 的 SIGINT 退出码上，与节点逻辑无关，重跑即过——后续由 2.1.1 的 L3 自动重跑兜住。）

### 2.1.1 — 教学稳健性与结构整理

- **L3 失败自动重跑**：`run_tests.sh` 把“超时自动重跑一次”扩展到 L3 系统测试——首次失败自动重跑一次，连续两次才算真失败（仅 L3；L0/L1/L2 确定性测试不重跑）。两个 CI 工作流都调用它，自动受益；节点关闭逻辑未改。
- **conda 守卫修复**：`hci_interfaces/CMakeLists.txt` 原来的 `if(DEFINED ENV{CONDA_PREFIX})` 会把 `conda deactivate` 后残留的空字符串误判成“conda 激活”而中断编译；改为非空判断，与 `run_tests.sh` / `check_env.sh` / `setup_ros_env.sh` 的 `[ -n ]` 一致，并加回归测试锁定。
- **练习目录改名**：`ex2_ros_basics` / `ex3_face_yolo` → `exercises/ros_basics` / `exercises/face_recognition`（去掉会被误读成讲号的数字），与参考系统 `hci_ws` 分开；仓库、8 讲及 `parts/` 镜像、`curriculum_lint.py` 路径白名单里的引用一并同步。
- **模块地图与运行手册**：`START_HERE.md` 的解锁地图补“讲↔练习↔里程碑↔目录”与四套编号对照；README 加入口指引、目录树改为 `exercises/` 子树；新增 `docs/RUNBOOK.md`（一次跑通全程）。
- **位置无关**：文档命令不再假设仓库在 `~/hci-course-code`，统一用 `$HCI_ROOT`（`setup_ros_env.sh --bashrc` 写进 `~/.bashrc`，新终端自动可用）。
- **收尾**：改名把 4 行路径顶过 99 字符行宽，已重新折行修复 flake8；屏蔽 `setup_conda.sh` 在新版 conda 上的 `auto_activate_base` 改名提示。

**验证**：2.1.1 在 Ubuntu 26.04 + ROS 2 Lyrical 上实跑（2026-10-14，Python 3.14.4）——编译、`check_env`、`check_env train`、ROS 环境 473 通过均正常，`$HCI_ROOT` 生效。实跑发现并修复 1 处 flake8 行宽后未再整跑；已在代码层面核验：全仓库无超 99 字符行、`flake8 --max-line-length=99` 干净。训练层 130 项于 2.1.0 已全绿，本轮未改训练相关代码。

> 首个公开版即以上 2.1.1 的内容（仅版本号改为 1.0.0）。推送到 GitHub 后按 `docs/MAINTAINING.md` 打 `v1.0.0` 标签。
