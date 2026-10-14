# 代码是怎样组织的

这份说明写给想读懂、改写这份代码的同学。先看第 1 节的阅读顺序，按练习的进度读；第 2–5 节解释包怎么分、为什么这样分；第 6 节是第 1 版与第 2 版的名字对照。

## 1. 按练习的阅读顺序

每一步只需要读表里列出的文件。文件开头都有一段中文说明，从上到下就能读懂。

| 练习 | 先读 | 再读 | 对应测试（读测试是理解代码最快的办法） |
|---|---|---|---|
| 练习 2 | `exercises/ros_basics/` 的 7 个脚本（按文件开头的编号） | `hci_common/ros/runner.py`：节点运行的样板，Ctrl+C 时先停车再退出 | `exercises/ros_basics/tests/test_scripts.py` |
| 练习 3 | `exercises/face_recognition/` 各步脚本（README 的顺序） | `hci_perception/recognition/`：`yunet.py`、`sface.py`、`yolo_onnx.py`（练习 3 和 ROS 节点用的是同一套代码） | `exercises/face_recognition/tests/` |
| 练习 4 | `hci_common/camera_model.py`（第 3 讲的针孔模型）→ `hci_perception/ros/camera_node.py` → `recognizer_node.py` → `viewer_node.py` | `hci_perception/recognition/base.py` 与 `factory.py`（统一接口、按参数选后端）；`hci_bringup/launch/perception.launch.py` | `hci_perception/test/test_*_node.py` |
| 期末 | `hci_behavior/estimator.py` → `state_machine.py` → `safety.py` → `ros/behavior_node.py` | `hci_sim/world.py` → `renderer.py` → `ros/virtual_camera_node.py`；`hci_bringup/launch/system.launch.py` 与 `config/` | `hci_behavior/test/`、`hci_bringup/test/test_system_sim.py` |

## 2. 六个包，三层

```
            ┌──────────────────────────── hci_bringup ────────────────────────────┐
            │  launch：perception.launch.py · system.launch.py   config：参数与仿真世界 │
            └───────────┬───────────────────────┬───────────────────────┬─────────┘
                        ▼                       ▼                       ▼
            ┌──── hci_perception ───┐ ┌──── hci_behavior ────┐ ┌────── hci_sim ──────┐
            │ 感知人、理解人、反馈    │ │ 机器响应              │ │ 被作用的世界（仿真）  │
            │ camera / recognizer / │ │ estimator →          │ │ world → renderer →   │
            │ viewer，识别后端       │ │ state_machine →      │ │ virtual_camera_node  │
            │                       │ │ safety → behavior_node│ │                      │
            └─────┬───────────┬─────┘ └─────┬──────────┬─────┘ └──────────┬──────────┘
                  ▼           ▼             ▼          ▼                   ▼
            ┌ hci_interfaces（契约）┐   ┌──────────────── hci_common（地基）────────────────┐
            │ Detection             │   │ camera_model · identity · params · rate · samples │
            │ DetectionArray        │   │ ros/：params · runner · image_msgs · qos · testing │
            │ BehaviorState         │   └────────────────────────────────────────────────────┘
            └───────────────────────┘
```

| 包 | 一句话 | 主要文件 |
|---|---|---|
| `hci_interfaces` | 消息契约：节点之间传什么 | `msg/Detection.msg`、`DetectionArray.msg`、`BehaviorState.msg` |
| `hci_common` | 两个以上的包都要用的东西 | `camera_model.py`（像素 ↔ 方位角、像素高 ↔ 距离）、`identity.py`（stu_学号 与显示名）、`params.py`（参数只写一处）、`ros/runner.py`、`ros/image_msgs.py`、`ros/qos.py`、`ros/testing.py` |
| `hci_perception` | 摄像头、识别、显示 | `capture.py`、`recognition/`（每个后端一个文件）、`overlay.py`、`ros/` 下三个节点 |
| `hci_behavior` | 看到人之后做什么 | `estimator.py`、`state_machine.py`、`safety.py`、`config.py`、`ros/behavior_node.py` |
| `hci_sim` | 没有摄像头也能闭环 | `world.py`、`renderer.py`、`ros/virtual_camera_node.py` |
| `hci_bringup` | 系统怎么启动只在一个地方 | `launch/`、`config/`、`hci_bringup/options.py`（启动参数的组合规则） |

