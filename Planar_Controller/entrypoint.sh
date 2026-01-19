#!/bin/bash
set -e

echo "=== Container Started ==="

# 1. Extract System Layout
echo "[Entrypoint] Running system layout extraction..."
python library/extract_system_layout.py

if [ -f "pmc_config.xml" ]; then
    echo "[Entrypoint] Layout extraction successful. pmc_config.xml found."
else
    echo "[Entrypoint] WARNING: pmc_config.xml not found after extraction attempt."
fi

# 2. Run Main Planner
echo "[Entrypoint] Starting XBot Planner..."
# Pass all arguments to xbot_planner.py
exec python xbot_planner_packml.py "$@"
