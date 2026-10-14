# 一帧图像中的全部检测结果
std_msgs/Header header  # 必须原样复制自对应图像的 header（时间戳 + frame_id）
uint32 image_width      # 图像宽度（像素）
uint32 image_height     # 图像高度（像素）
Detection[] detections  # 本帧所有检测结果（可以为空）