中间三个包之间没有箭头：它们只通过话题通信，可以单独替换、单独测试。`hci_sim` 只用标准消息（图像、内参、位姿），所以连 `hci_interfaces` 也不依赖。

## 3. 两层：纯 Python 与 ros/

每个包里，包名目录下是**纯 Python** 的算法：不导入 rclpy，只用标准库、NumPy、OpenCV、Pillow、PyYAML，单元测试毫秒级就能跑完。`ros/` 子目录是 **ROS 外壳**：声明参数、订阅、发布、定时器，把消息转换成纯 Python 的数据，调用算法，再把结果发出去。

这样分有三个好处：

1. **好测试**：状态机、相机模型、渲染这些核心逻辑不启动 ROS 就能测，安全规则还能用属性测试随机检查上千组输入（见 docs/TESTING.md）。
2. **好复用**：练习 3 在训练环境（conda，没有 ROS）里直接导入 `hci_perception` 的识别后端和 `hci_common` 的工具。`env/setup_conda.sh` 在 conda 环境里放一个 `hci_course.pth`，指向这两个包的源码目录，所以训练环境不需要安装 ROS。
3. **好替换**：节点的构造函数可以传入替身（`CameraNode(source=...)`、`RecognizerNode(recognizer=...)`、`VirtualCameraNode(world=...)`），测试时不必真开摄像头、真跑模型。

## 4. 结构规则（违反即测试失败）

| 规则 | 由哪个测试检查 |
|---|---|
| 1. 只有 `ros/`、launch 文件和测试可以导入 rclpy 与消息包 | `tests/test_architecture.py` |
| 2. 纯 Python 部分只用标准库、NumPy、OpenCV、Pillow、PyYAML 和下层的包；onnxruntime、ultralytics 这些重型依赖只在用到的函数里导入 | `tests/test_architecture.py` |
| 3. 上层只依赖下层，同层互不依赖（测试代码也一样）；跨包的检查放在 `hci_bringup` | `tests/test_architecture.py` |
| 4. 练习 3 只导入 `hci_common`、`hci_perception` 的纯 Python 部分 | `tests/test_architecture.py` |
| 5. 节点只写相对话题名，系统拓扑由 launch 的命名空间与重映射决定 | `tests/test_architecture.py` |
| 6. 代码导入了什么，`package.xml` 里就声明什么 | `tests/test_architecture.py` |
| 7. 每个节点的参数只在一个 `Params` 数据类里声明一次；yaml 的键、README 的参数表由测试核对 | `hci_bringup/test/test_config.py`、`tests/test_docs.py` |
| 8. 个人数据不进仓库 | `tests/test_repo_hygiene.py` |

## 5. 几个设计决定

**用物理量说话**。识别结果带方位角（弧度，左正）和距离（米），由相机内参按针孔模型算出：`bearing = atan2(cx − u, fx)`，`distance = fy × H / h ÷ cos(bearing)`，其中 `H` 是人脸的实际高度（`target_height`，默认 0.22 m），`h` 是框的像素高度。坐标约定按 REP 103：机体系 x 向前、y 向左，逆时针为正，所以人在左边时方位为正，机器人向左转（角速度为正）就能对准。行为参数因此可以直接写"停在 1.0 m""对准误差 8°"。

**相机同时发布内参**。`camera_node` 和 `virtual_camera_node` 都在 `image_raw` 旁边发布 `camera_info`（ROS 图像管线的惯例）。笔记本摄像头没有标定，内参由水平视场角 `hfov_deg` 推出；标定过的相机发布真实内参，识别节点自动使用。

**只处理最新一帧，可靠性按发布端选**。识别节点的图像订阅用 KEEP_LAST、深度 1：推理比摄像头慢时，旧画面被新画面覆盖，延迟不会越积越大。可靠性默认 Reliable：实测在同一台电脑上传 640×480 的画面时，Best Effort 丢掉的分片不会重传，15 帧/秒只收到 5–7 帧，看门狗会频繁停车；改成 Reliable 后收到 11–14 帧/秒。机器人自带的相机各有各的设置：TurtleBot 4 的 OAK-D 用 Best Effort 发布，Reliable 的订阅者匹配不上它；Gazebo 经 ros_gz 桥接的相机用 Reliable 发布 1920×1080 的图像，这时若用 Best Effort 订阅，6 MB 一帧，分片丢一片就整帧作废，在 WSL2 上实测每秒只剩约 1 帧。所以每个平台在 `hci_bringup/options.py` 里写明自己相机的可靠性，`camera:=robot` 时 launch 照此设置（参数 `image_reliability`，命令行上也可以指定；QoS 的构造见 `hci_common/ros/qos.py`）。

