# 练习 3：训练"认出我"的 YOLO（自查，不提交）

目标：在自己的笔记本上微调一个两类 YOLO 模型：

| 类别号 | 类别名 | 含义 | 显示为 |
|---|---|---|---|
| 0 | `stu_<学号>` | 你本人 | 张三 2023123456（绿色框） |
| 1 | `face` | 其他任何人 | 他人（橙色框） |

本练习在**训练环境**（conda 环境 `hci-train`）里完成。还没有这个环境时，先在仓库根目录运行一次 `bash env/setup_conda.sh --mirror`（见 `env/README.md`）。所有命令都在本目录下执行：

```bash
conda activate hci-train
cd $HCI_ROOT/exercises/face_recognition
```

练习 3 的最终产物是 `runs/me/weights/best.onnx`。练习 4 和期末的 ROS 节点只加载这个文件，不需要 PyTorch。回到 ROS 之前，先 `conda deactivate`，或者直接新开一个终端。

> **隐私**：本练习产生的照片、视频、标注和模型都只保存在 `data/`、`dataset/`、`runs/`、`out/` 中，不要上传到任何地方（详见仓库根目录 README 第 12 节）。

人脸检测（YuNet）、ONNX 推理、SFace 比对、画框这些部分，练习 3 和 ROS 节点用的是同一套代码（`hci_ws/src/hci_perception/hci_perception/recognition/` 与 `overlay.py`）。每个脚本的逻辑都写成了函数，`main()` 只负责解析命令行，所以 `tests/` 里能直接测试它们；需要换数据位置时，第 1–6 步的脚本都接受 `--data /别的/文件夹`；第 7、8 步的 `--data` 指的是 `data.yaml` 文件。

---

## 第 1 步　分场次录制自己的视频

```bash
python capture_sessions.py --session s1 --seconds 20
python capture_sessions.py --session s2 --seconds 20     # 换个地方、换个光照再录
...（共 4–6 个场次）
```

- **为什么要分场次**：同一段视频里相邻帧几乎一样。每个场次换一种条件（窗边/台灯/背光、不同背景、戴眼镜/不戴、不同发型或衣服），模型才能学到"这个人"而不是"这个房间"。
- 录制时慢慢转头、抬头、低头，换几种表情，偶尔离镜头远一点。
- 摄像头按 MJPG、640×480 打开，与 ROS 的 camera_node 相同（用的是同一个 `VideoSource`）。WSL2 先按根目录 README 第 4.7 节用 usbipd 把摄像头转发进来；打不开时脚本会说明原因（没有转发、没有权限，或者被别的程序占用）。
- 不想折腾摄像头，就用手机或 Windows"相机"应用录制，把文件复制到 `data/videos/`，按 `s1.mp4`、`s2.mp4`… 命名即可。

## 第 2 步　抽帧，去掉模糊帧和重复帧

```bash
python extract_frames.py                  # 默认每 12 帧取 1 帧
python extract_frames.py --every 8        # 张数不够时取得密一些
```

清晰度用"拉普拉斯方差"衡量，低于 `--blur` 的帧丢弃；与上一张几乎一样的帧（缩略图平均像素差小于 `--dup`）也丢弃。目标是所有场次合计 **200–400 张**。

## 第 3 步　用 YuNet 自动预标注

```bash
python prelabel_yunet.py --images data/self --class-id 0 --largest-only
```

OpenCV 自带的 YuNet 人脸检测器会先把框画好，并写成 YOLO 格式（`类别 cx cy w h`，均归一化到 0–1）。`--largest-only` 表示只标画面里最大的那张脸，避免把背景里偶然出现的人标成你。

## 第 4 步　人工检查

```bash
python review_labels.py --images data/self
```

按键：空格 = 通过；`x` = 删除这张（移到 `data/rejected/`）；`b` = 上一张；`q` = 退出。检查过的图片会记下来，下次只显示没检查过的（包括之后新录的场次）；想全部重新检查，删除 `data/self/.review_progress.json`。重点看：框是否贴合额头到下巴、有没有漏标、有没有把别人标成你。需要手动画框时，可以用 X-AnyLabeling（到它的 GitHub Releases 页面下载，本地运行，导出 YOLO 格式）。

