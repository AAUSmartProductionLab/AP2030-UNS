cmake_minimum_required(VERSION 3.22.1)
project(bt_controller C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_BUILD_TYPE Debug) # Note: Consider not forcing build type directly in CMakeLists

add_subdirectory(third_party/json)
add_subdirectory(third_party/magic_enum)
add_subdirectory(third_party/json-schema-validator)

# Add Paho and BehaviorTree.CPP as subdirectories
# It's good practice to set options for submodules to avoid building unnecessary parts
# and to control linkage (e.g., prefer static libraries for Docker images).

# Paho.mqtt.cpp options (check Paho's CMakeLists.txt for exact option names)
set(PAHO_WITH_MQTT_C ON CACHE BOOL "Build Paho with MQTT C library")
set(PAHO_BUILD_STATIC OFF CACHE BOOL "Build Paho libraries as static") # Prefer static
set(PAHO_BUILD_SHARED ON CACHE BOOL "Build Paho libraries as shared")
set(PAHO_BUILD_SAMPLES OFF CACHE BOOL "Do not build Paho samples")
set(PAHO_BUILD_EXAMPLES OFF CACHE BOOL "Do not build Paho examples") # If 'examples' is the correct option name
add_subdirectory(third_party/paho.mqtt.cpp)

# BehaviorTree.CPP options (check BehaviorTree.CPP's CMakeLists.txt for exact option names)
set(BTCPP_SHARED_LIBS OFF CACHE BOOL "Build BehaviorTree.CPP as a static library") # Prefer static
set(BTCPP_EXAMPLES OFF CACHE BOOL "Do not build BehaviorTree.CPP examples")
set(BUILD_TESTING OFF CACHE BOOL "Do not build BehaviorTree.CPP examples")
set(ENABLE_COROUTINES ON CACHE BOOL "Enable coroutines if your C++ version supports it") # Example option
add_subdirectory(third_party/BehaviorTree.CPP)


# Find external packages
find_package(PkgConfig REQUIRED)
find_package(Threads REQUIRED)
find_package(yaml-cpp REQUIRED)
find_package(fmt REQUIRED)
pkg_check_modules(UUID REQUIRED uuid)


add_library(bt_controller_common STATIC
    src/utils.cpp
    src/mqtt/node_message_distributor.cpp
    src/mqtt/mqtt_client.cpp
    src/mqtt/mqtt_sub_base.cpp
    src/mqtt/mqtt_pub_base.cpp
    src/bt/mqtt_action_node.cpp
    src/bt/mqtt_condition_node.cpp
    src/bt/mqtt_async_sub_node.cpp
    src/bt/actions/move_shuttle_to_position.cpp
    src/bt/actions/omron_arcl_request_node.cpp
    src/bt/actions/generic_action_node.cpp
    src/bt/actions/configuration_node.cpp
    src/bt/conditions/generic_condition_node.cpp
    src/bt/controls/bc_fallback_node.cpp
)

target_include_directories(bt_controller_common
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
        ${YAML_CPP_INCLUDE_DIRS}
        # The include directories for paho and bt.cpp should be handled by target_link_libraries
        # if their CMake targets are set up correctly with PUBLIC/INTERFACE include directories.
    PRIVATE
        /usr/local/include # This might not be needed if all deps are handled via CMake targets
        ${UUID_INCLUDE_DIRS}
)

target_link_libraries(bt_controller_common
    PUBLIC
        nlohmann_json_schema_validator::validator
        behaviortree_cpp
        paho-mqttpp3
        paho-mqtt3as
        Threads::Threads
        ${YAML_CPP_LIBRARIES}
        fmt::fmt
        magic_enum::magic_enum
        ${UUID_LIBRARIES}
)

add_executable(bt_controller
    src/BehaviorTreeController.cpp
)

target_include_directories(bt_controller
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
    PRIVATE
        /usr/local/include # This might not be needed
)

target_link_libraries(bt_controller
    PRIVATE
    bt_controller_common
)