# 人机交互工程 · 大作业参考代码

**目标：做一个能"看见人、理解人、回应人"的机器人。**

摄像头拍到你 → 自己训练的 YOLO 认出"这是我（学号）"还是"其他人"，并算出你在哪个方向、离多远 → 结果通过 ROS 2 话题传给显示节点和行为节点 → 机器人转向你、靠近到社交距离、停下向你问好。没有摄像头也能做：仓库自带一个轻量仿真器，机器人头上有一台虚拟相机。

本仓库是练习 2–4 和期末大作业的**参考实现**。它不是标准答案：可以直接运行，也可以读懂后改写，或者只借用其中一部分。期末只提交**一段 3–5 分钟的演示视频和一份 Word 报告**，不需要提交代码、照片或模型。

> **第一次打开这个仓库？** 先看 [`START_HERE.md`](START_HERE.md) 的「解锁地图」：它按里程碑 M0–M6 告诉你每一讲该打开哪个目录、跑哪条命令、留下什么证据，不必一次读完整个仓库。

> 课程里的脑机接口（BCI/脑电）内容只在课堂上讲，不包含在练习和大作业中，所以本仓库只有视觉这一条线。

## 目录

1. [五分钟看到效果](#1-五分钟看到效果)
2. [系统一览](#2-系统一览)
3. [仓库结构](#3-仓库结构)
4. [第一次安装](#4-第一次安装)
5. [练习 2：ROS 2 基础](#5-练习-2ros-2-基础)
6. [练习 3：训练"认出我"的 YOLO](#6-练习-3训练认出我的-yolo)
7. [练习 4：感知管线](#7-练习-4感知管线)
8. [期末大作业：让机器人回应你](#8-期末大作业让机器人回应你)
9. [话题与启动参数速查](#9-话题与启动参数速查)
10. [测试](#10-测试)
11. [常见问题](#11-常见问题)
12. [隐私与数据安全（必读）](#12-隐私与数据安全必读)
13. [许可与致谢](#13-许可与致谢)

## 1. 五分钟看到效果

装好 ROS 2 Lyrical 以后（见第 4 节），不需要摄像头，也不需要先训练模型：

```bash
cd 你的 hci-course-code 目录            # 仓库放哪都行，进到它的根目录即可
bash env/setup_ros_env.sh --bashrc && source ~/.bashrc    # 会把仓库位置记成 $HCI_ROOT（新终端自动可用）
cd hci_ws && colcon build --symlink-install && source install/setup.bash
ros2 launch hci_bringup system.launch.py
```

> 下文命令里的 **`$HCI_ROOT`** 就是你克隆仓库的根目录。它由上面的 `setup_ros_env.sh --bashrc` 写进 `~/.bashrc`，之后每个新终端都自动可用；万一某个终端里是空的（还没跑过它），`cd` 进仓库再 `export HCI_ROOT="$PWD"` 即可。放在哪个路径都行，文档不假设位置。

turtlesim 窗口里，海龟 turtle1 就是机器人，旁边的小海龟 `stranger` 标出一位"虚拟人"。显示窗口里是机器人头上那台虚拟相机看到的画面。海龟会转向这个人、靠近、停在 1 m 处，状态条上出现"你好！"。仿真里还没有自己的模型时，系统自动进入演示模式（`follow:=anyone`），跟随画面里的任何人脸；在显示窗口里按空格键可以暂停或恢复机器人。

## 2. 系统一览

```
                    ┌──────────── 机器人的位姿 /turtle1/pose ────────────┐
                    ▼                                                    │
 virtual_camera_node（仿真）或 camera_node（摄像头、视频）                 │
        │ /camera/image_raw、/camera/camera_info                          │
        ▼                                                                 │
 recognizer_node ── /hci/detections（谁、在哪个方向、多远）──┬──▶ behavior_node ── /turtle1/cmd_vel ──▶ turtlesim
 （YOLO / YuNet / YuNet+SFace）                              │    （估计 → 状态机 → 安全）      或 /cmd_vel ──▶ Gazebo 小车
        │                                                     │         │ /hci/behavior_state、/hci/greeting
        └──────────── 图像 ──────────▶ viewer_node ◀──────────┘─────────┘
                                   （画框、姓名、状态条；空格键暂停机器人）
```

用仿真时，机器人一转，虚拟相机的画面就跟着变：识别和行为节点收到的就是普通的图像，不知道自己在仿真里。换成笔记本摄像头时，只把 `virtual_camera_node` 换成 `camera_node`；换成 Gazebo 小车时，用 `robot:=` 换掉 turtlesim。识别、行为、显示三个节点都不用改。

| 环节 | 对应讲次 | 对应练习 | 代码 |
|---|---|---|---|
| 准备：Ubuntu 26.04（双系统或 WSL2） | 第 1 讲 人机交互与脑机交互导论 | 练习 1 | `env/` |
| 看见人：话题、服务、动作、图像消息 | 第 2 讲 ROS 2 通信机制 | 练习 2 | `exercises/ros_basics/` |
| 理解人：YOLO 认出本人与他人，相机模型 | 第 3–5 讲 人的信号、信号处理、深度学习与感知解码 | 练习 3 | `exercises/face_recognition/`、`hci_perception` |
| 传递：检测结果 → 自定义消息 → 显示 | 第 6 讲 ROS 2 感知系统 | 练习 4 | `hci_perception`、`hci_bringup` |
| 回应人：状态机、安全、社交距离、仿真 | 第 7 讲 机器响应与交互设计，第 8 讲 系统集成、部署与伦理 | 期末 | `hci_behavior`、`hci_sim` |

## 3. 仓库结构

```
hci-course-code/
├── README.md                 本文件
├── LICENSE                   许可证（第 13 节）
├── LICENSES/                 随仓库分发的第三方文件的许可全文（Apache-2.0）
├── docs/                     ARCHITECTURE.md（代码怎么组织、按练习的阅读顺序）
│                             TESTING.md（测试怎么分层、怎么写）· VERIFICATION.md（验证记录）
│                             MAINTAINING.md（给助教和维护者：发布新版本、每学期更新）
├── env/                      环境脚本：setup_ros_env.sh · setup_conda.sh · check_env.sh
├── tools/                    run_tests.sh（一条命令跑全部测试）· download_models.sh
├── pytest.ini                测试的公共设置
├── tests/                    仓库级检查：分层规则、代码风格、环境脚本、仓库卫生
├── exercises/               练习 2、3 的两个动手目录
│   ├── ros_basics/          练习 2：话题、服务、动作、图像，7 个小脚本 + tests/
│   └── face_recognition/    练习 3：录制 → 抽帧 → 预标注 → 检查 → 负样本 → 建数据集 → 训练 → 评估 → 导出 + tests/
└── hci_ws/src/               练习 4 与期末：ROS 2 工作空间，6 个包
    ├── hci_interfaces/       消息：Detection · DetectionArray · BehaviorState
    ├── hci_common/           地基：相机模型、参数声明、节点运行、图像转换、测试辅助
    ├── hci_perception/       感知：camera_node · recognizer_node · viewer_node，识别后端，人脸模型
    ├── hci_behavior/         行为：behavior_node（估计 → 状态机 → 安全）
    ├── hci_sim/              仿真：virtual_camera_node（虚拟人与虚拟相机）
    └── hci_bringup/          启动与配置：perception.launch.py · system.launch.py · config/
```

每个包都分两层：包名目录下是纯 Python 的算法（不依赖 ROS，单独就能测试，练习 3 也复用它们），`ros/` 子目录是节点（参数、订阅、发布、定时器）。详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)，里面还有按练习排好的阅读顺序。

## 4. 第一次安装

**前提**：Ubuntu 26.04（双系统或 WSL2），建议内存 8 GB 以上，预留 25 GB 磁盘空间。图文步骤见课程附录 A、B。

### 4.1 两个环境，一个桥梁

| | ROS 环境 | 训练环境 |
|---|---|---|
| 用在 | 练习 2、练习 4、期末 | 练习 3 |
| Python | 系统自带的 Python 3.14 | conda 环境 `hci-train`（Python 3.14） |
| 装包 | `sudo apt install`（由 `setup_ros_env.sh` 完成） | `pip install`（由 `setup_conda.sh` 完成） |
| 打开终端后 | 直接用（`~/.bashrc` 已 source ROS），**不要激活 conda** | `conda activate hci-train` |
| 检查 | `bash env/check_env.sh` | `bash env/check_env.sh train` |

两个环境之间只传一个文件：练习 3 导出的 **`best.onnx`**。ROS 节点用 apt 安装的 ONNX Runtime 加载它，不需要 PyTorch。

为什么要分开：ROS 2 的 Python 部分是 apt 装在系统 Python 上的，ROS 官方文档明确说明它不能和 conda 的包混用；而训练用的 Ultralytics 不在 apt 里，往系统 Python 里 `pip install` 又会被 Ubuntu 拒绝。详细说明见 [env/README.md](env/README.md)。

### 4.2 安装 Ubuntu 26.04 和 ROS 2 Lyrical

WSL2 用户在 Windows 的 PowerShell 中执行（双系统用户跳过这一步）：

```powershell
wsl --install -d Ubuntu-26.04
```

然后在 Ubuntu 终端中按 ROS 官方文档的步骤安装 ROS 2 Lyrical（有三处小改动，见代码下面的说明）：

```bash
sudo apt update && sudo apt install -y software-properties-common curl
sudo add-apt-repository -y universe
export ROS_APT_SOURCE_VERSION=$(curl -fsSL -o /dev/null -w '%{url_effective}' https://github.com/ros-infrastructure/ros-apt-source/releases/latest | sed 's#.*/##')
echo "ros2-apt-source $ROS_APT_SOURCE_VERSION"
curl -fL -o /tmp/ros2-apt-source.deb "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.$(. /etc/os-release && echo ${UBUNTU_CODENAME:-${VERSION_CODENAME}})_all.deb"
sudo dpkg -i /tmp/ros2-apt-source.deb
sudo apt update && sudo apt upgrade -y
sudo apt install -y ros-lyrical-desktop ros-dev-tools build-essential
```

和官方文档相比：
- 第 3 行从 GitHub"最新发布"页面的跳转地址里取版本号。官方写法要调用 GitHub 的 API，每个 IP 每小时只能调 60 次，机房里很多人同时安装时会失败。第 4 行打印出的应是一个版本号，而不是空白或 `latest`。
- 两个 `curl` 加了 `-f`：下载失败时直接报错，而不是把一个错误网页存成安装包。
- 最后一行多了 `build-essential`：它是 C++ 编译器，编译自定义消息要用，`ros-dev-tools` 里没有，新装的 Ubuntu 也没有。

在国内，先按第 4.5 节把 Ubuntu 和 ROS 的软件源换成镜像，下载会快很多。

### 4.3 ROS 环境（练习 2、4 与期末）

```bash
# 1) 放好代码：git clone 或把压缩包解压到任意位置（放在 Linux 侧主目录下最快，不要放在
#    /mnt/c 这样的 Windows 磁盘上，会很慢）。进入仓库，并把它的位置记进 HCI_ROOT——
#    这是整个流程里唯一一次需要输入路径，之后所有命令都用 $HCI_ROOT：
cd 你放代码的位置/hci-course-code        # 主目录下、~/Documents 下……放哪都行，进到仓库根即可
export HCI_ROOT="$PWD"

# 2) 用 apt 安装编译器、节点和测试要用的包、中文字体；--bashrc 把本课程几行写进 ~/.bashrc
#    （含 HCI_ROOT，之后每个新终端都自动可用），并关掉 conda 在新终端里自动进入 (base)
bash env/setup_ros_env.sh --bashrc
source ~/.bashrc

# 3) 编译 ROS 2 工作空间
cd "$HCI_ROOT/hci_ws"
colcon build --symlink-install
source install/setup.bash

# 4) 检查环境，跑一遍测试（约 7 分钟，最后打印汇总）
cd "$HCI_ROOT"
bash env/check_env.sh
bash tools/run_tests.sh
```

以后每打开一个新终端，ROS 和工作空间都会自动加载，直接就是 ROS 环境。修改了节点代码或 yaml 以后，重启节点就能生效（`--symlink-install` 的作用）；新增文件或修改消息定义时，再编译一次。

### 4.4 训练环境（练习 3 之前完成即可）

```bash
cd "$HCI_ROOT"
bash env/setup_conda.sh --mirror        # 没有 conda 时先装 Miniforge，再创建 hci-train（约 3 GB）；--mirror 使用清华镜像
# 新开一个终端（HCI_ROOT 已写进 ~/.bashrc，自动可用）：
conda activate hci-train
bash "$HCI_ROOT/env/check_env.sh" train
conda deactivate                        # 用完退出，回到 ROS 环境
```

有 NVIDIA 显卡想用 GPU 训练，把上面的 `setup_conda.sh --mirror` 换成 `setup_conda.sh --mirror --cuda`（GPU 版 PyTorch 约 7 GB；已经建好的环境再运行一次，会把 CPU 版换成 GPU 版）。

PyTorch（2.14）和 Ultralytics（8.4）锁定在测试过的版本，学期中途上游发布新版本也不影响你；脚本还会关掉 Ultralytics 默认开启的匿名使用统计。

**记住一条规则：一个终端只用一个环境。** 跑 ROS 的终端不要激活 conda；训练的终端 `conda activate hci-train`。装错了也不要紧：在 conda 里编译工作空间会被直接拦下，节点也会提示"不是系统 Python"。

### 4.5 在国内：哪些下载要换成镜像

| 下载的内容 | 默认来源 | 在国内怎么做 |
|---|---|---|
| Ubuntu 的软件包 | archive.ubuntu.com | 换成清华镜像（命令见下），安全更新仍用官方源 |
| ROS 2 的软件包 | packages.ros.org | 装好 `ros2-apt-source` 之后换成清华镜像（命令见下） |
| `ros2-apt-source` 安装包 | GitHub | 第 4.2 节的 `curl` 失败时，在浏览器里打开 github.com/ros-infrastructure/ros-apt-source/releases，下载 `ros2-apt-source_<版本>.resolute_all.deb`，复制到 Ubuntu 里再 `sudo dpkg -i` |
| 训练环境（Miniforge、conda-forge、PyPI） | 国外 | `bash env/setup_conda.sh --mirror`（清华镜像；PyTorch 官方源下载失败时自动改用阿里云镜像） |
| SFace 模型 | GitHub | `bash tools/download_models.sh --mirror`（hf-mirror.com，下载后同样校验 SHA256） |
| YOLO 预训练权重 `yolo26n.pt` | GitHub | 第一次训练时自动下载；失败时见第 11 节常见问题 |
| Open Images 他人人脸 | Google、AWS 的存储 | 多半连不上：改用 `get_openimages_faces.py --from-folder`（见 exercises/face_recognition/README.md） |
| WSL、VS Code | 微软 | 不用换 |

```bash
# Ubuntu 软件源换成清华镜像（第 4.2 节的第一次 apt update 之前执行；安全更新仍用官方源）
sudo sed -i 's#http://\([a-z]*\.\)\?archive\.ubuntu\.com/ubuntu#https://mirrors.tuna.tsinghua.edu.cn/ubuntu#' /etc/apt/sources.list.d/ubuntu.sources
# ROS 2 软件源换成清华镜像（第 4.2 节 sudo dpkg -i 之后、下一次 apt update 之前执行）
sudo sed -i --follow-symlinks 's#https\?://packages\.ros\.org/ros2/ubuntu#https://mirrors.tuna.tsinghua.edu.cn/ros2/ubuntu#' /etc/apt/sources.list.d/ros2.sources
grep URIs /etc/apt/sources.list.d/*.sources     # 确认地址已经换好
```

`sudo apt update` 报镜像里找不到 `resolute` 时，说明镜像还没同步 Ubuntu 26.04 的 ROS 包，把 ROS 的源换回官方地址再更新：`sudo sed -i --follow-symlinks 's#https://mirrors.tuna.tsinghua.edu.cn/ros2/ubuntu#http://packages.ros.org/ros2/ubuntu#' /etc/apt/sources.list.d/ros2.sources`。

### 4.6 用 VS Code 打开（可选）

1. WSL2 用户在 Windows 上安装 VS Code，再在扩展里安装"WSL"；双系统用户直接在 Ubuntu 里安装 VS Code。
2. 在 Ubuntu 终端里执行 `cd $HCI_ROOT && code .`。第一次会自动在 Ubuntu 里装好 VS Code 的服务端，窗口左下角显示"WSL: Ubuntu-26.04"就连上了。**打开的文件夹必须是 hci-course-code 本身**，不要打开它的上一层目录。
3. 用 Ctrl+` 打开的终端就是 Ubuntu 终端，ROS 和工作空间已经加载；点终端右上角的"+"再开一个。按 Ctrl+C 停止程序前，先确认终端里没有选中的文字（有选中时 Ctrl+C 是复制）。
4. 仓库自带的 `.vscode/settings.json` 已经设好：默认解释器是系统 Python（ROS 环境），VS Code 不会在新开的终端里自动激活 conda。练习 3 要用训练环境时，新开一个终端，自己执行 `conda activate hci-train`。打开的是上一层目录（例如 `~/Documents/Code`）时，这些设置不生效：VS Code 的 Python 扩展会在终端里悄悄激活 conda（提示符前面不一定有 `(base)`），编译会被拦下。这时用"文件 → 打开文件夹"重新打开 hci-course-code，关掉旧终端再新开一个。
5. turtlesim、显示窗口和 rqt 仍然是单独弹出的 Linux 窗口；暂停机器人的空格键要在显示窗口里按。

### 4.7 WSL2 里使用笔记本摄像头（可选）

WSL2 默认看不到 USB 摄像头，要用 usbipd-win 把它从 Windows 转发进来。大作业不用摄像头也能完成（仿真 `camera:=sim`，或者用手机录的视频 `camera:=video`），这一节可以等练习 3 录视频之前再做。双系统用户跳过这一节。

```powershell
# Windows 的 PowerShell：安装 usbipd-win（只需一次）
winget install --interactive --exact dorssel.usbipd-win
# 以管理员身份打开 PowerShell：找到摄像头那一行（例如 Integrated Camera）的 BUSID，下面以 2-4 为例
usbipd list
usbipd bind --busid 2-4             # 只需一次
usbipd attach --wsl --busid 2-4     # 每次重启电脑或 WSL 之后都要再执行一次
```

```bash
# Ubuntu 终端
sudo modprobe uvcvideo              # 加载摄像头驱动（每次 attach 之后执行）
ls -l /dev/video*                   # 出现 /dev/video0 等就转发成功了
sudo usermod -aG video $USER        # 允许自己使用摄像头（只需一次）
```

加入 video 组以后要重新登录才生效：在 PowerShell 里执行 `wsl --shutdown`，重新打开 Ubuntu 终端，再执行一次上面的 `usbipd attach` 和 `sudo modprobe uvcvideo`。之后 `bash env/check_env.sh` 的第 4 项会显示摄像头可用，也可以直接运行 `ros2 launch hci_bringup perception.launch.py` 看画面。

- 一个摄像头常常对应好几个 `/dev/video*`，`/dev/video0` 一般就是彩色画面。带红外人脸解锁的笔记本还有一个红外摄像头：画面是黑白的或者打不开时，换个编号试试（`source:=2` 等）。
- 转发期间 Windows 用不了这个摄像头，Windows Hello 人脸解锁也用不了（改用 PIN）。用完在 PowerShell 里执行 `usbipd detach --busid 2-4`，摄像头就回到 Windows。
- 本仓库的节点和脚本都按 MJPG 格式打开摄像头。自己写的程序如果画面发绿、只有上面一部分，见第 11 节常见问题。

## 5. 练习 2：ROS 2 基础

详见 [exercises/ros_basics/README.md](exercises/ros_basics/README.md)。在 ROS 环境里运行；每个新终端都先 `cd $HCI_ROOT/exercises/ros_basics`。

```bash
cd $HCI_ROOT/exercises/ros_basics
python3 talker.py                                 # 终端 1：发布 /chatter
python3 listener.py                               # 终端 2：订阅 /chatter
ros2 run turtlesim turtlesim_node                 # 终端 1：海龟
python3 turtle_circle.py --v 2 --w 1              # 终端 2：画半径 2 的圆（话题）
python3 turtle_spawn.py --x 2 --y 8 --name buddy  # 放一只新海龟（服务）
python3 turtle_rotate.py --theta 90               # 转到朝上，打印进度（动作）
python3 cam_pub.py --source 0                     # 摄像头 -> /camera/image_raw（WSL2 见第 4.7 节，或用 --source 视频）
python3 cam_view.py                               # 订阅并显示延迟和帧率；对比 --reliable
```

## 6. 练习 3：训练"认出我"的 YOLO

详见 [exercises/face_recognition/README.md](exercises/face_recognition/README.md)，其中有每一步的原理和常见错误。在训练环境里运行：先 `conda activate hci-train`，再 `cd $HCI_ROOT/exercises/face_recognition`。

| 步骤 | 命令（在 `exercises/face_recognition/` 下执行） | 产出 |
|---|---|---|
| 1 录制 | `python capture_sessions.py --session s1 --seconds 20`（换光照、背景录 4–6 次） | `data/videos/s*.mp4` |
| 2 抽帧 | `python extract_frames.py` | `data/self/s*/…jpg`（合计 200–400 张） |
| 3 预标注 | `python prelabel_yunet.py --images data/self --class-id 0 --largest-only` | YOLO 标签 |
| 4 检查 | `python review_labels.py --images data/self` | 删掉错误标注 |
| 5 他人人脸 | `python get_openimages_faces.py --num 300` | `data/others/…`（类别 face） |
| 6 建数据集 | `python build_dataset.py --student-id 你的学号` | `dataset/data.yaml`（按场次划分） |
| 7 训练 | `python train.py` | `runs/me/weights/best.pt` |
| 8 评估 | `python evaluate.py --model runs/me/weights/best.pt` | mAP、精确率、召回率 |
| 9 导出 | `python export_onnx.py --model runs/me/weights/best.pt` | `best.onnx`（交给 ROS 环境），以及与 .pt 的一致性和速度对比 |
| 试用 | `python predict.py --model runs/me/weights/best.onnx --source 0 --name 张三` | 实时画面 |

类别约定：**0 = `stu_<学号>`（本人），1 = `face`（他人）**。显示时 `stu_2023123456` 会变成"张三 2023123456"，`face` 显示为"他人"。改测学生证 / 标志物（Track B）时加 `build_dataset.py --other-class other`，第 1 类即 `other`，核心流程与节点完全不变（代码按类别角色工作，不假设第 1 类是人脸）。不想训练也可以用两步法（YuNet 检测 + SFace 比对，`sface_verify.py`），它的登记文件能直接交给识别节点（第 7 节）。

## 7. 练习 4：感知管线

在 ROS 环境里运行（训练完记得 `conda deactivate`，或者新开一个终端）。`perception.launch.py` 启动三个节点：相机 → 识别 → 显示。

```bash
# 先用 OpenCV 自带的 YuNet 跑通管线（还没训练好自己的模型时；YuNet 随包提供，不用写路径）。
# YuNet 只检测、不认人：每张脸都标为"他人"并默认打码，想看清画面加 blur_others:=false
ros2 launch hci_bringup perception.launch.py

# 换成练习 3 导出的 ONNX 模型，并显示你的姓名
ros2 launch hci_bringup perception.launch.py \
    model:=$HCI_ROOT/exercises/face_recognition/runs/me/weights/best.onnx id_map:="stu_2023123456=张三"

# 两步法：YuNet 检测 + SFace 比对（先 bash tools/download_models.sh，在国内加 --mirror；再用 sface_verify.py 登记）
ros2 launch hci_bringup perception.launch.py \
    gallery:=$HCI_ROOT/exercises/face_recognition/data/me_sface.npy identity:=stu_2023123456

# 没有摄像头（WSL2 见第 4.7 节）时，用手机或 Windows"相机"录一段视频代替（必须写绝对路径）
ros2 launch hci_bringup perception.launch.py camera:=video source:=$HOME/me.mp4 model:=...
```

识别节点除了"是谁"，还按相机模型算出每个人的**方位角**（弧度，左正）和**距离**（米）：方位由框中心的横坐标和焦距算出，距离由框的高度和人脸的实际高度（参数 `target_height`，默认 0.22 m）算出。摄像头节点同时发布 `/camera/camera_info`（内参）；笔记本摄像头没有标定时，内参由水平视场角 `hfov_deg` 推出。

在另一个终端观察数据是怎样流动的：

```bash
ros2 node list                       # 三个节点
ros2 topic list -t                   # 话题及类型
ros2 topic hz /hci/detections        # 检测频率（参考：CPU 上 10–15 Hz）
ros2 topic delay /hci/detections     # 从拍到画面到检测完成的延迟（靠 header 里的时间戳）
ros2 topic echo /hci/detections --once
ros2 interface show hci_interfaces/msg/Detection
ros2 param describe /hci/recognizer_node target_height   # 每个参数都有中文说明
ros2 run rqt_graph rqt_graph         # 节点-话题关系图（适合截图放进报告）
```

Lyrical 没有把 `rqt_graph`、`rqt_plot` 这些工具直接放进命令行，要用 `ros2 run <包> <程序>` 启动。

每个参数的默认值和含义见 [hci_ws/README.md](hci_ws/README.md)，参数文件在 `hci_ws/src/hci_bringup/config/`。

## 8. 期末大作业：让机器人回应你

`system.launch.py` 启动整个系统。两个参数分别选**机器人**和**图像来源**：

| `camera:=` | 图像来源 | 可以搭配的 `robot:=` |
|---|---|---|
| `sim`（默认） | 虚拟相机按 turtle1 的位姿渲染画面 | `turtlesim`（默认） |
| `webcam` | 笔记本摄像头 | `turtlesim`、`gazebo` |
| `video` | 视频文件（`source:=/绝对路径/视频.mp4`），用来复现问题 | `turtlesim`、`gazebo` |
| `robot` | 机器人自带的相机 | `gazebo`（机器人带相机时）、`turtlebot4` |

```bash
# 仿真里认出"我"：自己的模型 + 一张自己的正脸照片（只在本机读取，不会复制到任何地方）
ros2 launch hci_bringup system.launch.py \
    model:=$HCI_ROOT/exercises/face_recognition/runs/me/weights/best.onnx \
    id_map:="stu_2023123456=张三" me_image:=$HOME/me.jpg

# 笔记本摄像头 + turtlesim：你在动，海龟回应（"人在回路中"）
ros2 launch hci_bringup system.launch.py camera:=webcam model:=$HOME/.../best.onnx id_map:="stu_2023123456=张三"

# 同时录包到 ~/hci_bags（只录检测结果、状态、速度、位姿，不录原始图像）
ros2 launch hci_bringup system.launch.py record:=true
```

仿真世界在 `hci_bringup/config/sim_world.yaml`：机器人前方约 2.2 m 处站着"陌生人"（公有领域照片）和"我"（`me_image` 给的照片，没给时不出现）。可以复制一份改位置、加人、让人来回走动（`walk`、`period`），用 `world:=/绝对路径/my_world.yaml` 加载。

机器人的反应如下（参数单位都是米、弧度、秒；给人调的角度用度）：

| 你（目标）在哪里 | 状态 | 机器人的反应 |
|---|---|---|
| 画面里只有别人 | STOP | 停住，原因"只看到他人"（`stop_on_other: true`） |
| 不在画面里 | STOP 或 SEARCH | 默认停住；把 `search_turn_rate` 设为大于 0（如 0.3）时原地慢转寻找你 |
| 方位偏差超过 `align_tolerance_deg`（8°） | ALIGN | 原地转向你（人在左边就向左转，角速度为正） |
| 已对准，距离大于 `greet_distance`（1.0 m） | APPROACH | 前进，越近越慢；前进中偏差放宽到 16° 才停下来转向 |
| 到达问候距离 | GREET | 停下，发布一次"你好，张三 2023123456！"；你左右移动时原地转向，保持面对你；你退开 0.2 m 以上才重新靠近 |
| 检测结果中断超过 0.5 s，或在显示窗口按了空格键 | STOP | 看门狗或暂停停车；任何时候都不后退，离人近于 `min_distance`（0.5 m）时绝不前进；按 Ctrl+C 退出时也会先发停车指令 |

`ros2 topic echo /hci/behavior_state` 能看到当前状态、原因、目标的方位与距离、下发的速度和端到端延迟；用 `ros2 run rqt_plot rqt_plot` 画出距离曲线，适合放进报告：在窗口上方的 Topic 框里输入 `/hci/behavior_state/target_distance`，点"+"（写在命令行里的话题常常加不上）。暂停和恢复也可以用命令：`ros2 service call /hci/behavior_node/enable std_srvs/srv/SetBool "{data: false}"`。注意这只是软件暂停，真机的急停必须独立于软件。

**换成其他仿真平台**（任选，不限于课件里的 TurtleBot 4），只改启动参数：

| 平台 | 启动方式 | 说明 |
|---|---|---|
| turtlesim | `robot:=turtlesim`（默认） | 自动启动，最轻量，WSL2 也流畅 |
| Gazebo 差速小车（TurtleBot 3 仿真等） | 先启动仿真，再 `robot:=gazebo camera:=webcam`（或 `camera:=video`，这时选没有相机的 burger），或 `camera:=robot`（选带相机的 waffle） | 速度话题 `/cmd_vel`，类型自动识别（Twist 或 TwistStamped）；平台参数在 `config/robots/gazebo.yaml`。还没有自己的模型时加 `follow:=anyone`，否则小车停着不动 |
| TurtleBot 4 真机（只作课堂案例） | `robot:=turtlebot4 camera:=robot` | 真机运行 ROS 2 Jazzy，要用装了 Jazzy 的电脑连接；大作业不需要 |

Gazebo 示例（TurtleBot 3，Gazebo Jetty）：

```bash
bash $HCI_ROOT/env/setup_ros_env.sh --gazebo     # 安装一次 Gazebo（ros_gz）和 TurtleBot 3 仿真，装完新开一个终端
# 终端 1：启动仿真（burger 没有相机，waffle 带相机）
export TURTLEBOT3_MODEL=burger
ros2 launch turtlebot3_gazebo empty_world.launch.py
# 终端 2：笔记本摄像头看着你，Gazebo 里的小车回应
ros2 launch hci_bringup system.launch.py robot:=gazebo camera:=webcam model:=... id_map:="stu_2023123456=张三"
# 还没有自己的模型时：YuNet 把每张脸都当作"他人"，加 follow:=anyone 才会跟随
ros2 launch hci_bringup system.launch.py robot:=gazebo camera:=webcam follow:=anyone
```

装完 Gazebo 要新开一个终端再启动仿真：原来的终端还没有加载 Gazebo 的环境，会报 `'NoneType' object has no attribute 'lower'`。在 WSL2 里 Gazebo 每秒大约只能渲染 10 帧，比 turtlesim 慢是正常的。

想用小车自己的相机，把 burger 换成 waffle，终端 2 用 `camera:=robot`。它看到的是 Gazebo 世界里的画面：空世界里没有人，所以只能用来检查画面和接线。waffle 的相机是 1920×1080，识别节点会先缩小再检测。

机器人的相机话题与默认的 `/camera/image_raw` 不同时，加 `robot_camera_topic:=/话题名`；速度话题不是 `/cmd_vel` 时，加 `cmd_vel_topic:=/话题名`。例如不装 TurtleBot 3、改用 ros_gz 自带的差速小车演示：终端 1 执行 `ros2 launch ros_gz_sim_demos diff_drive.launch.xml`，终端 2 执行 `ros2 launch hci_bringup system.launch.py robot:=gazebo camera:=webcam cmd_vel_topic:=/model/vehicle_blue/cmd_vel`。

调参：新建一个 yaml，只写要改的参数（格式照 `hci_bringup/config/behavior.yaml`），用 `behavior_params:=/绝对路径/my_behavior.yaml` 加载。它在默认参数和平台参数之后加载，所以平台的速度和消息类型不受影响，也不必重新编译。

**演示视频建议包含这些镜头**（3–5 分钟）：
① rqt_graph（`ros2 run rqt_graph rqt_graph`）中的系统结构；
② 显示窗口里认出你（绿色框、姓名、学号）以及认出他人（橙色框，默认打码）；
③ 机器人的各个状态依次出现（STOP → ALIGN → APPROACH → GREET，可选 SEARCH），同时在终端显示 `ros2 topic echo /hci/behavior_state --field reason`；
④ `ros2 topic hz`、`ros2 topic delay` 的数值，或 `rqt_plot` 画出的距离曲线；
⑤ 你改进过的地方。

录屏工具：Windows 用 Win+G（Xbox Game Bar）或 OBS；Ubuntu 用 Ctrl+Alt+Shift+R 或 OBS。

## 9. 话题与启动参数速查

| 话题或服务 | 类型 | 发布者 → 订阅者 |
|---|---|---|
| `/camera/image_raw` | `sensor_msgs/msg/Image`（bgr8） | camera_node 或 virtual_camera_node → recognizer_node、viewer_node |
| `/camera/camera_info` | `sensor_msgs/msg/CameraInfo` | camera_node 或 virtual_camera_node → recognizer_node |
| `/camera/image_raw/compressed` | `sensor_msgs/msg/CompressedImage` | camera_node（`publish_compressed: true` 时） |
| `/hci/detections` | `hci_interfaces/msg/DetectionArray` | recognizer_node → viewer_node、behavior_node |
| `/hci/behavior_state` | `hci_interfaces/msg/BehaviorState` | behavior_node → viewer_node |
| `/hci/greeting` | `std_msgs/msg/String` | behavior_node → viewer_node |
| `/hci/overlay` | `sensor_msgs/msg/Image` | viewer_node（有人订阅时才发布）→ rqt_image_view |
| `/turtle1/cmd_vel` | `geometry_msgs/msg/Twist` | behavior_node → turtlesim |
| `/turtle1/pose` | `turtlesim_msgs/msg/Pose` | turtlesim → virtual_camera_node |
| `/hci/behavior_node/enable` | 服务 `std_srvs/srv/SetBool` | viewer_node（空格键）或 `ros2 service call` → behavior_node |

消息定义见 `hci_ws/src/hci_interfaces/msg/`：`Detection`（类别、显示名、置信度、框、方位角、距离）、`DetectionArray`（header 原样复制自图像）、`BehaviorState`（状态常量 STOP…GREET、原因、目标、速度、延迟）。

`perception.launch.py` 的启动参数：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `camera` | `webcam` | webcam（摄像头）、video（视频文件）、robot（机器人相机）或 none（不启动相机） |
| `source` | | 摄像头编号或视频文件的绝对路径 |
| `robot` | | camera:=robot 时的机器人平台：gazebo 或 turtlebot4 |
| `robot_camera_topic` | | camera:=robot 时的图像话题（留空用平台的默认话题） |
| `model` | | 练习 3 导出的 best.onnx（绝对路径）；留空用 YuNet 演示模式 |
| `gallery` | | 两步法的登记文件（.npy，绝对路径） |
| `identity` | | 两步法比对成功时的类别名，如 stu_2023123456 |
| `id_map` | | 学号与姓名，如 "stu_2023123456=张三"，多人用逗号分隔 |
| `image_reliability` | | reliable 或 best_effort：图像订阅的可靠性（留空时自动选择） |
| `show_window` | | true 或 false：是否弹窗显示 |
| `blur_others` | | true 或 false：是否给他人的脸打码 |
| `perception_params` | | 自己的参数文件（留空用 hci_bringup/config/perception.yaml） |

`system.launch.py` 的启动参数（另外接受上表除 `camera`、`robot` 以外的全部参数，原样交给感知部分）：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `robot` | `turtlesim` | turtlesim、gazebo 或 turtlebot4 |
| `camera` | `sim` | sim（虚拟相机）、webcam（摄像头）、video（视频文件）或 robot（机器人相机） |
| `follow` | | me（只跟随本人）或 anyone（任何人脸，演示用）；留空自动决定 |
| `record` | `false` | true：同时录包到 ~/hci_bags（不录原始图像） |
| `world` | | 仿真世界文件（留空用 hci_bringup/config/sim_world.yaml） |
| `me_image` | | 仿真里"我"的照片（绝对路径，只在本机读取） |
| `behavior_params` | | 自己的行为参数文件，在默认参数和平台参数之后加载（只写要改的参数） |
| `cmd_vel_topic` | | 机器人的速度话题（留空用平台的默认话题，如 /cmd_vel） |

## 10. 测试

一条命令检查环境、编译并按层运行全部测试，最后打印汇总表（有失败就返回非 0）：

```bash
bash tools/run_tests.sh            # ROS 环境：静态检查、单元、节点、系统，约 7 分钟
bash tools/run_tests.sh --quick    # 只跑单元测试，约 1 分钟
conda activate hci-train && bash tools/run_tests.sh train   # 训练环境：感知核心、练习 3、训练冒烟
```

测试怎样分层、每层测什么、怎样只跑一个文件、怎样给自己改的代码写测试，见 [docs/TESTING.md](docs/TESTING.md)。仓库推到 GitHub 后，每次推送到 main 都会在 GitHub 的 Ubuntu 26.04 机器上按学生的安装步骤自动跑一遍（`.github/workflows/`）。

## 11. 常见问题

先在下面的表里找。找不到时，在课程群里提问或者找助教，并附上：

1. `bash env/check_env.sh` 的完整输出（训练环境的问题用 `bash env/check_env.sh train`），第一行是你用的代码版本；
2. 出错的命令，以及它最后 20 行左右的输出；`run_tests.sh` 有失败时，附上 `hci_ws/log/run_tests/latest/` 里对应的 `.log` 文件；
3. 双系统还是 WSL2。

**不要发**人脸照片、视频、带人脸的截图，也不要发学号：截图前先给脸打码，日志里的 `stu_<学号>` 换成 `stu_xxx`；如果你的 Ubuntu 用户名就是学号，输出里路径中的用户名（`/home/` 后面那一段）也要换掉。

**环境相关**

| 现象 | 原因与解决 |
|---|---|
| `wsl --install -d Ubuntu-26.04` 提示找不到这个发行版 | WSL 太旧：先 `wsl --update`，再用 `wsl --list --online` 查看可安装的名字 |
| 安装 ROS 时打印的 ros2-apt-source 版本号是空白或 `latest`，或者 `curl` 报 `The requested URL returned error` | 连不上 GitHub：按第 4.5 节表格里的办法，在浏览器里下载 `ros2-apt-source_<版本>.resolute_all.deb`，复制到 Ubuntu 里再 `sudo dpkg -i` |
| `colcon build` 报 `No CMAKE_CXX_COMPILER could be found` | 没有 C++ 编译器：`sudo apt install -y build-essential`，然后在 `hci_ws` 里 `rm -rf build install log` 重新编译 |
| `colcon build` 报"检测到 conda 环境处于激活状态" | 在 conda 环境里编译了。执行 `conda deactivate`，然后 `rm -rf build install log` 重新编译 |
| VS Code 的终端里编译被拦下，说 conda 处于激活状态，可提示符前面没有 `(base)` | VS Code 打开的是 hci-course-code 的上一层目录，Python 扩展在终端里激活了 conda。按第 4.6 节重新打开 hci-course-code，再新开终端 |
| `colcon build` 先打印几行 `WARNING`，说 `AMENT_PREFIX_PATH` 或 `CMAKE_PREFIX_PATH` 里的路径不存在 | 删过 `install` 目录后，这个终端还记着旧路径，不影响编译。编译完新开一个终端（或 `source install/setup.bash`）就没有了 |
| `run_tests.sh` 的 L0 里 mypy 失败，日志里有 `Library stubs not installed for "yaml"` | 缺少类型存根：`sudo apt install python3-typeshed`（`setup_ros_env.sh` 会装）。不要照提示 `pip install types-PyYAML` |
| `run_tests.sh` 提示某一组"超过 300 秒没有结束……重跑一次" | 测试启动的 ROS 进程偶尔在退出时卡住（ROS 的通信库 Fast DDS 里的问题）。脚本已经结束它并自动重跑，重跑通过就没有问题；总是出现时，把 `hci_ws/log/run_tests/latest/` 里的 `*.timeout.log` 发给助教 |
| 节点警告"本节点由 …miniforge3… 运行，不是系统 Python"，或 `ros2` 命令报 `ModuleNotFoundError` | 这个终端激活了 conda。执行 `conda deactivate`（可能要执行两次，直到提示符前面没有括号），或者新开一个终端 |
| 每个新终端（或者 `source ~/.bashrc` 之后）都自动进入 `(base)` | 执行 `conda config --set auto_activate_base false`，再新开一个终端（`setup_ros_env.sh --bashrc` 和 `setup_conda.sh` 都会设置） |
| `check_env.sh` 提示还加载了其他版本的 ROS（例如 `/opt/ros/jazzy`） | 以前装过别的版本，`~/.bashrc` 里还在 source 它：`grep -n /opt/ros/ ~/.bashrc` 找到那一行删掉，新开终端 |
| `check_env.sh` 列出给其他 Ubuntu 版本的 ROS 软件源（`sudo apt update` 的输出里也能看到 `ros2/ubuntu noble` 这样的行） | 按旧教程或在旧系统上加的源，会混进不匹配的包。删掉列出的文件再 `sudo apt update`；列出的是 `/etc/apt/sources.list` 时只删那一行；是 `ros2.sources` 时按第 4.2 节重新安装 `ros2-apt-source` |
| 练习 3 的脚本提示"找不到 ultralytics"或"找不到 hci_perception" | 没有激活训练环境：`conda activate hci-train`；仓库换了位置时重新运行 `bash env/setup_conda.sh` |
| `pip install` 报 `externally-managed-environment` | 你在往系统 Python 里装包。ROS 环境的包用 `sudo apt install python3-xxx`；训练用的包先 `conda activate hci-train` 再装 |
| `无法导入 onnxruntime` | ROS 环境：`sudo apt install python3-onnxruntime`（`setup_ros_env.sh` 会装） |
| `.pt 模型只能在训练环境里使用` | ROS 节点只加载 ONNX：`model:=…/best.onnx`（由 `export_onnx.py` 导出） |
| 加载 best.onnx 时报 opset 或 IR 版本不支持 | 导出时改过 `--opset`。用默认值重新导出：`python export_onnx.py --model runs/me/weights/best.pt` |
| 在系统 Python 里同时导入 onnx 和 onnxruntime，进程直接崩溃 | Ubuntu 26.04 的 apt 版两者冲突（注册了同一份 protobuf 描述）。ROS 节点只用 onnxruntime，不受影响；需要 onnx 时在训练环境里用 |
| `conda: command not found` | 刚装完 Miniforge，当前终端还不认识 conda：新开一个终端，或执行 `source ~/.bashrc` |

**运行相关**

| 现象 | 原因与解决 |
|---|---|
| 摄像头打不开（WSL2），提示"没有 /dev/video0" | WSL2 要用 usbipd 把摄像头转发进来，见第 4.7 节；每次重启电脑或 WSL 后要重新 `usbipd attach`，再 `sudo modprobe uvcvideo`。仍不稳定时，改用视频文件 `camera:=video source:=/绝对路径/me.mp4`，或者直接用仿真 `camera:=sim`，**大作业完全可以不用摄像头完成** |
| 提示"没有权限使用 /dev/video0" | `sudo usermod -aG video $USER`，然后重新登录：WSL2 在 PowerShell 里执行 `wsl --shutdown`，重新打开终端，再 `usbipd attach`（第 4.7 节） |
| 摄像头画面发绿，只有上面一部分有图像（WSL2） | 摄像头用了不压缩的 YUYV 格式，经 usbipd 传不完整。本仓库的节点和脚本都设成了 MJPG；自己用 OpenCV 写的程序，打开摄像头后加一行 `cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))` |
| `usbipd attach` 时多出一行乱码 | 多半是 WSL 的提示"检测到 localhost 代理配置，但未镜像到 WSL"（Windows 开了代理），编码不对显示成乱码。与摄像头无关，转发照常进行 |
| 中文显示成方块 | `sudo apt install fonts-noto-cjk` |
| 不弹出显示窗口 | WSL2 执行 `wsl --update`（启用 WSLg）；或者 `show_window:=false`，改用 `ros2 run rqt_image_view rqt_image_view`，在下拉框里选 `/hci/overlay` |
| viewer_node 提示"3 秒内没有配对成功" | recognizer_node 没在运行，或者两个节点订阅的图像话题不一致。用 `ros2 topic list`、`ros2 topic hz` 排查 |
| 画面忽闪、两路画面交替出现 | 有两个节点在发布同一个图像话题（camera_node 会警告）。例如同时用了 `camera:=webcam` 和机器人自带的相机 |
| 识别节点收不到机器人相机的画面，或者每秒只有一两帧 | 订阅的可靠性（QoS）要和相机匹配。`camera:=robot` 时按平台自动选择：Gazebo 里 TurtleBot 3 的相机按 Reliable 发布 1920×1080 的大图像，用 Best Effort 订阅时分片一丢整帧作废，每秒只剩约 1 帧；TurtleBot 4 的相机按 Best Effort 发布，订阅端也只能用 Best Effort。换了别的机器人时，用 `ros2 topic info -v <图像话题>` 看发布端用哪种，再加 `image_reliability:=reliable` 或 `best_effort` |
| 机器人不动 | ① `ros2 topic echo /hci/behavior_state --field reason` 看原因；② 仿真没启动或速度话题不对（behavior_node 会提示"还没有节点订阅"）；③ 消息类型不匹配时在行为参数里设 `cmd_vel_type: twist` 或 `stamped`；④ 是否按了空格键暂停；⑤ 用摄像头或机器人相机、还没有自己的模型时，只会跟随本人，而 YuNet 把每张脸都当作"他人"：加 `follow:=anyone`（启动时的日志也会提示） |
| `rqt_graph: command not found` | Lyrical 没有把 rqt 的工具放进命令行：`ros2 run rqt_graph rqt_graph`，`rqt_plot` 同理 |
| rqt_plot 的窗口里没有曲线 | 在窗口上方的 Topic 框里输入话题，例如 `/hci/behavior_state/target_distance`，再点"+" |
| 启动 Gazebo 报 `'NoneType' object has no attribute 'lower'` | 刚装完 Gazebo，这个终端还没有加载它的环境（找不到 `gz` 命令）。新开一个终端再启动 |
| 仿真里认不出"我" | 照片要是清晰的正脸、脸占照片一半左右（参数 `me_target_ratio`）；你的模型要能认出这张照片：先在训练环境里、`exercises/face_recognition/` 下运行 `python predict.py --model runs/me/weights/best.onnx --source 照片所在文件夹` 试一下 |
| 训练时下载 yolo26n.pt 失败 | 在浏览器里从 Ultralytics 的 GitHub Releases 页面（github.com/ultralytics/assets/releases）下载，放到 `exercises/face_recognition/` 目录；实在下载不了，可以用 `--model yolo26n.yaml` 从零训练（需要 60 轮以上，效果会差一些） |
| Gazebo 很卡或黑屏（WSL2） | 先用 turtlesim 完成大作业；Gazebo 可以试 `export LIBGL_ALWAYS_SOFTWARE=1`（软件渲染），或者在双系统下运行 |
| 两台电脑的 ROS 2 互相干扰（同一 Wi-Fi） | 各自 `export ROS_DOMAIN_ID=<学号后两位>`；只想本机通信时，设置 `export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST` |
| `ros2 param set` 提示 read-only | 本仓库的参数只在节点启动时读取一次，所以设成了只读。改好 yaml（或命令行参数）后重启节点 |
| `run_tests.sh` 里 xmllint 显示跳过 | 它要联网下载 package.xml 的格式定义；离线时跳过，不代表代码有问题 |

## 12. 隐私与数据安全（必读）

人脸属于《个人信息保护法》中的**敏感个人信息**。本课程的做法如下：

- **只在自己的电脑上处理**：照片、视频、标注、`best.pt`/`best.onnx`、SFace 登记文件都只保存在本机的 `exercises/face_recognition/data/`、`dataset/`、`runs/`、`out/` 中；仿真用的 `me_image` 只在本机读取。`.gitignore` 已排除这些文件，测试也会检查仓库里没有个人数据。**不要上传到任何网盘、GitHub 或云端 GPU**。训练也在本机的 conda 环境里完成。
- **报告里只放截图**：期末只交视频和 Word 报告；显示节点默认给他人的脸打码（`blur_others`），报告中你自己的脸也可以打码。
- **录包不录原始图像**：`record:=true` 只录检测结果、状态、速度和位姿，保存在仓库外的 `~/hci_bags/`。
- **他人人脸**：使用 Open Images 等公开数据集（许可见下文），或者只用**明确同意**的同学的照片；不要偷拍，也不要从社交网络上抓取。
- **课程结束后删除**：`cd $HCI_ROOT && rm -rf exercises/face_recognition/data exercises/face_recognition/dataset exercises/face_recognition/runs exercises/face_recognition/out ~/hci_bags`，再删掉自己放在别处的照片和视频（例如本 README 示例里的 `~/me.jpg`、`~/me.mp4`）。
- **不愿使用人脸**：完全可以用"个人标志物"代替，例如一张自制卡片或学生证背面。流程不变，只是第 3 步改为用 X-AnyLabeling 手动标注；类别名仍用 `stu_<学号>`，并把识别节点的 `target_height` 改成卡片的实际高度。

## 13. 许可与致谢

- 本仓库：暂采用 GNU Affero General Public License v3.0（AGPL-3.0，见 [LICENSE](LICENSE)），以与课程所用的 Ultralytics YOLO（AGPL-3.0 组件；练习 3 与 `ultralytics_pt` 后端会用到）保持许可证兼容。是否、以及在何种组合或分发方式下需要整体以 AGPL 开源，取决于具体用法；**正式公开前请由项目负责人确认最终许可证与模型权重条款**。对本课而言：学生只交视频和报告、不对外分发代码，基本不受影响；若把改写后的系统对外发布或提供网络服务，通常需要同样以 AGPL-3.0 开源。
- 各包 `test/` 下的 `test_flake8.py`、`test_mypy.py`、`test_pep257.py`、`test_xmllint.py` 改自 ros2pkg 的模板（Apache-2.0，文件头保留原版权声明，许可全文见 [LICENSES/Apache-2.0.txt](LICENSES/Apache-2.0.txt)）。
- `hci_perception/models/face_detection_yunet_2023mar.onnx`：OpenCV Zoo，MIT 许可（版权声明与许可全文见同一文件夹的 `LICENSE-YuNet.txt`）；`face_recognition_sface_2021dec.onnx`（需下载，不随仓库发布）：OpenCV Zoo，Apache-2.0 许可。
- `hci_common/data/sample_face.jpg`：NASA 拍摄的宇航员 Eileen Collins 照片（经 scikit-image 收录），公有领域。
- Open Images V7：标注为 CC BY 4.0，图片为 CC BY 2.0（以各图片页面标注的许可为准）。
- Miniforge：BSD-3-Clause，软件包来自社区的 conda-forge 源。
- 平台：Ubuntu 26.04 LTS、ROS 2 Lyrical Luth、turtlesim、Gazebo Jetty（ros_gz）、TurtleBot 3 仿真；课堂案例 TurtleBot 4（ROS 2 Jazzy）。
