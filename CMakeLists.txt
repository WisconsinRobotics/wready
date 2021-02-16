cmake_minimum_required(VERSION 3.0.2)
project(wready)

find_package(catkin REQUIRED COMPONENTS
    rospy
    std_msgs
    message_generation
)

include_directories(
    ${catkin_INCLUDE_DIRS}
)

catkin_python_setup()

# Generate messages in the 'msg' folder
add_message_files(
  FILES
  InitNotify.msg
  InitProgress.msg
)

# Generate services in the 'srv' folder
add_service_files(
  FILES
  InitRequest.srv
)

# Generate added messages and services with any dependencies listed here
generate_messages(
  DEPENDENCIES std_msgs
)

catkin_package(
  CATKIN_DEPENDS message_runtime
)
