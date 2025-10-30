cmake_minimum_required(VERSION 3.22.1)
project(bt_controller C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(PkgConfig REQUIRED)
find_package(Threads REQUIRED)
find_package(yaml-cpp REQUIRED)
find_package(fmt REQUIRED)
find_package(magic_enum REQUIRED)
find_package(nlohmann_json_schema_validator REQUIRED)
find_package(PahoMqttCpp REQUIRED)
find_package(behaviortree_cpp REQUIRED)
pkg_check_modules(UUID REQUIRED uuid)
find_package(CURL REQUIRED)

add_library(bt_controller_common STATIC
    src/utils.cpp
    src/mqtt/node_message_distributor.cpp
    src/mqtt/mqtt_client.cpp
    src/aas/aas_client.cpp
    src/mqtt/mqtt_sub_base.cpp
    src/mqtt/mqtt_pub_base.cpp
    src/bt/mqtt_action_node.cpp
    src/bt/mqtt_sync_action_node.cpp
    src/bt/mqtt_sync_condition_node.cpp
    src/bt/mqtt_decorator.cpp
    src/bt/actions/move_to_position.cpp
    src/bt/actions/generic_action_node.cpp
    src/bt/actions/command_execute_node.cpp
    src/bt/actions/configuration_node.cpp
    src/bt/actions/pop_element_node.cpp
    src/bt/actions/refill_node.cpp
    src/bt/conditions/generic_condition_node.cpp
    src/bt/decorators/occupy.cpp
    src/bt/decorators/get_product_from_queue.cpp
    src/bt/decorators/keep_running_until_empty.cpp
    src/bt/controls/bc_fallback_node.cpp
)

target_include_directories(bt_controller_common
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
        ${YAML_CPP_INCLUDE_DIRS}
    PRIVATE
        ${UUID_INCLUDE_DIRS}
)

target_link_libraries(bt_controller_common
    PUBLIC
        nlohmann_json_schema_validator::validator
        behaviortree_cpp
        PahoMqttCpp::paho-mqttpp3
        Threads::Threads
        ${YAML_CPP_LIBRARIES}
        fmt::fmt
        magic_enum::magic_enum
        ${UUID_LIBRARIES}
    PRIVATE
        CURL::libcurl
)

add_executable(bt_controller
    src/BehaviorTreeController.cpp
)

target_include_directories(bt_controller
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(bt_controller
    PRIVATE
    bt_controller_common
)