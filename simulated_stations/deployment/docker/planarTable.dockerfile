##############################################
# Stage 1: Base image with Wine environment
# This stage is slow but gets cached
##############################################
FROM scottyhardy/docker-wine:stable-9.0 AS wine-base

ENV WINEDEBUG=-all
ENV WINEPREFIX=/root/.wine
# ENV WINEARCH=win32
ENV HOME=/root

USER root
RUN apt-get update && apt-get install -y xvfb cabextract procps xdotool scrot && rm -rf /var/lib/apt/lists/*

# Initialize Wine (the slow part - gets cached)
# Using explicit Xvfb with timeout to prevent hangs
RUN set -ex && \
    rm -rf /tmp/.X* && \
    Xvfb :0 -screen 0 1024x768x24 &  \
    XVFB_PID=$! && \
    sleep 3 && \
    export DISPLAY=:0 && \
    echo "Starting wineboot..." && \
    timeout 120 wineboot --init || echo "wineboot timed out or failed" && \
    echo "Wineboot complete, starting winetricks..." && \
    timeout 300 winetricks -q corefonts || echo "winetricks timed out or failed" && \
    echo "Installing .NET Framework 4.8..." && \
    timeout 600 winetricks -q dotnet48 || echo "dotnet48 timed out or failed" && \
    echo "Winetricks complete" && \
    kill $XVFB_PID 2>/dev/null || true

##############################################
# Stage 2: Install the application-
# Rebuilds quickly when you change wine commands
##############################################
FROM wine-base AS app-install

WORKDIR /app

# Copy installer files
COPY ["Simulation Installer.msi", "/app/"]
COPY ["setup.exe", "/app/"]

# Run the installer - modify this section as needed
# Using msiexec for the MSI file instead of setup.exe
RUN set -ex && \
    rm -rf /tmp/.X* && \
    Xvfb :0 -screen 0 1024x768x24 & \
    XVFB_PID=$! && \
    sleep 3 && \
    export DISPLAY=:0 && \
    echo "Running MSI installer..." && \
    timeout 300 wine msiexec /i "Z:\\app\\Simulation Installer.msi" /qn /norestart && \
    echo "Installer complete" && \
    sleep 5 && \
    kill $XVFB_PID 2>/dev/null || true

##############################################
# Stage 3: Final runtime image
##############################################
FROM wine-base AS runtime

# Copy installed application from app-install stage
COPY --from=app-install /root/.wine /root/.wine

# Create entrypoint script
RUN printf '#!/bin/bash\n\
set -e\n\
export HOME=/root\n\
export WINEPREFIX=/root/.wine\n\
export XDG_RUNTIME_DIR=/tmp/runtime-root\n\
mkdir -p $XDG_RUNTIME_DIR\n\
chmod 700 $XDG_RUNTIME_DIR\n\
\n\
INSTALL_DIR="/root/.wine/drive_c/Program Files/Planar Motor Inc/Planar Motor Simulation Tool"\n\
\n\
# Function to auto-click Start Simulation button with retries\n\
auto_start_simulation() {\n\
    echo "Waiting for app to load..."\n\
    sleep 10\n\
    \n\
    # Retry clicking multiple times to ensure simulation starts\n\
    for attempt in 1 2 3; do\n\
        echo "Click attempt $attempt/3..."\n\
        xdotool mousemove ${START_BTN_X:-400} ${START_BTN_Y:-480}\n\
        sleep 0.5\n\
        xdotool click 1\n\
        sleep 3\n\
        \n\
        # Check if UDP port 8888 is now listening (simulation started)\n\
        if grep -q ":22B8" /proc/net/udp 2>/dev/null; then\n\
            echo "Simulation started successfully (UDP 8888 listening)"\n\
            scrot /app/screenshot.png 2>/dev/null || true\n\
            return 0\n\
        fi\n\
    done\n\
    echo "Warning: Simulation may not have started correctly"\n\
    scrot /app/screenshot.png 2>/dev/null || true\n\
}\n\
\n\
if [ "$RUN_GUI" = "true" ] && [ -n "$DISPLAY" ]; then\n\
    # GUI mode - use host display\n\
    cd "$INSTALL_DIR"\n\
    exec wine "$INSTALL_DIR/Virtual PMC UI.exe" "$@"\n\
else\n\
    # Headless mode - run GUI in virtual framebuffer\n\
    echo "Starting headless mode with virtual display..."\n\
    rm -f /tmp/.X99-lock 2>/dev/null || true\n\
    Xvfb :99 -screen 0 1024x768x24 &\n\
    XVFB_PID=$!\n\
    export DISPLAY=:99\n\
    sleep 2\n\
    cd "$INSTALL_DIR"\n\
    echo "Launching Virtual PMC UI (headless)..."\n\
    wine "$INSTALL_DIR/Virtual PMC UI.exe" "$@" &\n\
    WINE_PID=$!\n\
    auto_start_simulation\n\
    # Keep running\n\
    wait $WINE_PID\n\
fi\n\
' > /usr/local/bin/run-simulator.sh && chmod +x /usr/local/bin/run-simulator.sh

ENTRYPOINT []
CMD ["/usr/local/bin/run-simulator.sh"]
