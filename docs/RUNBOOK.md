# 一次跑通全程（RUNBOOK）

把这套系统从**零**跑到**真人全链路**的一条线性路径：装环境 → 编译与全部自动测试 → 练习 2 → 练习 3 训练自己的模型 → 感知 → 仿真闭环 → 人在回路。按里程碑 M0–M6 排列，和 [`START_HERE.md`](../START_HERE.md) 的解锁地图一一对应。

> 本文件是"一口气跑一遍"的操作顺序；每一步的原理、参数和常见错误在各自的 README（[根 README](../README.md)、[练习 2](../exercises/ros_basics/README.md)、[练习 3](../exercises/face_recognition/README.md)）；带每项实测状态的验收清单见 [`docs/VERIFICATION.md`](VERIFICATION.md) 第 6 节（L5）。

## 两个环境、两个终端

- **ROS 环境**：系统 Python + apt 装的 ROS 2 Lyrical。用于 M1、M4、M5、M6。终端里**不要**有 `(base)`。
- **训练环境**：conda 的 `hci-train`。只用于 M3（练习 3 训练导出）。用 `conda activate hci-train`。
- 两者之间只传一个文件：练习 3 导出的 `best.onnx`。**混用（PATH 里混进 conda）是最常见的报错来源**——一个终端只用一个环境，切换时新开终端最省心。
- 下文命令里的 **`$HCI_ROOT`** = 仓库根目录。**仓库放在哪个路径都行**；M0 里设一次，`setup_ros_env.sh --bashrc` 会把它写进 `~/.bashrc`，之后每个新终端自动可用。若某个终端里 `$HCI_ROOT` 是空的（没跑过 `--bashrc`），`cd` 进仓库再 `export HCI_ROOT="$PWD"` 即可。
- 标记：🎥 需要摄像头（WSL2 先按根 README 第 4.7 节用 usbipd 转发，或用手机录 mp4 代替）；🪟 需要桌面弹窗（WSLg 或双系统）；🌐 需要联网。

---

## M0 · 装环境（每台机器一次）

```bash
# 仓库放哪都行。进到它的根目录，记下位置（整个流程唯一一次输入路径）：
cd 你克隆/解压到的位置/hci-course-code
export HCI_ROOT="$PWD"

# ROS 环境（装 ROS 依赖、C++ 编译器、类型存根；--bashrc 把 HCI_ROOT 等写进 ~/.bashrc，新终端自动有）
bash env/setup_ros_env.sh --bashrc          # 🌐
# 新开一个终端（或 source ~/.bashrc）让设置生效；之后所有命令都用 $HCI_ROOT

# SFace 模型（两步法 sface_verify 要用；国内加 --mirror）
bash "$HCI_ROOT/tools/download_models.sh"   # 🌐

# 训练环境（国内加 --mirror；有 NVIDIA 显卡加 --cuda）
bash "$HCI_ROOT/env/setup_conda.sh"          # 🌐
```

**✓ 成功标志**：`bash env/check_env.sh` 与 `bash env/check_env.sh train` 两个都全绿（没有 GPU 时 GPU 那项显示 `!`，正常）。

---

## M1–M6 · 全部自动测试（先确认一切就绪）

```bash
# ROS 终端（无 conda）：编译 + L0–L3，约 7 分钟
bash tools/run_tests.sh
bash tools/run_tests.sh --gui               # 🪟 想把需要弹窗的测试也跑上

# 训练终端：L1 核心 + L4 训练冒烟，约 1–2 分钟
conda activate hci-train
bash tools/run_tests.sh train
```

**✓ 成功标志**：ROS 环境 **473 项通过 / 0 失败**，训练环境 **130 项通过 / 0 失败**（跳过项是缺 SFace 模型、从 zip 运行、需 `--gui`、需本机照片，均为预期）。失败排查见 [`docs/TESTING.md`](TESTING.md) 第 10 节。

---

## M1 · 练习 2：ROS 2 通信

ROS 终端，`cd $HCI_ROOT/exercises/ros_basics`（新终端已自动 source ROS）。

```bash
# 发布 / 订阅
python3 talker.py                 # 终端 A
python3 listener.py               # 终端 B：收到的序号与 A 一致

# 话题控制海龟
ros2 run turtlesim turtlesim_node                 # 终端 A
python3 turtle_circle.py --v 2.0 --w 1.0          # 终端 B：画出半径 r=v/ω=2 的圆，Ctrl+C 后停

# 服务 / 动作
python3 turtle_spawn.py --x 2 --y 8 --name buddy  # 窗口里多一只海龟
python3 turtle_rotate.py --theta 90               # 海龟转到朝上，打印进度反馈

# 图像消息 + QoS
python3 cam_pub.py --source 0     # 🎥 终端 A（也可 --source /绝对路径/me.mp4）
python3 cam_view.py               # 🪟 终端 B：有画面，左上角显示延迟和帧率
```

**✓ 成功标志**：以上每条都出现 README 表里"看到什么算成功"的现象。

---

## M2+M3 · 练习 3：训练"认出我"的模型

训练终端，`conda activate hci-train && cd $HCI_ROOT/exercises/face_recognition`。

