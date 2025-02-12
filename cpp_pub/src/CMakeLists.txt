cmake_minimum_required(VERSION 3.5)

project(async_publish C CXX)

find_package(PkgConfig REQUIRED)
find_package(Threads REQUIRED)
find_package(PahoMqttCpp REQUIRED)
find_package(nlohmann_json REQUIRED)
find_package(behaviortree_cpp REQUIRED)

pkg_check_modules(UUID REQUIRED uuid)

# Manually specify the JSON schema validator library
find_library(nlohmann_json_schema_validator
    PATHS /usr/local/lib
)

add_executable(async_publish async_publish.cpp)

target_link_libraries(${PROJECT_NAME} 
    PahoMqttCpp::paho-mqttpp3 
    PahoMqttCpp::paho-mqtt3as 
    ${UUID_LDFLAGS} 
    ${JSON_SCHEMA_VALIDATOR_LIB}
    nlohmann_json::nlohmann_json 
    behaviortree_cpp
)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# target_include_directories(${PROJECT_NAME} PRIVATE 
#     /usr/local/include/nlohmann
# )