## 第 5 步　准备"他人"人脸（负样本）

```bash
python get_openimages_faces.py --num 300                  # 方式 A：Open Images V7 公开图片
python get_openimages_faces.py --from-folder /路径/照片    # 方式 B：已获同意的同学照片
```

- 方式 A 从 Open Images V7 验证集中挑出带"Human face"框的图片（标注 CC BY 4.0，图片 CC BY 2.0），直接使用官方标注的框，类别记为 `face`。
- 在国内：方式 A 要从 Google 的服务器下载标注文件，多半连不上。可以改用方式 B；也可以由老师在能访问的网络里用方式 A 下载一份（`data/others/images/`），发给大家，再用方式 B 从解压出来的文件夹导入（YuNet 会自动标注）。
- 方式 B 可以分几次、从不同的文件夹导入，不会覆盖前一批；同一张照片导入两次也只留一份。
- 数量与本人照片相当即可。如果他人太少，模型容易把所有脸都认成你；如果太多，模型又会不敢认你。
- **不要**从社交网络上抓取他人照片。WIDER FACE 的许可是 CC BY-NC-ND，课程里也不使用它。

## 第 6 步　组装数据集（按场次划分）

```bash
python build_dataset.py --student-id 2023123456
python build_dataset.py --student-id 2023123456 --val-sessions s5 s6    # 自己指定验证场次
```

默认用**最后一个场次**做验证集，他人图片随机取 20% 做验证。脚本会打印训练集和验证集各有多少本人框、他人框。

> **为什么不能随机划分？** 如果随机划分，验证集里的每一张在训练集里都有"几乎一样的兄弟"，验证指标会高得不真实（数据泄漏）。按场次划分，考的是"换了光照和背景还认不认得出"。

## 第 7 步　训练

```bash
python train.py                                   # CPU：yolo26n.pt，imgsz 416，30 轮，约 20–60 分钟
python train.py --model yolo11n.pt --name me_yolo11   # 换 YOLO11 对比（结果在 runs/me_yolo11/，不覆盖 runs/me/）
python train.py --device 0 --imgsz 640 --epochs 60   # 有 NVIDIA 显卡时
```

用显卡训练，要先用 `bash env/setup_conda.sh --cuda` 装 GPU 版 PyTorch，并且 `bash env/check_env.sh train` 显示"GPU 可用"。

- 预训练权重第一次运行时会自动从 GitHub 下载。下载失败时，可以手动从 Ultralytics 的 GitHub Releases（github.com/ultralytics/assets/releases）下载 `yolo26n.pt`，放到本目录。
- 验证指标连续 10 轮没有提升就会提前停止（`--patience`）。
- 结果在 `runs/me/`：`weights/best.pt`，训练曲线 `results.png`，混淆矩阵 `confusion_matrix.png`（适合放进报告）。
- **不建议**用云端 GPU 训练：那等于把你的照片传到了网上。

## 第 8 步　评估

```bash
python evaluate.py --model runs/me/weights/best.pt
python evaluate.py --model runs/me/weights/best.pt --test-dirs data/test/dark data/test/glasses data/test/others
```

- 第一条命令输出验证集（未参与训练的场次）上的 mAP50、mAP50-95，以及每个类别的精确率 P 和召回率 R。
- `--test-dirs`：自己另外建几个文件夹（放在 `data/test/` 下，和其他个人数据一样只留在本机），放暗光、戴眼镜、侧脸，以及他人的公开照片。脚本会统计每个文件夹里"识别为本人"的比例，带框图片保存在 `runs/eval/`。
- 怎么看结果：本人文件夹里"识别为本人"的比例就是召回率，越高越好；他人文件夹里"识别为本人"的比例就是误认率，越低越好。两者是此消彼长的关系，可以调 `--conf` 观察。

## 第 9 步　导出 ONNX

