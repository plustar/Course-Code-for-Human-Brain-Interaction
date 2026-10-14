# models：预训练人脸模型（来自 OpenCV Zoo）

| 文件 | 用途 | 大小 | 许可 | 使用位置 |
|---|---|---|---|---|
| `face_detection_yunet_2023mar.onnx` | YuNet 人脸检测（框 + 5 个关键点） | 约 230 KB，**随仓库提供** | MIT（版权声明与许可全文见 `LICENSE-YuNet.txt`） | 识别节点的演示模式（没有给 `model` 时）、练习 3 预标注、两步法的检测部分 |
| `face_recognition_sface_2021dec.onnx` | SFace 人脸特征（128 维） | 约 37 MB，**需要下载** | Apache-2.0 | 两步法（识别节点的 `gallery` 参数）、练习 3 拓展 `sface_verify.py` |

- 下载或修复：在仓库根目录运行 `bash tools/download_models.sh`。它会校验 SHA256，只下载缺失或不一致的文件。
- 两个模型都通过 OpenCV 的 `cv2.FaceDetectorYN` 和 `cv2.FaceRecognizerSF` 调用，需要较新的 OpenCV。本仓库在 ROS 环境的 python3-opencv 4.10（Ubuntu 26.04 apt）和训练环境的 opencv-python 4.x 上都验证过；已确认 OpenCV 4.6（Ubuntu 24.04 自带）不能运行 YuNet 2023mar。
- OpenCV Zoo 另有一个 `face_detection_yunet_2026may.onnx`（动态输入尺寸，面向 OpenCV 5.x）。本课程使用 OpenCV 4.x，所以用 2023mar 版本。
- 模型随 `hci_perception` 包安装，代码里用 `hci_perception.recognition.yunet.default_model()` 找到它，启动节点时不用写路径。
- 来源：https://github.com/opencv/opencv_zoo （`models/face_detection_yunet`、`models/face_recognition_sface`）
- **不要**把你自己训练的 `best.pt`、`best.onnx` 或登记文件 `me_sface.npy` 放到这里：它们属于你的个人数据，应该留在 `exercises/face_recognition/runs/` 和 `exercises/face_recognition/data/`（`.gitignore` 已经排除）。
