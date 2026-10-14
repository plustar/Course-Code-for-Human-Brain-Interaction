# 单个检测结果（一张人脸；改测学生证的同学就是一张证件）
string class_name       # 模型类别名，如 "stu_2023123456"（本人）或 "face"（他人）
string display_name     # 显示名，如 "张三 2023123456"；他人为 "他人"
float32 confidence      # 置信度 0.0–1.0
int32 x_min             # 边界框左上角 x（像素，原图坐标）
int32 y_min             # 边界框左上角 y（像素）
int32 x_max             # 边界框右下角 x（像素）
int32 y_max             # 边界框右下角 y（像素）
float32 bearing         # 方位角（弧度）：相机机体系（x 前、y 左）里，正前方为 0，左正（REP 103）
float32 distance        # 相机到目标的直线距离（米），由框高、目标实际高度和相机内参估计；估不出时为 NaN
