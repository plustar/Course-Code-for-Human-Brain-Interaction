# hci_ws：ROS 2 工作空间（练习 4 与期末）

| 包 | 类型 | 内容 |
|---|---|---|
| `hci_interfaces` | ament_cmake | 消息：`Detection`、`DetectionArray`、`BehaviorState` |
| `hci_common` | ament_python | 地基：相机模型、命名约定、参数声明、节点运行、图像转换、QoS、测试辅助 |
| `hci_perception` | ament_python | `camera_node`、`recognizer_node`、`viewer_node`；识别后端（YOLO 的 ONNX、YuNet、两步法、Ultralytics）；人脸模型 |
| `hci_behavior` | ament_python | `behavior_node`；估计、状态机、安全三步 |
| `hci_sim` | ament_python | `virtual_camera_node`：turtlesim 里的虚拟人与虚拟相机 |
| `hci_bringup` | ament_python | `perception.launch.py`、`system.launch.py`；各节点与各机器人平台的参数、仿真世界 |

包之间的依赖关系和每个包里文件的分工见 [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)。

## 编译

在 **ROS 环境**里编译和运行：系统自带的 Python，**不要激活 conda**（`conda deactivate`，或者新开一个终端）。

```bash
source /opt/ros/lyrical/setup.bash
cd $HCI_ROOT/hci_ws
colcon build --symlink-install
source install/setup.bash
```

- `--symlink-install`：Python 代码和 yaml 以符号链接的形式安装，修改后**重启节点**就能生效，不用重新编译。新增文件、修改 `setup.py` 或 `.msg` 时，再执行一次 `colcon build --symlink-install`。
- 生成的可执行文件第一行是 `#!/usr/bin/python3`，也就是系统 Python。`bash env/check_env.sh` 会检查这一点。
- **在激活了 conda 的终端里编译会被直接拦下**：`hci_interfaces/CMakeLists.txt` 发现 `CONDA_PREFIX` 后会报错并提示先 `conda deactivate`。原因是消息代码和节点必须对应系统 Python，混进 conda 的 Python 会在运行时出现各种 `ImportError`。已经在 conda 里编译过的，执行 `conda deactivate`，删除 `build install log` 后重新编译。
- 节点需要的 Python 包都来自 apt（`bash env/setup_ros_env.sh` 已安装）。ONNX Runtime 在 rosdep 里没有对应的键，所以 `package.xml` 里只写了注释。

## 运行

两个 launch 文件覆盖全部用法（命令见根目录 README 第 7、8 节）：

```bash
ros2 launch hci_bringup perception.launch.py     # 感知：相机 -> 识别 -> 显示（练习 4）
ros2 launch hci_bringup system.launch.py         # 整个系统：感知 + 行为 + 机器人（期末）
ros2 launch hci_bringup system.launch.py --show-args   # 列出全部启动参数和说明
```

也可以单独启动某个节点。节点里写的都是相对话题名（`image_raw`、`detections`、`cmd_vel`……），由 launch 放进命名空间并重映射；单独运行时自己加上同样的命名空间和重映射：

```bash
ros2 run hci_perception camera_node --ros-args -r __ns:=/camera -p source:=/绝对路径/me.mp4
ros2 run hci_perception recognizer_node --ros-args -r __ns:=/hci \
    -r image_raw:=/camera/image_raw -r camera_info:=/camera/camera_info
ros2 run hci_behavior behavior_node --ros-args -r __ns:=/hci -r cmd_vel:=/turtle1/cmd_vel \
    -p cmd_vel_type:=twist
```

## 节点与参数

参数在节点代码里只声明一次（`Params` 数据类：名称、默认值、中文说明），`ros2 param describe` 能看到说明。下面的表格由测试与代码核对，改了参数忘了改表格，`bash tools/run_tests.sh` 会报出来。参数都是**只读**的：只在节点启动时读取一次，运行中 `ros2 param set` 会明确报错；改参数请改 yaml 或命令行，然后重启节点。数值参数写整数或小数都可以（`-p fps:=30` 与 `-p fps:=30.0` 相同）。

### camera_node：摄像头或视频 → 图像与内参

发布 `image_raw`、`camera_info`（以及可选的 `image_raw/compressed`）。launch 把它放进 `/camera` 命名空间。同一话题上发现别的发布者时会警告（两路画面会交替出现）。

