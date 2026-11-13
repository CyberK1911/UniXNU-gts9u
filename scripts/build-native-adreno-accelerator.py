#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

target = Path(__file__).resolve().parent / 'build-adreno740-accelerator.py'
if not target.is_file():
    target = Path(__file__).resolve().parents[1] / 'scripts/build-adreno740-accelerator.py'
sys.exit(subprocess.run([sys.executable, str(target)] + sys.argv[1:]).returncode)
