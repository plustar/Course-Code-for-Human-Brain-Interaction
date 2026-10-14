# env：环境脚本

本课程用 **Ubuntu 26.04 + ROS 2 Lyrical**，分两个 Python 环境：

| | ROS 环境 | 训练环境 |
|---|---|---|
| 用在 | 练习 2、练习 4、期末 | 练习 3 |
| Python | 系统自带的 Python 3.14（`/usr/bin/python3`） | conda 环境 `hci-train`（Python 3.14） |
| 安装包的方式 | `sudo apt install` | conda 环境里的 `pip install` |
| 主要的包 | rclpy、OpenCV 4.10、ONNX Runtime、Pillow | PyTorch（CPU 版）、Ultralytics、ONNX、ONNX Runtime、OpenCV 4.x |
| 安装脚本 | `bash env/setup_ros_env.sh` | `bash env/setup_conda.sh` |
| 每次使用前 | `source /opt/ros/lyrical/setup.bash`，**不要**激活 conda | `conda activate hci-train` |
| 检查 | `bash env/check_env.sh` | `bash env/check_env.sh train` |

两个环境之间只传一个文件：练习 3 导出的 **`best.onnx`**。训练环境负责把它训练和导出出来；ROS 环境里的 `recognizer_node` 用 ONNX Runtime 加载它，不需要 PyTorch。

练习 3 还复用感知包与地基包的纯 Python 代码（YuNet、SFace、ONNX 解码、画框）：`setup_conda.sh` 在 `hci-train` 的 site-packages 里写一个 `hci_course.pth`，指向 `hci_ws/src/hci_common` 和 `hci_ws/src/hci_perception` 两个源码目录，所以训练环境不需要安装 ROS。仓库换了位置时重新运行一次 `setup_conda.sh`。

## 文件

| 文件 | 作用 |
|---|---|
| `setup_ros_env.sh` | 确认系统是 26.04、已装 ROS 2 Lyrical、没有激活 conda，然后用 apt 安装编译消息包要用的 C++ 编译器（`build-essential`），节点要用的 `python3-opencv python3-pil python3-onnxruntime python3-yaml fonts-noto-cjk`，以及测试要用的 pytest 插件、hypothesis、onnx、shellcheck、ament_mypy 和它要的类型存根（`python3-typeshed`）、rmw_test_fixture，最后实际运行一次 YuNet 人脸检测。`--gazebo` 另外安装 Gazebo（`ros-lyrical-ros-gz`）和 TurtleBot 3 仿真（装完新开一个终端再启动）；`--bashrc` 把 source ROS 和工作空间的两行写进 `~/.bashrc`，并关掉 conda 在新终端里自动进入 `(base)` |
| `setup_conda.sh` | 没有 conda 时先安装 Miniforge（装到 `~/miniforge3`）；创建环境 `hci-train`（Python 3.14），先装 CPU 版 PyTorch（2.14.x），再装 `requirements-train.txt`，关掉 Ultralytics 的匿名使用统计，写入 `hci_course.pth`，最后检查版本并运行一次 YuNet。`--mirror` 使用清华镜像（Miniforge、conda-forge、PyPI），`--cuda` 安装 GPU 版 PyTorch。可以重复运行 |
| `requirements-train.txt` | 训练环境的 pip 包：`ultralytics`（8.4.x）、`onnx`（1.23.x）、`onnxslim`（0.1.x）、`onnxruntime`（1.30.x）、`opencv-python<5`、`pillow`、`pyyaml`，以及测试用的 `pytest`、`pytest-timeout`、`pytest-cov`、`hypothesis` |
| `check_env.sh` | 一键检查。不带参数时检查 ROS 环境（系统、ROS 2、系统 Python 的依赖、摄像头、中文字体、工作空间；还会指出其他版本的 ROS、给其他 Ubuntu 版本的 ROS 软件源、缺少的编译器）；带 `train` 时检查训练环境，并显示 Ultralytics 的匿名统计是否关闭 |

```bash
cd $HCI_ROOT
bash env/setup_ros_env.sh --bashrc      # ROS 环境（先按根目录 README 第 4.2 节装好 ROS 2 Lyrical）
bash env/setup_conda.sh --mirror        # 训练环境（练习 3 之前完成即可）
bash env/check_env.sh                   # 检查 ROS 环境（不要激活 conda）
conda activate hci-train && bash env/check_env.sh train && conda deactivate
```

## 为什么这样分

