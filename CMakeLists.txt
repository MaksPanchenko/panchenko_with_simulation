cmake_minimum_required(VERSION 3.16)
project(multiwii VERSION 2.2.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
add_compile_options(-Wall -Wextra -Wpedantic)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rcl_interfaces REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(mavros_msgs REQUIRED)
find_package(tf2 REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(Eigen3 REQUIRED)
find_package(Threads REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_path(ASIO_INCLUDE_DIR asio.hpp REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/MSPRawMessage.msg"
  "srv/ReceiveMSPRawMessage.srv"
  "srv/SendMSPRawMessage.srv")

add_library(multiwii_msp STATIC
  third_party/msp/src/Client.cpp
  third_party/msp/src/PeriodicTimer.cpp
  third_party/msp/src/FlightController.cpp)
target_include_directories(multiwii_msp PUBLIC third_party/msp/inc ${ASIO_INCLUDE_DIR}
  PRIVATE third_party/msp/inc/msp)
target_compile_definitions(multiwii_msp PUBLIC ASIO_STANDALONE)
target_link_libraries(multiwii_msp PUBLIC Threads::Threads)

add_executable(multiwii_node src/main.cpp src/multiwii_node.cpp)
target_include_directories(multiwii_node PRIVATE include)
option(MULTIWII_EMULATION_BUILD "Disable node optimization for faster builds under CPU emulation" OFF)
if(MULTIWII_EMULATION_BUILD AND CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(multiwii_node PRIVATE -O0 -g0)
endif()
ament_target_dependencies(multiwii_node
  rclcpp rcl_interfaces std_msgs geometry_msgs sensor_msgs mavros_msgs tf2 tf2_ros)
target_link_libraries(multiwii_node multiwii_msp Eigen3::Eigen)

add_executable(msp_emulator src/msp_emulator.cpp)
target_link_libraries(msp_emulator util)

install(TARGETS multiwii_node msp_emulator DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY launch cfg DESTINATION share/${PROJECT_NAME})
install(FILES third_party/msp/LICENSE DESTINATION share/${PROJECT_NAME}/licenses RENAME msp-LICENSE)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_status test/test_status.cpp)
  target_include_directories(test_status PRIVATE include)
  target_link_libraries(test_status multiwii_msp)
endif()

ament_export_dependencies(rosidl_default_runtime)
ament_package()
