import subprocess
import os
from dotenv import load_dotenv

load_dotenv()
SUDO_PASS = os.getenv("SUDO_PASS", "1234ZERO")

def execute_bash(command):
    """
    Armored Execution Engine.
    Uses stdin piping to flawlessly handle LLM newlines, quotes, and && chains as root.
    """
    command = command.strip()
    
    # 1. Try as standard user first
    process = subprocess.run(command, shell=True, text=True, capture_output=True)
    exit_code = process.returncode
    output = process.stdout if exit_code == 0 else process.stderr
    
    # 2. AUTO-ESCALATION: If permission denied or exit 1
    if exit_code != 0 and ("Permission denied" in output or exit_code == 1):
        
        # THE FIX: We pass the password on line 1, and the AI's raw command on the next lines.
        # This completely bypasses the need for quotes or escaping.
        payload = f"{SUDO_PASS}\n{command}\n"
        
        # Execute 'sudo bash' directly, feeding it the payload
        retry = subprocess.run(
            ["sudo", "-S", "bash"], 
            input=payload, 
            text=True, 
            capture_output=True
        )
        
        if retry.returncode == 0:
            return f"[ROOT OVERRIDE SUCCESS]\n{retry.stdout.strip()}", 0
        else:
            return retry.stderr.strip(), retry.returncode

    if not output.strip():
        output = "[Success: Command executed with no output]"
        
    return output.strip(), exit_code