**ROS 为什么不用 conda？** ROS 2 的 Python 部分（rclpy、消息代码等）是 apt 安装的，针对的就是系统自带的 Python 3.14 和 apt 版 NumPy。ROS 官方文档明确说明：apt 安装的 ROS 与 conda 安装的包混用不能正常工作，使用 ROS 时 `PATH` 里不要有 conda 的路径。所以 ROS 这边只用 apt，节点需要的 OpenCV、ONNX Runtime、Pillow 在 Ubuntu 26.04 的官方源里都有。

**训练为什么用 conda？** Ultralytics 不在 apt 里。往系统 Python 里 `pip install` 会被 Ubuntu 拒绝（`externally-managed-environment`），强行安装又可能覆盖 ROS 依赖的包。放进一个独立的 conda 环境，训练环境怎么折腾都不会影响 ROS；装坏了执行 `conda env remove -n hci-train`，再运行一次 `setup_conda.sh` 就能重来。

**为什么用 Miniforge，不用 Anaconda？** Miniforge 默认只用社区维护的 conda-forge 源，不受 Anaconda 商业服务条款的约束，下载也小。如果你已经装了 Miniconda 或 Anaconda，`setup_conda.sh` 会直接使用它，并且创建环境时只从 conda-forge 下载（`--override-channels -c conda-forge`）。

**两个环境怎样互不干扰？**

- `setup_conda.sh` 执行 `conda config --set auto_activate_base false`：新开的终端不会自动进入 conda，默认就是 ROS 环境。
- 激活 `hci-train` 时，环境自带的脚本（`etc/conda/activate.d/hci_isolate_ros.sh`）会暂时清掉 ROS 设置的 `PYTHONPATH`、`LD_LIBRARY_PATH` 和 `AMENT_PREFIX_PATH`；`conda deactivate` 时再恢复。所以即使 `~/.bashrc` 里 source 了 ROS，训练环境也不会误用 ROS 的 Python 包。
- 反过来，在激活 conda 的终端里编译 `hci_ws` 会被直接拦下（`hci_interfaces/CMakeLists.txt` 里的检查），节点启动时如果发现自己不是由系统 Python 运行的也会给出警告。

**ONNX 为什么默认 opset 18？** Ubuntu 26.04 的 apt 版 ONNX Runtime 是 1.23，训练环境里的 PyTorch 更新。用 `export_onnx.py` 的默认 `--opset 18` 导出，ROS 这边一定能加载。

**为什么锁定 `opencv-python<5`？** 不锁的话，pip 现在会装上 OpenCV 5。ROS 环境用的是 apt 的 OpenCV 4.10，训练环境锁在 4.x，两边的人脸检测接口和行为保持一致。

**为什么锁定 PyTorch、Ultralytics 和 ONNX 相关包的版本？** 学期中途上游发布新版本时，先装和后装环境的同学会用上不同的版本，训练结果和报错都可能不一样。锁在测试过的 PyTorch 2.14.x、Ultralytics 8.4.x、onnx 1.23.x、onnxslim 0.1.x、onnxruntime 1.30.x，同一版本线上的修复照样会装上。怎样升级见 [docs/MAINTAINING.md](../docs/MAINTAINING.md) 第 4 节：要改 `setup_conda.sh` 里的 `TORCH`、`requirements-train.txt` 和 `tests/test_env_scripts.py` 里对应的检查，再跑一遍两个环境的测试。

**为什么关掉 Ultralytics 的匿名统计？** Ultralytics 默认把匿名的使用统计和崩溃报告发给它的服务器。课程用不到，`setup_conda.sh` 执行 `settings.update({'sync': False})` 把它关掉；设置保存在 `~/.config/Ultralytics/settings.json`。

**为什么默认装 CPU 版 PyTorch？** 在 Linux 上直接 `pip install torch` 会下载带 CUDA 的版本（数 GB）。练习用的笔记本大多没有 NVIDIA 显卡，CPU 版只有约 200 MB。有 NVIDIA 显卡、驱动也装好了（双系统，或 WSL2 装了 Windows 版驱动）的同学，运行 `bash env/setup_conda.sh --cuda`。

**为什么不用 cv_bridge？** 为了少一个依赖，也为了让大家看清 `sensor_msgs/Image` 在内存里是怎么排列的。`hci_common/ros/image_msgs.py` 用几十行 NumPy 代码完成了 Image 与数组之间的转换，效果相同。

**为什么 ROS 环境里不能同时导入 onnx 和 onnxruntime？** Ubuntu 26.04 用 apt 安装的这两个包注册了同一份 protobuf 描述，在同一个进程里先后导入时进程会直接崩溃。ROS 节点只用 onnxruntime，不受影响；测试需要生成 ONNX 模型时，在子进程里调用 onnx（见 `hci_perception/testing.py`）。训练环境里的 pip 版没有这个问题。
