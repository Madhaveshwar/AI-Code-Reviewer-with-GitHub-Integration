"""Launcher script to run the AI Code Reviewer application from the workspace root."""

from __future__ import annotations

import os
import subprocess
import sys

if __name__ == "__main__":
    app_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "app.py"
    )
    print(f"Starting Streamlit dashboard from: {app_path}")
    subprocess.run([sys.executable, "-m", "streamlit", "run", app_path])