**大画面先缩小再检测**。YuNet 的耗时与像素数成正比：1920×1080 一帧约 160 ms，识别节点就跟不上相机。`yunet.py` 把长边超过 640 的画面先缩小，检测结果再换算回原图坐标，同样的画面约 17 ms（在测试机的 CPU 上）。下游拿到的框和关键点仍是原图坐标，方位和距离的计算不受影响。

**估计 → 决策 → 安全三步分开**。`estimator.py` 从每帧检测里挑出要找的人（多个候选时，已经在跟的人优先，不会在两人之间来回跳），做多帧确认和平滑；`state_machine.py` 决定 STOP、SEARCH、ALIGN、APPROACH、GREET，带两处迟滞（前进中对准阈值放宽到 2 倍；问候后人要退开 `greet_hysteresis` 才重新靠近）；`safety.py` 是最后一道关：暂停、看门狗、只有 APPROACH 能前进、绝不后退、近于 `min_distance` 不前进、限速。安全层只改输出、不改状态机：看门狗短暂超时后人还在原地时，不会重新问候一遍。

**仿真只做必要的一点**。`hci_sim` 不模拟物理，只回答一个问题："机器人此刻的相机看到什么"：把每个虚拟人换算到机器人坐标，按针孔模型决定画在哪一列、画多大，近的挡住远的。这样闭环在任何笔记本上都能跑，也是系统测试的底座；画面由真正的识别后端（YuNet 或你的模型）处理，测试检查过 1–4 m、±25° 内反算的距离误差不超过 10%、方位误差不超过 1°。

**换平台只改参数**。`robot:=` 选机器人（速度话题与消息类型在 `hci_bringup/options.py` 和 `config/robots/`），`camera:=` 选图像来源，两者组合；`behavior_node` 的 `cmd_vel_type: auto` 等机器人订阅了速度话题后按它的类型（Twist 或 TwistStamped）发布。速度话题与默认不同时，用 `cmd_vel_topic:=` 指定。

## 6. 第 1 版与第 2 版的名字对照

第 2 版按职责而不是算法命名，同一个概念在包、节点、消息、话题里用同一个词，参数用 SI 单位（米、弧度、秒、赫兹），只有给人调的角度用度并加 `_deg` 后缀。

| 类别 | 第 1 版 | 第 2 版 |
|---|---|---|
| 包 | hci_vision | `hci_perception`（另新增 `hci_common`、`hci_sim`、`hci_bringup`） |
| 节点 | yolo_node、display_node、response_node | `recognizer_node`、`viewer_node`、`behavior_node`（另新增 `virtual_camera_node`） |
| 启动 | vision.launch.py、bringup.launch.py | `perception.launch.py`、`system.launch.py`（`robot:=` 与 `camera:=` 组合） |
| 话题 | /hci/state（字符串）、/hci/annotated_image、/hci/debug_image | `/hci/behavior_state`（BehaviorState 消息）、`/hci/overlay`；新增 `/camera/camera_info` |
| 参数 | image_topic、detections_topic、cmd_vel_topic（节点参数） | 删除，改用 launch 的重映射（system.launch.py 另有启动参数 `cmd_vel_topic`） |
| 参数 | conf_threshold、model_path、yunet_model_path | `min_confidence`、`model`（YuNet 随包提供，不用写路径） |
| 参数 | target_box_ratio 0.35、align_tolerance 0.15 | `greet_distance` 1.0（米）、`align_tolerance_deg` 8（度） |
| 参数 | max_linear、min_linear、max_angular、search_angular、kp_angular | `max_speed`、`min_speed`、`max_turn_rate`、`search_turn_rate`、`kp_turn` |
| 模块 | detectors.py、labels.py、controller.py | `recognition/`（每个后端一个文件）、`identity.py` + `overlay.py`、`estimator.py` + `state_machine.py` + `safety.py` |
| 目录 | 仓库根目录的 models/、VERIFICATION.md | `hci_perception/models/`、`docs/VERIFICATION.md` |
