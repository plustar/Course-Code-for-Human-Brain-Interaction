"""
hci_sim：轻量仿真器——turtlesim 里的虚拟人，加一台装在机器人头上的虚拟相机。

纯 Python 部分（只用 NumPy 和 OpenCV）：
  world     虚拟人与机器人位姿（turtlesim 坐标）
  renderer  按针孔相机模型渲染机器人看到的画面
ROS 外壳（hci_sim.ros）：virtual_camera_node
"""
