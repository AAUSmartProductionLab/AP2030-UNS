cmake_minimum_required(VERSION 3.22.1)
project(bt_controller C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_BUILD_TYPE Debug) # Note: Consider not forcing build type directly in CMakeLists

add_subdirectory(third_party/json)
add_subdirectory(third_party/magic_enum)
add_subdirectory(third_party/json-schema-validator)

# Find external packages
find_package(PkgConfig REQUIRED)
find_package(Threads REQUIRED)
find_package(PahoMqttCpp REQUIRED)
find_package(behaviortree_cpp REQUIRED)
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
    PRIVATE
        /usr/local/include
        ${UUID_INCLUDE_DIRS}
)

target_link_libraries(bt_controller_common
    PUBLIC
        nlohmann_json_schema_validator::validator
        behaviortree_cpp                          
        PahoMqttCpp::paho-mqttpp3                 
        PahoMqttCpp::paho-mqtt3as                 
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
        /usr/local/include
)

target_link_libraries(bt_controller
    PRIVATE
    bt_controller_common
)
