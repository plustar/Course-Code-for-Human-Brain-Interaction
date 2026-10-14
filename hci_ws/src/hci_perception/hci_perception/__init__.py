"""
hci_perception：感知人、理解人——摄像头、识别、显示。

纯 Python 部分（训练环境里也能导入，练习 3 直接复用）：
  capture      图像来源：摄像头或视频文件
  recognition  识别后端：YOLO 的 ONNX、YuNet、两步法（YuNet + SFace）、Ultralytics
  overlay      画框、中文标签、状态条、给他人打码
ROS 外壳（hci_perception.ros）：camera_node、recognizer_node、viewer_node
"""