```bash
python capture_sessions.py --session s1 --seconds 20   # 🎥 换光照/背景录 4–6 个场次
python extract_frames.py                               # 抽帧，目标合计 200–400 张
python prelabel_yunet.py --images data/self --class-id 0 --largest-only
python review_labels.py --images data/self             # 🪟 人工检查标注
python get_openimages_faces.py --num 300               # 🌐 他人负样本（国内连不上改 --from-folder /路径）
python build_dataset.py --student-id 你的学号           # 按场次划分，生成 dataset/data.yaml
python train.py                                        # CPU 约 20–60 分（有 N 卡：--device 0 --imgsz 640）
python evaluate.py --model runs/me/weights/best.pt     # 打印 mAP 与每类 P/R
python export_onnx.py --model runs/me/weights/best.pt  # 产出 best.onnx，并与 .pt 对比一致性与耗时
```

**✓ 成功标志**：得到 `runs/me/weights/best.onnx`；evaluate 的本人召回率高、他人误认率低。导出后 `conda deactivate`（或新开 ROS 终端）再进入下一步。

> 不想训练也可用两步法：`python sface_verify.py` 登记本人特征（`data/me_sface.npy`），直接交给识别节点（见 M4 的 `gallery:=` 用法）。

---

## M4 · 练习 4：感知管线

ROS 终端，`cd $HCI_ROOT`。`perception.launch.py` 启动 相机 → 识别 → 显示 三个节点。

```bash
# 先用 OpenCV 自带的 YuNet 跑通（还没有自己的模型时；每张脸标"他人"并默认打码）
ros2 launch hci_bringup perception.launch.py           # 🪟

# 换成练习 3 的模型，并显示你的姓名
ros2 launch hci_bringup perception.launch.py \
    model:=$HCI_ROOT/exercises/face_recognition/runs/me/weights/best.onnx \
    id_map:="stu_你的学号=你的名字"

# 另一个终端观察数据流
ros2 topic hz /hci/detections        # 参考：CPU 上 10–15 Hz
ros2 topic delay /hci/detections     # 从拍到画面到检测完成的延迟
ros2 run rqt_graph rqt_graph         # 节点-话题关系图（适合截图进报告）
```

**✓ 成功标志**：画面里你的脸被框出、标你的名字；`/hci/detections` 稳定发布。

---

## M5 · 仿真闭环 + 仿真里认出"我"

ROS 终端。`system.launch.py` 启动 turtlesim + 虚拟相机 + 识别 + 行为 + 显示 五个节点。

```bash
# 纯仿真闭环（演示模式，不用模型）：看海龟 转向 → 靠近 → 问候
ros2 launch hci_bringup system.launch.py               # 🪟

# 仿真里认出"我"（真模型 + 一张自己的正脸照片，只在本机读取）
ros2 launch hci_bringup system.launch.py \
    model:=$HCI_ROOT/exercises/face_recognition/runs/me/weights/best.onnx \
    id_map:="stu_学号=名字" me_image:=$HOME/me.jpg

# 同时录包到 ~/hci_bags（只录检测/状态/速度/位姿，不录原始图像）
ros2 launch hci_bringup system.launch.py record:=true
```

**✓ 成功标志**：海龟走向"我"、停在约 1 m、问候一次"你好，名字"；只有陌生人时不动；按空格键暂停能停车。

---

## M6 · 人在回路（真摄像头，完整真跑通）

ROS 终端。这一步把"你自己采的数据 → 你自己训的模型 → 认出真人 → 机器人回应"整条链路真跑一遍。

```bash
# 笔记本摄像头 + turtlesim：你在动，海龟回应
ros2 launch hci_bringup system.launch.py camera:=webcam \   # 🎥
    model:=$HCI_ROOT/exercises/face_recognition/runs/me/weights/best.onnx \
    id_map:="stu_学号=名字"
```

**✓ 成功标志**：你左右移动，海龟转向你；离你远于 1 m 时前进（APPROACH），走近到约 1 m 时问候一次（GREET）；离开画面后海龟停下（STOP）。**跑通这一条 = 全程打通。**

可选 · Gazebo：

```bash
bash env/setup_ros_env.sh --gazebo     # 🌐 装完提示新开终端
# 新开终端：
ros2 launch hci_bringup system.launch.py camera:=webcam robot:=gazebo \
    model:=$HCI_ROOT/exercises/face_recognition/runs/me/weights/best.onnx \
    id_map:="stu_学号=名字"            # burger 无相机时加 follow:=anyone
```

---

## 一次跑通大约要多久

| 阶段 | 大致耗时 | 依赖 |
|---|---|---|
| M0 装环境 | 30–60 分（看网速） | 🌐 |
| 全部自动测试 | ROS ~7 分 + 训练 ~2 分 | — |
| 练习 2 | 15–20 分 | 🎥🪟 |
| 练习 3 训练 | 录制与标注 ~30 分 + CPU 训练 20–60 分 | 🎥🪟🌐 |
| 感知 + 闭环 + 人在回路 | 15–20 分 | 🎥🪟 |

不含训练，一条线走下来约 1 小时；含 CPU 训练再加 1 小时左右。时间紧时：装好环境 + 跑完自动测试 + 仿真闭环（M5 第一条，不用模型）就能确认系统本身是通的，训练与真摄像头可以之后补。
