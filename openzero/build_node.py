import os
import subprocess
import sys

def build():
    print(">>> INITIALIZING OPENZERO SOVEREIGN BUILD ENGINE")
    
    # 1. Install PyInstaller if missing
    try:
        import PyInstaller
    except ImportError:
        print("> Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # 2. Define Build Command
    # --onefile: Bundle everything into a single executable
    # --name: Name of the output binary
    # --hidden-import: Ensure dynamic imports like socketio are included
    cmd = [
        "pyinstaller",
        "--onefile",
        "--name", "openzero_node",
        "--hidden-import", "engineio.async_drivers.threading",
        "--hidden-import", "socketio",
        "zero_core.py"
    ]

    print(f"> Executing: {' '.join(cmd)}")
    try:
        subprocess.check_call(cmd)
        print("\n[SUCCESS] Build Complete. Node binary located in 'dist/openzero_node'")
    except Exception as e:
        print(f"\n[ERROR] Build failed: {e}")

if __name__ == "__main__":
    build()
