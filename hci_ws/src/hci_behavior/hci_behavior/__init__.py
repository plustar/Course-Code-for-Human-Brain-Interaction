"""
hci_behavior：机器响应——机器人看到人之后做什么。

纯 Python 部分，三步各自可测：
  estimator      估计：挑出要找的人，防抖、平滑
  state_machine  决策：STOP / SEARCH / ALIGN / APPROACH / GREET
  safety         安全：暂停、看门狗、只有 APPROACH 能前进、最近距离、限速
  config         三步共用的参数（SI 单位）
ROS 外壳（hci_behavior.ros）：behavior_node
"""
