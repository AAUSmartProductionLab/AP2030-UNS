cmake_minimum_required(VERSION 3.5)
project(async_publish C CXX)

# Set C++ standard early
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Add JSON library (header-only)
add_library(json INTERFACE)
target_include_directories(json INTERFACE 
    ${CMAKE_CURRENT_SOURCE_DIR}/../../third_party/json/include
)

# Add JSON schema validator
add_library(json_schema_validator STATIC
    ${CMAKE_CURRENT_SOURCE_DIR}/../../third_party/json-schema-validator/src/json-schema-draft7.json.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../third_party/json-schema-validator/src/json-uri.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../third_party/json-schema-validator/src/json-validator.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../third_party/json-schema-validator/src/json-patch.cpp
)
target_include_directories(json_schema_validator PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/../../third_party/json-schema-validator/src
    ${CMAKE_CURRENT_SOURCE_DIR}/../../third_party/json/include
)
target_link_libraries(json_schema_validator PUBLIC json)

# Other packages
find_package(PkgConfig REQUIRED)
find_package(Threads REQUIRED)
find_package(PahoMqttCpp REQUIRED)
find_package(behaviortree_cpp REQUIRED)

pkg_check_modules(UUID REQUIRED uuid)


include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${PahoMqttCpp_INCLUDE_DIRS}
)

add_executable(async_publish
    async_publish.cpp
    mqtt/utils.cpp
    mqtt/callbacks.cpp
    mqtt/mqtttopic.cpp
    mqtt/proxy.cpp
)

target_include_directories(${PROJECT_NAME} PRIVATE 
    /usr/local/include
    ${CMAKE_CURRENT_SOURCE_DIR}/../../third_party/json/include
    ${CMAKE_CURRENT_SOURCE_DIR}/../../third_party/json-schema-validator/src
)

target_link_libraries(${PROJECT_NAME} 
    PahoMqttCpp::paho-mqttpp3 
    PahoMqttCpp::paho-mqtt3as 
    ${UUID_LDFLAGS} 
    json_schema_validator
    behaviortree_cpp
)