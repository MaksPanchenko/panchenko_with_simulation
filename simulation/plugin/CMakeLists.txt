find_package(gz-sim8 REQUIRED)
find_package(gz-plugin2 REQUIRED)
find_package(gz-math7 REQUIRED)
find_package(gz-transport13 REQUIRED)
add_library(BetaflightPlugin SHARED src/BetaflightPlugin.cpp src/BetaflightSocket.cpp src/Util.cpp)
target_include_directories(BetaflightPlugin PRIVATE include)
target_link_libraries(BetaflightPlugin PRIVATE gz-sim8::gz-sim8 gz-plugin2::register
  gz-math7::gz-math7 gz-transport13::gz-transport13)
install(TARGETS BetaflightPlugin DESTINATION lib)
