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

# ---------------------------------------------------------------------------
# jsonata-cpp (rayokota/jsonata-cpp) - JSONata expression evaluator.
#
# Pulled in via FetchContent. If the build environment does not have
# internet access, drop the v0.1.2 release zip into
# BT_Controller/third_party/jsonata-cpp/v0.1.2.zip and the URL will be
# read from the local file via the file:// scheme.
# ---------------------------------------------------------------------------
include(FetchContent)
set(JSONATA_LOCAL_ZIP "${CMAKE_CURRENT_SOURCE_DIR}/third_party/jsonata-cpp/v0.1.2.zip")
if(EXISTS "${JSONATA_LOCAL_ZIP}")
    set(JSONATA_URL "file://${JSONATA_LOCAL_ZIP}")
else()
    set(JSONATA_URL "https://github.com/rayokota/jsonata-cpp/archive/refs/tags/v0.1.2.zip")
endif()
FetchContent_Declare(
    jsonata
    URL ${JSONATA_URL}
)
FetchContent_MakeAvailable(jsonata)

add_library(bt_controller_common STATIC
    src/utils.cpp
    src/mqtt/node_message_distributor.cpp
    src/mqtt/mqtt_client.cpp
    src/aas/aas_client.cpp
    src/aas/aas_interface_cache.cpp
    src/aas/transformation_resolver.cpp
    src/mqtt/mqtt_sub_base.cpp
    src/mqtt/mqtt_pub_base.cpp
    src/bt/execution_refs.cpp
    src/bt/bt_log.cpp
    src/bt/symbolic_state.cpp
    src/bt/bt_runtime_validator.cpp
    src/bt/mqtt_action_node.cpp
    src/bt/mqtt_sync_action_node.cpp
    src/bt/mqtt_sync_condition_node.cpp
    src/bt/mqtt_decorator.cpp
    src/bt/actions/generic_action_node.cpp
    src/bt/actions/command_execute_node.cpp
    src/bt/actions/configuration_node.cpp
    src/bt/actions/pop_element_node.cpp
    src/bt/actions/refill_node.cpp
    src/bt/actions/retrieve_aas_properties_node.cpp
    src/bt/actions/execute_action_node.cpp
    src/bt/conditions/generic_condition_node.cpp
    src/bt/conditions/fluent_check_node.cpp
    src/bt/decorators/occupy.cpp
    src/bt/decorators/get_product_from_queue.cpp
    src/bt/decorators/keep_running_until_empty.cpp
    src/bt/decorators/sampling_gate.cpp
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
        jsonata::jsonata
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

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
option(BT_CONTROLLER_BUILD_TESTS "Build BT_Controller unit tests" OFF)
if(BT_CONTROLLER_BUILD_TESTS)
    find_package(GTest REQUIRED)
    enable_testing()
    add_executable(test_execution_refs
        tests/test_execution_refs.cpp
    )
    target_link_libraries(test_execution_refs
        PRIVATE
            bt_controller_common
            GTest::gtest
            GTest::gtest_main
    )
    add_test(NAME test_execution_refs COMMAND test_execution_refs)

    add_executable(test_symbolic_state
        tests/test_symbolic_state.cpp
    )
    target_link_libraries(test_symbolic_state
        PRIVATE
            bt_controller_common
            GTest::gtest
            GTest::gtest_main
    )
    add_test(NAME test_symbolic_state COMMAND test_symbolic_state)
endif()