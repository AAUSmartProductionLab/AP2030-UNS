FROM ubuntu:jammy

#Use the following for a non-dev container
# FROM ubuntu:22.04


# Avoid prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install essential build tools and dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    make \
    git \
    gcc \
    libssl-dev \
    python3-pip \
    python3-venv \
    sudo \
    pkg-config \
    uuid-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create and use a virtual environment for Conan
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install conan

# Build Paho
WORKDIR /src
RUN git clone https://github.com/eclipse-paho/paho.mqtt.cpp.git
WORKDIR /src/paho.mqtt.cpp
RUN git checkout v1.5.2
RUN git submodule update --init
RUN cmake -Bbuild -H. -DPAHO_WITH_MQTT_C=ON -DPAHO_BUILD_EXAMPLES=ON
RUN cmake --build build/ --target install
RUN ldconfig

# Build BehaviorTree.CPP
WORKDIR /src
RUN git clone https://github.com/BehaviorTree/BehaviorTree.CPP.git
WORKDIR /src/BehaviorTree.CPP
RUN conan profile detect
RUN mkdir build && cd build && \
    conan install .. --output-folder=. --build=missing && \
    cmake .. -DCMAKE_TOOLCHAIN_FILE="conan_toolchain.cmake" && \
    cmake --build . --parallel && \
    make install

    
# Clone third-party dependencies
WORKDIR /src
RUN mkdir -p /src/planar-motors-experiments/third_party
WORKDIR /src/planar-motors-experiments/third_party
RUN git clone https://github.com/nlohmann/json.git
RUN git clone https://github.com/pboettch/json-schema-validator.git


# Copy the repository content from the host (excluding build directories)
WORKDIR /src
RUN mkdir -p /src/planar-motors-experiments/MQTT_BT_Controller
COPY MQTT_BT_Controller/*.* /src/planar-motors-experiments/MQTT_BT_Controller/
COPY MQTT_BT_Controller/include /src/planar-motors-experiments/MQTT_BT_Controller/include
COPY MQTT_BT_Controller/src /src/planar-motors-experiments/MQTT_BT_Controller/src
COPY MQTT_BT_Controller/schemas /src/planar-motors-experiments/MQTT_BT_Controller/schemas
# Build the project (the code will be copied during build with Docker context)
WORKDIR /src/planar-motors-experiments/MQTT_BT_Controller
RUN mkdir -p build && cd build && \
    cmake .. && \
    make -j$(nproc)

WORKDIR /src/planar-motors-experiments/MQTT_BT_Controller/build
CMD ["./bt_controller"]