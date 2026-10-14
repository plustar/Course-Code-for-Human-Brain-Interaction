# 从这里开始 · 代码解锁地图

别被整个仓库吓到。你**不需要**一次读完 6 个包、十几个脚本和四百多个测试。这门课是一条项目线、7 个里程碑（M0–M6），**一次只解锁一块**：到了哪一讲，就只打开那一关要看的目录、跑那一关要跑的命令、留下那一关的证据。

> 完整的功能说明、参数速查和常见问题在 [`README.md`](README.md)；架构与分层规则在 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。本页只帮你决定**现在该看哪里**。

## 怎么用这张地图

- 读代码的顺序：先读 `README.md` 对应小节 → 再读**纯 Python 核心**（包名目录下）→ 最后读 **ROS 外壳**（`ros/` 子目录）。
- 看不懂的先跳过。本课的过关标准是**能跑通 + 能改参数 + 能解释**，不是读懂每一行。
- 每关结束顺手留下"证据"（截图/数据/短视频），到期末直接拼进报告（见 `README.md` 与课程规范 §5.1 的证据档案）。

## 解锁地图（M0 → M6）

| 里程碑 | 讲 | 练习 | 现在打开这些 | 跑这条命令 | 留下的证据 |
|---|---|---|---|---|---|
| **M0 环境** | L1 | 练习 1 | 先不用本仓库；装好系统 | `lsb_release -a` | 版本截图 |
| **M1 通信** | L2 | 练习 2 | `exercises/ros_basics/` | `talker.py` / `listener.py` / `turtle_circle.py` / `cam_pub.py` | rqt_graph、画圆、相机画面 |
| **M2 数据** | L3+L4 | 准备（采集/标注） | `exercises/face_recognition/`：`capture_sessions.py`→`extract_frames.py`→`prelabel_yunet.py`→`review_labels.py` | 采集与标注脚本 | 数据规模、按场次划分、`data.yaml` |
| **M3 模型** | L5 | 练习 3 | `exercises/face_recognition/`：`get_openimages_faces.py`→`build_dataset.py`→`train.py`→`evaluate.py`→`export_onnx.py` | 练习 3 全流程 | 验证指标、`best.onnx` 导出日志 |
| **M4 感知系统** | L6 | 练习 4 | `hci_ws/src/`：`hci_interfaces`→`hci_common`→`hci_perception` | `ros2 launch hci_bringup perception.launch.py` | 画面中的框、`ros2 topic delay` |
| **M5 行为闭环** | L7 | 课后 | `hci_ws/src/`：`hci_behavior`、`hci_sim` | `ros2 launch hci_bringup system.launch.py` | "转向→靠近→问候"短视频 |
| **M6 系统验收** | L8 | 期末 | `hci_bringup/` 配置、`tools/run_tests.sh` | 期末：录视频 + 写报告 | 端到端视频、系统证据页、测试表 |

> **四套编号怎么对应**：里程碑 **M0–M6** 是主轴，每个里程碑对应一讲（**L1–L8**）和一关"练习 / 准备 / 课后 / 期末"。练习编号 **1–4** 只发给"有独立代码目录或完整流程"的四关，所以既不是每讲都有、也**不等于讲号**——例如**练习 3 在第 5 讲**。两个练习目录按内容命名、不带数字（原 `ex2_ros_basics` / `ex3_face_yolo` 已改名为 `exercises/ros_basics` / `exercises/face_recognition`），正是为了不被误读成讲号。

每关的详细步骤和自检标准，见 `README.md` 对应小节（练习 2 / 3 / 4 / 期末）。想一口气把全程（装环境 → 测试 → 训练 → 闭环 → 人在回路）跑一遍，照 [`docs/RUNBOOK.md`](docs/RUNBOOK.md) 走。

## 读每个包的顺序（分层）

`hci_ws/src/` 的 6 个包，每个都分两层，**先读核心、再读外壳**：

- **包名目录**（如 `hci_perception/hci_perception/`）：不依赖 ROS 的纯 Python 核心——相机模型、识别后端、行为的"估计→状态机→安全"。练习 3 在训练环境里可以直接 `import` 复用。
- **`ros/` 子目录**（如 `hci_perception/ros/`）：节点外壳——订阅/发布、参数、定时器。把核心接到 ROS 上。

读不动整包时，只读你这一关要改的那个函数即可（`README.md` 和附录 D 指到了文件与函数）。

## 两条 Track：人脸或标志物，二选一（代码已平权）

- **Track A（本人人脸）** 与 **Track B（学生证 / 自制标志物）** 是**同等选项**。核心代码按"类别角色"工作——第 0 类是本人（`stu_<学号>`）、第 1 类是他人——**不假设第 1 类一定是人脸**，所以两条 Track 共用同一套脚本、节点和参数。
- 唯一区别：建数据集时 `build_dataset.py --other-class other`（Track A 默认 `face`），负样本自备（Track B 用其它卡片 / 背景，手工标注）。`identity` 与行为参数（`stop_on_other`、`me_target_ratio` 等）都按角色命名，不带 face 字样。
- 只有 **YuNet 预标注、SFace 两步法、`get_openimages_faces.py`** 是 Track A（人脸）专用助手；Track B 用 X-AnyLabeling 手工标注即可。两条都能拿满分。

## 两个 Python 环境：一个终端只用一个

- **训练环境**（conda `hci-train`）：只用在 **M3 / 练习 3**（训练导出 `best.onnx`）。`conda activate hci-train`。
- **ROS 环境**（系统 Python + apt）：**M1、M4、M5、M6**（练习 2、4 与期末）。`source /opt/ros/lyrical/setup.bash`，**不激活 conda**。
- 两者之间只传一个文件：`best.onnx`。混用（PATH 里有 conda）是最常见的报错来源。

## 需要帮助

- 跑不起来：`README.md` 第 11 节「常见问题」、课程**附录 G 排错大全**。
- 想知道某个节点/话题/参数：`README.md` 第 9 节速查、`docs/ARCHITECTURE.md`。
- 隐私：照片、视频、权重**只留本机**，不上传网络；期末报告只放截图（`README.md` 第 12 节）。
