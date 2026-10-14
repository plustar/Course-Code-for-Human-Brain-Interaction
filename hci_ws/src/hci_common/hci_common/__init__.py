"""
hci_common：几个功能包都要用的地基。

纯 Python 部分（不导入 ROS，训练环境里也能用）：
  camera_model  针孔相机模型：像素与方位角、目标像素高与距离互算
  identity      "认出我"的命名约定：类别名 stu_<学号> 与 face、显示名
  params        用 dataclass 描述节点参数（名称、默认值、中文说明）
  rate          限制处理频率
  samples       测试与仿真用的公有领域人脸照片

ROS 外壳（hci_common.ros，只在 ROS 环境里用）：
  params        把 dataclass 里的参数声明给 ROS 节点
  runner        启动节点、Ctrl+C 与 kill 时先清理再退出
  image_msgs    图像消息、压缩图像、相机内参与 NumPy 的互相转换
  qos           图像话题的 QoS：只处理最新一帧，可靠性与发布端相配
  testing       测试用的隔离通信环境、探针节点和子进程管理
"""
