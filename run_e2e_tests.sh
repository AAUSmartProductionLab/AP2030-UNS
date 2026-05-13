#!/bin/bash
cd "$(dirname "$0")/kg-bridge"
python3 -m pytest tests/test_e2e_real_stack.py -v -s -p no:launch_testing --tb=short
