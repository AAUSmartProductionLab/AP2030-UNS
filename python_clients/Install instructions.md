# Install Instructions 
- The instructions are for linux and executed on a Ubuntu-22.04 WSL

## ROS2
- [ROS2 Humble Install instructions](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html)
## Installation of Behavior Tree.cpp and build using ros2' colcon
```bash
sudo apt-get install libzmq3-dev libboost-dev
pip install catkin_pkg
git clone https://github.com/BehaviorTree/BehaviorTree.CPP.git
cd BehaviorTree.CPP
mkdir build
colcon build
```

## Installation of Groot2
- Go to [Groot Website](https://www.behaviortree.dev/groot/) and donwload the Linux installer
```bash 
sudo apt install qtwayland5
chmod +x Groot2-v1.6.1-linux-installer.run
./Groot2-v1.6.1-linux-installer.run
echo -e "\nexport QT_QPA_PLATFORM=\"xcb\"" >> ~/.bashrc
echo -e "\nalias groot2='/home/${USER}/Groot2/bin/groot2'" >> ~/.bashrc
```
- Groot can now be openend with ```groot2```

## Installation of paho.mqtt.cpp
- Instruction from [paho.mqtt.cpp git repo](https://github.com/eclipse-paho/paho.mqtt.cpp?tab=readme-ov-file#build-the-paho-c-and-paho-c-libraries-together)
```bash
#Not sure if these are truly necessary
sudo apt-get install build-essential gcc make cmake
sudo apt-get install libssl-dev
sudo apt-get install doxygen graphviz

git clone https://github.com/eclipse/paho.mqtt.cpp
cd paho.mqtt.cpp
git checkout v1.5.0
git submodule init
git submodule update
cmake -Bbuild -H. -DPAHO_WITH_MQTT_C=ON -DPAHO_BUILD_EXAMPLES=ON
sudo cmake --build build/ --target install
sudo ldconfig
```

## C++ json validation
```bash
    # Clone specific versions
    
    git clone -b v3.11.2 https://github.com/nlohmann/json.git
    git clone -b v2.3.0 https://github.com/pboettch/json-schema-validator.git

    # Build and install in the same order
    cd json
    mkdir build && cd build
    cmake .. 
    make install

    cd ../../json-schema-validator
    mkdir build && cd build
    cmake .. -DJSON_VALIDATOR_BUILD_TESTS=OFF
    make install
```

## Install Docker
```bash
    sudo apt-get install ca-certificates curl
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    sudo docker run hello-world
```

## Install Docker Compose
```bash
    sudo apt-get update
    sudo apt-get install docker-compose-plugin
    docker compose version
```

## Docker post Install Steps
```bash
    sudo groupadd docker
    sudo usermod -aG docker $USER
    newgrp docker
    sudo systemctl enable docker.service
    sudo systemctl enable containerd.service
```