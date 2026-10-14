cmake_minimum_required(VERSION 3.20)

# ROS 2 的 Python 接口必须用系统 Python 生成。conda 环境激活时，CMake 可能找到 conda 里的
# Python，生成的消息代码在系统 Python 里就用不了，所以这里直接报错提醒。
# 放在 project() 之前：project() 会先找编译器，这条提示不能被它的报错挡住。
# 用“非空”判断（与 run_tests.sh、check_env.sh、setup_ros_env.sh 的 [ -n "$CONDA_PREFIX" ] 一致）：
# conda deactivate 后有时会把 CONDA_PREFIX 留成空字符串，只判断 DEFINED 会把这种残留误当成
# “conda 仍激活”，报出括号里为空的假错误。
if(DEFINED ENV{CONDA_PREFIX} AND NOT "$ENV{CONDA_PREFIX}" STREQUAL "")
  set(vscode_hint "")
  if("$ENV{TERM_PROGRAM}" STREQUAL "vscode")
    set(vscode_hint "VS Code 的终端：确认打开的文件夹就是 hci-course-code，然后关掉这个终端、新开一个。")
  endif()
  message(FATAL_ERROR "检测到 conda 环境（$ENV{CONDA_PREFIX}）处于激活状态。"
    "编译和运行 ROS 前请先执行 conda deactivate，然后删除 build install log 重新编译。${vscode_hint}")
endif()

project(hci_interfaces)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)

# 生成自定义消息（C / C++ / Python 代码）
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/Detection.msg"
  "msg/DetectionArray.msg"
  "msg/BehaviorState.msg"
  DEPENDENCIES std_msgs
)

ament_export_dependencies(rosidl_default_runtime)

if(BUILD_TESTING)
  # package.xml 的格式检查（ament_xmllint）
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