| 参数 | 默认值 | 说明 |
|---|---|---|
| `source` | `"0"` | 摄像头编号（0 即 /dev/video0）或视频文件的绝对路径 |
| `width` | `640` | 期望的画面宽度（像素），以摄像头实际支持的为准 |
| `height` | `480` | 期望的画面高度（像素） |
| `fps` | `30.0` | 摄像头的发布频率（Hz）；视频文件按自身帧率播放 |
| `fourcc` | `"MJPG"` | 摄像头像素格式；MJPG 数据量小，WSL2 转发更稳定；留空则不设置 |
| `loop_video` | `true` | 视频文件播完后是否从头循环 |
| `hfov_deg` | `60.0` | 摄像头的水平视场角（度），用来推出内参；笔记本摄像头多在 55–70 |
| `frame_id` | `"camera"` | 写进 header 的坐标系名 |
| `publish_compressed` | `false` | 是否同时发布 JPEG 压缩图像（Wi-Fi 传输时省带宽） |

### recognizer_node：图像 → 检测结果（谁、在哪个方向、多远）

订阅 `image_raw`（或 `image_raw/compressed`）和 `camera_info`，发布 `detections`。设计要点：
① **只处理最新一帧**：图像订阅用 KEEP_LAST、深度 1，推理比摄像头慢时旧画面被新画面覆盖，延迟不会越积越大。可靠性默认 Reliable：同一台电脑上传大图像时，Best Effort 丢掉的分片不会重传，整帧作废。订阅机器人自带的相机时按平台选择，`camera:=robot` 时由 launch 设置：TurtleBot 4 的相机用 Best Effort 发布，订阅端只能用 `best_effort`；Gazebo 里 TurtleBot 3 的相机用 Reliable 发布 1920×1080 的图像，仍用 `reliable`。
② **限频**：按"每 1/`max_rate` 秒一帧"的时间表放行，提前到达的画面直接跳过（不解码）；允许 20% 的时间抖动，摄像头帧率等于 `max_rate` 时也不会漏帧。
③ **原样复制图像 header**：显示节点靠它配对，`ros2 topic delay` 靠它测延迟。
④ **方位与距离**：按 `camera_info` 的内参用针孔模型算出；没有收到内参（或尺寸不符）时按 `hfov_deg` 近似。
⑤ **大画面先缩小**：YuNet 检测前把长边超过 640 的画面缩小，结果再换算回原图坐标（1920×1080 一帧从约 160 ms 降到约 17 ms）。

| 参数 | 默认值 | 说明 |
|---|---|---|
| `model` | `""` | 练习 3 导出的 best.onnx（绝对路径）；留空则用 YuNet 演示模式 |
| `gallery` | `""` | 两步法的登记文件（sface_verify.py enroll 生成的 .npy）；设置后改用 YuNet 检测 + SFace 比对 |
| `identity` | `""` | 两步法比对成功时使用的类别名，如 stu_2023123456 |
| `min_confidence` | `0.5` | 置信度低于它的检测结果丢掉 |
| `iou_threshold` | `0.5` | NMS 的重叠阈值：同一张脸重叠的框只留一个 |
| `imgsz` | `416` | 推理尺寸，与训练时一致；固定尺寸的 .onnx 自动使用导出时的尺寸 |
| `max_rate` | `15.0` | 推理频率上限（Hz） |
| `use_compressed` | `false` | 订阅 image_raw/compressed（JPEG），Wi-Fi 下省带宽 |
| `image_reliability` | `"reliable"` | 图像订阅的可靠性：reliable，或 best_effort（机器人的相机话题用 Best Effort 发布时） |
| `id_map` | `["stu_2023123456=张三"]` | 学号与姓名的对应，多人写多项 |
| `target_height` | `0.22` | 目标的实际高度（米）：人脸约 0.22；改测学生证时填卡片高度 |
| `hfov_deg` | `60.0` | 没有收到 camera_info 时，按这个水平视场角（度）估计内参 |

### viewer_node：给人看的反馈界面

订阅图像与检测结果（按时间戳配对），以及 `behavior_state`、`greeting`；有人订阅时发布 `overlay`。有图形界面时弹窗显示，窗口里按空格键暂停或恢复机器人（调用 `behavior_node/enable` 服务）。他人的脸默认打码。

