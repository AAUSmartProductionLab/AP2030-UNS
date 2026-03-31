#!/usr/bin/env python3
"""Compatibility wrapper for the production planner runtime entrypoint."""

from .runtime.service_runner import *  # noqa: F401,F403


if __name__ == "__main__":
    main()
