# 行为节点每个控制周期发布一次的状态，可以直接用 rqt_plot 画曲线、放进报告
uint8 STOP=0            # 停车：没确认看到本人、只看到他人、看门狗超时或已暂停
uint8 SEARCH=1          # 原地慢转寻找本人（search_turn_rate > 0 时）
uint8 ALIGN=2           # 原地转向，对准本人
uint8 APPROACH=3        # 已对准，向前靠近
uint8 GREET=4           # 到达问候距离：停下问候，只原地转动保持面向对方

std_msgs/Header header
uint8 state             # 上面五个常量之一
string reason           # 进入当前状态的原因，如 "看门狗：检测结果超时"
bool enabled            # false 表示已用 ~/enable 服务暂停
string target_name      # 正在跟随的人的显示名；没有目标时为空
float32 target_bearing  # 目标的方位角（弧度，左正）；没有目标时为 NaN
float32 target_distance # 目标的距离（米）；没有目标时为 NaN
float32 linear          # 本周期下发的线速度（m/s）
float32 angular         # 本周期下发的角速度（rad/s，逆时针为正）
float32 latency         # 从图像采集到下发速度的时间（秒）；没有目标时为 NaN