```bash
python export_onnx.py --model runs/me/weights/best.pt
```

导出 `best.onnx`，然后用 ROS 识别节点里同一套代码（`hci_perception/recognition/yolo_onnx.py`）加载，与 `.pt` 对比检出框是否一致以及平均耗时（比较时用 0.25 的置信度阈值）。ONNX 模型只需要 onnxruntime（几十 MB），不需要 PyTorch（上 GB），在 CPU 上通常也更快。

默认按 opset 18 导出（`--opset 18`），保证 ROS 环境里 apt 安装的 ONNX Runtime 1.23 能加载。导出后，就可以换到 ROS 终端（不要激活 conda），用练习 4 的命令加载它。

> 输出格式：Ultralytics 默认导出的形状是 `(1, 4+类别数, 锚点数)`，需要自己做置信度过滤和 NMS，`yolo_onnx.py` 里有逐行注释。如果导出时加 `nms=False`（YOLO26 的免 NMS 头）或 `nms=True`，形状是 `(1, N, 6)`，同一套代码也能解析。

## 试用

```bash
python predict.py --model runs/me/weights/best.onnx --source 0 --name 张三        # 摄像头
python predict.py --model runs/me/weights/best.onnx --source me.mp4 --name 张三   # 视频
python predict.py --model runs/me/weights/best.onnx --source data/test/others --save out/
```

结束时会打印一共处理了多少张画面、检出本人和他人各多少次。

## 拓展：两步法人脸识别（SFace）

```bash
bash ../tools/download_models.sh                       # 第一次使用：下载 SFace 模型（约 37 MB）
python sface_verify.py enroll --images data/self/s1    # 登记：提取你的平均人脸特征 -> data/me_sface.npy
python sface_verify.py run --source 0                  # 实时比对：余弦相似度 ≥ 0.363 判为本人
```

两类 YOLO 只能在"本人"和"face"之间二选一，没有"陌生人"的概念。两步法先检测人脸，再把人脸变成 128 维特征，与登记的特征比较相似度，低于阈值就判为陌生人，所以天然能拒识从没见过的人。这是一个很好的报告对比点。`data/me_sface.npy` 属于生物识别信息，同样只能留在本机。

登记文件可以直接交给 ROS 识别节点，不用训练也能在练习 4 和期末里"认出我"：

```bash
ros2 launch hci_bringup perception.launch.py \
    gallery:=$HCI_ROOT/exercises/face_recognition/data/me_sface.npy identity:=stu_2023123456
```

## 常见问题

| 现象 | 可能原因 |
|---|---|
| 提示"找不到 ultralytics"或"找不到 torch" | 没有激活训练环境：`conda activate hci-train`；还没有这个环境就先运行 `bash env/setup_conda.sh` |
| `conda: command not found` | 刚装完 Miniforge，当前终端还不认识 conda：新开一个终端，或执行 `source ~/.bashrc` |
| `pip install` 报 `externally-managed-environment` | 当前是系统 Python，Ubuntu 不允许往里面 pip 装包。训练用的包要装进 conda 环境：先 `conda activate hci-train` |
| 验证集上很好，换个房间就不认了 | 场次太少或条件太单一；多录几个不同光照和背景的场次 |
| 总把别人认成你 | 他人样本太少，或者他人照片里的脸都很小；增加他人样本，并提高识别节点的 `min_confidence` |
| 你侧脸时认不出 | 训练集里侧脸太少；录制时多转头，检查时保留侧脸 |
| 训练很慢 | 减小 `--imgsz`（如 320）或 `--batch`；关掉其他程序；WSL2 可以在 `.wslconfig` 里多分配内存和 CPU |
| mAP 一直是 0 | 标签路径不对（`dataset/labels/...` 与图片同名），或者类别号写错了；打开 `runs/me/train_batch0.jpg` 看看框对不对 |
| 想确认这些脚本在自己的环境里能用 | `conda activate hci-train` 后在仓库根目录运行 `bash tools/run_tests.sh train`：用合成数据把第 3–9 步都跑一遍，约 1 分钟 |
