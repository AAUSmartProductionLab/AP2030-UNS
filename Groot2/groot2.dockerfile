FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install Groot2 dependencies, and VNC components
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    # Groot2 OpenGL dependencies
    libglvnd0 libgl1 libglx0 libegl1 libxkbcommon0 libxcomposite1 \
    libxcursor1 libxdamage1 libxfixes3 libxi6 libxrandr2 libxtst6 libfontconfig1 \
    libopengl0 libglu1 mesa-utils libsm6 libxext6 \
    # VNC and minimal window manager
    tigervnc-standalone-server \
    tigervnc-common \
    novnc \
    x11-xserver-utils \
    openbox \
    websockify \
    # Tool to automate window actions
    xdotool \
    # For noVNC customization
    sed \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Download and extract Groot2
RUN mkdir -p /opt/groot && \
    cd /tmp && \
    curl -L -o Groot2.AppImage https://s3.us-west-1.amazonaws.com/download.behaviortree.dev/groot2_linux_installer/Groot2-v1.6.1-x86_64.AppImage && \
    chmod +x Groot2.AppImage && \
    ./Groot2.AppImage --appimage-extract && \
    mv squashfs-root/* /opt/groot/ && \
    rm -rf /tmp/squashfs-root Groot2.AppImage

# Configure VNC with a secure empty password
RUN mkdir -p /root/.vnc && \
    echo "robotlab" | vncpasswd -f > /root/.vnc/passwd && \
    chmod 600 /root/.vnc/passwd

# Create Openbox configuration to maximize Groot2 and remove all window decorations
RUN mkdir -p /root/.config/openbox && \
    echo '<?xml version="1.0" encoding="UTF-8"?>' > /root/.config/openbox/rc.xml && \
    echo '<openbox_config xmlns="http://openbox.org/3.4/rc">' >> /root/.config/openbox/rc.xml && \
    echo '  <theme>' >> /root/.config/openbox/rc.xml && \
    echo '    <titleLayout></titleLayout>' >> /root/.config/openbox/rc.xml && \
    echo '  </theme>' >> /root/.config/openbox/rc.xml && \
    echo '  <applications>' >> /root/.config/openbox/rc.xml && \
    echo '    <application name="*">' >> /root/.config/openbox/rc.xml && \
    echo '      <maximized>yes</maximized>' >> /root/.config/openbox/rc.xml && \
    echo '      <decor>no</decor>' >> /root/.config/openbox/rc.xml && \
    echo '    </application>' >> /root/.config/openbox/rc.xml && \
    echo '  </applications>' >> /root/.config/openbox/rc.xml && \
    echo '</openbox_config>' >> /root/.config/openbox/rc.xml

# Modify noVNC to auto-connect without showing the connection screen
RUN sed -i 's/UI.connect();/UI.connect(); document.getElementById("noVNC_connect_button").click();/' /usr/share/novnc/app/ui.js

# Create startup script for VNC server with minimal window manager
RUN echo '#!/bin/bash' > /usr/local/bin/start-vnc && \
    echo 'vncserver :1 -geometry 2560x1440 -depth 24 -localhost no -xstartup /usr/bin/openbox-session' >> /usr/local/bin/start-vnc && \
    echo 'websockify -D --web=/usr/share/novnc/ 6080 localhost:5901' >> /usr/local/bin/start-vnc && \
    chmod +x /usr/local/bin/start-vnc

# Create custom index.html for noVNC to auto-connect
RUN echo '<!DOCTYPE html>' > /usr/share/novnc/index.html && \
    echo '<html><head>' >> /usr/share/novnc/index.html && \
    echo '<meta http-equiv="refresh" content="0; url=vnc.html?autoconnect=true&reconnect=true&reconnect_delay=1000&resize=remote&quality=9&compression=0&view_only=0">' >> /usr/share/novnc/index.html && \
    echo '</head></html>' >> /usr/share/novnc/index.html

# Create Groot2 script with VNC display and auto-maximize
RUN echo '#!/bin/bash' > /usr/local/bin/groot2 && \
    echo 'export DISPLAY=:1' >> /usr/local/bin/groot2 && \
    echo 'cd /opt/groot && ./AppRun "$@" &' >> /usr/local/bin/groot2 && \
    echo 'sleep 2' >> /usr/local/bin/groot2 && \
    echo 'xdotool search --class "Groot2" windowactivate %@ windowmaximize %@' >> /usr/local/bin/groot2 && \
    chmod +x /usr/local/bin/groot2

# Create entrypoint script with proper startup sequencing
RUN echo '#!/bin/bash' > /usr/local/bin/entrypoint.sh && \
    echo 'start-vnc' >> /usr/local/bin/entrypoint.sh && \
    echo 'sleep 3  # Give VNC server time to start' >> /usr/local/bin/entrypoint.sh && \
    echo 'export DISPLAY=:1' >> /usr/local/bin/entrypoint.sh && \
    echo 'groot2 &' >> /usr/local/bin/entrypoint.sh && \
    echo 'tail -f /dev/null' >> /usr/local/bin/entrypoint.sh && \
    chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 6080

# Set working directory
WORKDIR /workspaces

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]