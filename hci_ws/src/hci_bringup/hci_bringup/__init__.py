"""
hci_bringup：系统怎么启动只在这一个地方。

  launch/perception.launch.py  感知：相机 -> 识别 -> 显示（练习 4）
  launch/system.launch.py      整个闭环：感知 + 行为 + 机器人（期末），可选仿真相机与录包
  config/                      各节点的参数、各机器人平台的参数、仿真世界
  hci_bringup/options.py       启动参数的组合规则（launch 与测试共用）
"""