| 参数 | 默认值 | 说明 |
|---|---|---|
| `show_window` | `true` | 有图形界面时是否弹窗显示 |
| `use_compressed` | `false` | 订阅 image_raw/compressed（JPEG） |
| `image_reliability` | `"reliable"` | 图像订阅的可靠性：reliable 或 best_effort（同识别节点） |
| `slop` | `0.2` | 图像与检测结果配对时允许的时间差（秒） |
| `blur_others` | `true` | 给他人的脸打码 |
| `status_bar` | `true` | 在画面底部显示机器人的状态与问候语 |
| `greeting_seconds` | `5.0` | 问候语在状态条上显示多久（秒） |
| `font_path` | `""` | 中文字体文件；留空自动查找 |

### behavior_node：估计 → 状态机 → 安全 → 速度

订阅 `detections`，发布 `cmd_vel`（Twist 或 TwistStamped）、`behavior_state`、`greeting`，提供服务 `~/enable`（`std_srvs/SetBool`）。退出（Ctrl+C 或 kill）前一定先发零速度。前 16 个参数是行为本身的（`hci_behavior/config.py`），后 4 个与 ROS 接线有关。各机器人平台不同的部分在 `hci_bringup/config/robots/<平台>.yaml`。

| 参数 | 默认值 | 说明 |
|---|---|---|
| `target_class` | `""` | 要找的人的类别名；留空表示任何 stu_ 开头的类别都算本人 |
| `min_confidence` | `0.5` | 置信度低于它的检测结果不予理会 |
| `confirm_window` | `5` | 防抖：看最近多少帧 |
| `confirm_min` | `3` | 防抖：其中至少多少帧看到本人才算确认 |
| `smoothing` | `0.5` | 方位与距离的指数平滑系数，0 表示不平滑 |
| `align_tolerance_deg` | `8.0` | 方位误差小于它算已对准（度）；前进中放宽到 2 倍 |
| `kp_turn` | `2.0` | 转向的比例系数：角速度 = kp_turn × 方位角 |
| `max_turn_rate` | `0.6` | 最大角速度（rad/s） |
| `max_speed` | `0.2` | 最大线速度（m/s）；接近人时研究建议约 0.2 |
| `min_speed` | `0.05` | 靠近时的最小线速度（m/s），避免停在半路 |
| `greet_distance` | `1.0` | 到达这个距离（米）就停下问候；研究建议 0.8–1.0 |
| `greet_hysteresis` | `0.2` | 问候后，人退开超过这么多（米）才重新靠近 |
| `min_distance` | `0.5` | 安全：目标比这个距离（米）还近时绝不前进 |
| `watchdog_timeout` | `0.5` | 安全：超过这么多秒没收到检测结果就停车 |
| `search_turn_rate` | `0.0` | 没看到本人时原地慢转寻找的角速度（rad/s），0 表示不找 |
| `stop_on_other` | `true` | 只看到他人时停车并说明原因 |
| `cmd_vel_type` | `"auto"` | 速度消息类型：auto（按机器人订阅的类型）、twist 或 stamped |
| `frame_id` | `"base_link"` | TwistStamped 消息的坐标系名 |
| `control_rate` | `10.0` | 控制频率（Hz） |
| `greeting_template` | `"你好，{name}！"` | 问候语模板，{name} 会换成对方的显示名 |

### virtual_camera_node：装在 turtle1 头上的虚拟相机

订阅 `pose`（turtlesim 的位姿），发布 `image_raw`、`camera_info`；启动时调用 turtlesim 的 `spawn` 服务，为每个虚拟人放一只同名小海龟作为标记。世界文件的格式见 `hci_bringup/config/sim_world.yaml`。

| 参数 | 默认值 | 说明 |
|---|---|---|
| `world` | `""` | 世界文件（yaml）的绝对路径；留空则右前方站一位陌生人 |
| `me_image` | `""` | "我"的头像：一张正脸照片（像证件照，脸占画面一半左右），只在本机读取 |
| `me_target_ratio` | `0.45` | "我"的照片里，目标（人脸 / 标志物）高度占照片高度的比例 |
| `width` | `640` | 画面宽度（像素） |
| `height` | `480` | 画面高度（像素） |
| `hfov_deg` | `60.0` | 虚拟相机的水平视场角（度） |
| `rate` | `15.0` | 发布频率（Hz） |
| `frame_id` | `"camera"` | 写进 header 的坐标系名 |
| `spawn_markers` | `true` | 是否在 turtlesim 里放小海龟标出虚拟人的位置 |
| `pose_timeout` | `1.0` | 超过这么多秒没收到机器人位姿就不再出图（秒） |
