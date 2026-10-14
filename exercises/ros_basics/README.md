# 练习 2：ROS 2 基础（自查，不提交）

目标：确认 ROS 2 Lyrical 已经装好，并理解节点、话题、消息、服务、动作、QoS 这几个概念。练习 4 和期末都要用到它们。

本练习的脚本都在 **ROS 环境**里运行，也就是系统自带的 Python 3.14。每个终端先执行 `source /opt/ros/lyrical/setup.bash`（运行过 `bash env/setup_ros_env.sh --bashrc` 的话，新终端会自动执行），并且**不要激活 conda**。`cam_pub.py` 和 `cam_view.py` 要用 OpenCV，它由 `setup_ros_env.sh` 用 apt 安装（`python3-opencv`）。

| 文件 | 概念 | 做什么 | 运行 | 自查：看到什么算成功 |
|---|---|---|---|---|
| `talker.py` | 发布者 | 每 0.5 秒向 `/chatter` 发布一句话 | `python3 talker.py` | 终端不断打印"发布：你好，ROS 2！第 N 条" |
| `listener.py` | 订阅者 | 订阅 `/chatter` 并打印 | 另开终端 `python3 listener.py` | 收到的序号与发布的一致 |
| `turtle_circle.py` | 话题控制机器人 | 以 10 Hz 向 `/turtle1/cmd_vel` 发 Twist，让海龟画圆 | 终端 1 `ros2 run turtlesim turtlesim_node`，终端 2 `python3 turtle_circle.py --v 2.0 --w 1.0` | 海龟画出半径 r = v/ω = 2 的圆；按 Ctrl+C 后海龟停下 |
| `turtle_spawn.py` | 服务 | 调用 `/spawn`，在指定位置放一只新海龟 | `python3 turtle_spawn.py --x 2 --y 8 --name buddy` | 窗口里多了一只海龟；`ros2 topic echo /buddy/pose` 有数据 |
| `turtle_rotate.py` | 动作 | 用 `/turtle1/rotate_absolute` 让海龟转到指定朝向，打印进度 | `python3 turtle_rotate.py --theta 90` | 海龟转到朝上，终端打印一串"还差 …°"的反馈和最后的结果 |
| `cam_pub.py` | 图像消息 | 摄像头或视频 → `/camera/image_raw`（bgr8） | `python3 cam_pub.py --source 0`；WSL2 先按根目录 README 第 4.7 节转发摄像头，也可用 `--source /绝对路径/me.mp4` | `ros2 topic hz /camera/image_raw` 约 30 Hz（视频文件按它自己的帧率） |
| `cam_view.py` | QoS | 订阅图像并显示，左上角显示延迟和收到的帧率 | `python3 cam_view.py`；对比 `--reliable` | 窗口里有画面，延迟只有几毫秒 |

这些脚本由 `tests/test_scripts.py` 自动测试（`bash tools/run_tests.sh` 会运行它）。

## 顺便练习这些命令（练习 4 调试时天天用）

```bash
ros2 node list                          # 有哪些节点
ros2 node info /talker                  # 节点发布、订阅了什么
ros2 topic list -t                      # 话题及类型
ros2 topic echo /chatter                # 看消息内容
ros2 topic hz /camera/image_raw         # 频率
ros2 topic info /camera/image_raw -v    # 发布者和订阅者的 QoS
ros2 service list                       # 有哪些服务（turtlesim 的 /spawn、/kill……）
ros2 action list                        # 有哪些动作
ros2 interface show turtlesim_msgs/srv/Spawn
ros2 interface show turtlesim_msgs/action/RotateAbsolute
ros2 topic pub --once /turtle1/cmd_vel geometry_msgs/msg/Twist "{linear: {x: 2.0}, angular: {z: 1.8}}"
ros2 run rqt_graph rqt_graph            # 节点和话题的关系图（Lyrical 里要用 ros2 run 启动）
```

## 想一想

1. 先启动 `listener.py`，过一会儿再启动 `talker.py`，会漏掉消息吗？如果先启动 talker 呢？为什么？
2. 把 `turtle_circle.py` 的发送频率改成 0.5 Hz，海龟会怎样运动？（提示：turtlesim 大约 1 秒收不到指令就会停下。）
3. `cam_view.py` 默认用 Best Effort（`qos_profile_sensor_data`），而 `cam_pub.py` 用的是 Reliable。两者为什么能连上？反过来行不行？用 `ros2 topic info -v` 验证。再分别不加和加 `--reliable` 运行 `cam_view.py`，比较窗口里的帧率：在同一台电脑上传 640×480 这样的大图像时，Best Effort 丢掉的分片不会重传，整帧作废，收到的帧率可能明显低于发布的帧率。练习 4 的识别节点因此默认用 Reliable（参数 `image_reliability`）；订阅机器人自带的相机时按平台选择：TurtleBot 4 的相机用 Best Effort 发布，订阅端只能跟着用 Best Effort；Gazebo 里 TurtleBot 3 的相机用 Reliable 发布 1920×1080 的图像，实测用 Best Effort 订阅时每秒只收到约 1 帧。
4. 延迟由哪几部分组成？把 `cam_pub.py` 里的分辨率（640×480）调大，延迟会怎样变化？
5. `turtle_spawn.py` 为什么用服务而不用话题？`turtle_rotate.py` 为什么用动作而不用服务？各举一个机器人上的例子。

## 写法说明：两种节点模板

`talker.py` 和 `listener.py` 使用 ROS 2 Lyrical 官方教程的写法：

```python
def main():
    try:
        with rclpy.init():           # 离开 with 时自动关闭 rclpy
            node = Talker()
            rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):   # Ctrl+C
        pass
```

按下 Ctrl+C 时，`rclpy.spin` 可能抛出 `KeyboardInterrupt`，也可能抛出 `ExternalShutdownException`，所以两个都要捕获。偶尔 Ctrl+C 恰好落在 `rclpy.spin` 准备下一次等待的瞬间，终端会多打印一段以 `rcl_shutdown() was called` 结尾的 `RCLError`：这是 rclpy 处理 Ctrl+C 时的时序问题，官方模板也会遇到，不影响结果。

退出前还要做清理的节点（释放摄像头、关闭窗口、让海龟停下），改用 `try … finally`，把清理写在 `finally` 里，见 `cam_pub.py`、`cam_view.py`、`turtle_circle.py`。

`turtle_circle.py` 退出前要发一条"停止"指令。但 rclpy 默认在 Ctrl+C 的瞬间就关闭通信，这条指令会发不出去。所以它用 `rclpy.init(signal_handler_options=SignalHandlerOptions.NO)` 关掉了默认处理。期末的 `behavior_node` 也用同样的办法（见 `hci_common/ros/runner.py`），保证退出前一定停车。

`turtle_spawn.py` 和 `turtle_rotate.py` 只做一件事就退出，所以不 `spin`，而是用 `rclpy.spin_until_future_complete` 等服务的应答、动作的结果：等待期间照常处理回调（动作的反馈就是这样打印出来的）。
