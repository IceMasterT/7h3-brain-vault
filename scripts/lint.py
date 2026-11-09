#!/usr/bin/env python3
"""Vault health check. Kept for compatibility: same as `brain.py health`.
Usage: lint.py [--brief] [--write] [--json] [--strict]"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from brain import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["health", *sys.argv[1:]]))
