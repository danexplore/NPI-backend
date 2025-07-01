#!/usr/bin/env python3
import subprocess
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
PYTHON_EXE = PROJECT_ROOT / ".venv" / ("Scripts" if os.name == 'nt' else "bin") / ("python.exe" if os.name == 'nt' else "python")

if __name__ == "__main__":
    subprocess.run([
        str(PYTHON_EXE), "-m", "uvicorn", 
        "api.main:app", 
        "--host", "0.0.0.0", 
        "--port", "8000", 
        "--workers", "4",
        "--log-level", "warning"
    ])
