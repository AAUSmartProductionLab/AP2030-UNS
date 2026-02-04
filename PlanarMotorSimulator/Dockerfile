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
RUN apt-get update && apt-get install -y xvfb cabextract procps && rm -rf /var/lib/apt/lists/*

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
if [ "$RUN_GUI" = "true" ] && [ -n "$DISPLAY" ]; then\n\
    cd "$INSTALL_DIR"\n\
    exec wine "$INSTALL_DIR/Virtual PMC UI.exe" "$@"\n\
else\n\
    cd "$INSTALL_DIR"\n\
    exec wine "$INSTALL_DIR/Dlls/VirtualPMC.exe" "$@"\n\
fi\n\
' > /usr/local/bin/run-simulator.sh && chmod +x /usr/local/bin/run-simulator.sh

ENTRYPOINT []
CMD ["/usr/local/bin/run-simulator.sh"]
