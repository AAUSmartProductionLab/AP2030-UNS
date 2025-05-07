cmake_minimum_required(VERSION 3.22.1)
project(bt_controller C CXX)

# Set C++ standard early
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Add JSON library (header-only)
add_library(json INTERFACE)
target_include_directories(json INTERFACE 
    ${CMAKE_CURRENT_SOURCE_DIR}/third_party/json/include
)

# Add JSON schema validator
add_library(json_schema_validator STATIC
    ${CMAKE_CURRENT_SOURCE_DIR}/third_party/json-schema-validator/src/json-schema-draft7.json.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/third_party/json-schema-validator/src/json-uri.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/third_party/json-schema-validator/src/json-validator.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/third_party/json-schema-validator/src/json-patch.cpp
)
target_include_directories(json_schema_validator PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/third_party/json-schema-validator/src
    ${CMAKE_CURRENT_SOURCE_DIR}/third_party/json/include
)
target_link_libraries(json_schema_validator PUBLIC json)

# Other packages
find_package(PkgConfig REQUIRED)
find_package(Threads REQUIRED)
find_package(PahoMqttCpp REQUIRED)
find_package(behaviortree_cpp REQUIRED)
find_package(yaml-cpp REQUIRED)
find_package(fmt REQUIRED)
pkg_check_modules(UUID REQUIRED uuid)


include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${PahoMqttCpp_INCLUDE_DIRS}
)

# Create common library with shared source files
add_library(bt_controller_common STATIC
    src/mqtt/utils.cpp
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
    PRIVATE
        /usr/local/include
)

target_link_libraries(bt_controller_common
    PUBLIC
        json_schema_validator
        behaviortree_cpp
        PahoMqttCpp::paho-mqttpp3
        PahoMqttCpp::paho-mqtt3as
        ${UUID_LDFLAGS}
        ${YAML_CPP_LIBRARIES}
        fmt::fmt
)

add_executable(bt_controller
    src/bt_controller.cpp
)

target_include_directories(${PROJECT_NAME} 
    PUBLIC   
        ${CMAKE_CURRENT_SOURCE_DIR}/include
    PRIVATE 
        /usr/local/include
        ${CMAKE_CURRENT_SOURCE_DIR}/third_party/json/include
        ${CMAKE_CURRENT_SOURCE_DIR}/third_party/json-schema-validator/src
)

target_link_libraries(${PROJECT_NAME} 
    bt_controller_common
)

# # Add model generator executable
# add_executable(generate_model_xml
#     src/bt/Description/generate_model_xml.cpp
# )

# target_include_directories(generate_model_xml PRIVATE 
#     /usr/local/include
#     ${CMAKE_CURRENT_SOURCE_DIR}/third_party/json/include
#     ${CMAKE_CURRENT_SOURCE_DIR}/third_party/json-schema-validator/src
# )

# target_link_libraries(generate_model_xml 
#     bt_controller_common
# )