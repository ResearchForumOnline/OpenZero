import requests
import json
import re
import os
from shell_core import execute_bash, execute_persistent
from dotenv import load_dotenv

load_dotenv()

# Lock onto the local Gemma 4 edge engine by default.
ACTIVE_MODEL = os.getenv("ACTIVE_MODEL", "gemma4:e4b")
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

# Load the DevOps Frameworks into the System Prompt so the AI is smart
try:
    with open("/home/zero/openzero/knowledge/agent_frameworks.txt", "r") as f:
        FRAMEWORKS = f.read()
except:
    FRAMEWORKS = "No external frameworks loaded."

SYSTEM_PROMPT = f"""[ROOT SYSTEM OVERRIDE]
You are OpenZero, an autonomous Dev-Ops AI Agent with root access to a Linux OS.
You operate on a recursive ReAct loop. You do not ask the user to run commands; YOU run them.

AVAILABLE TOOLS:
1. <bash>sudo your_command_here</bash> (For terminal, file creation, system config)
2. <tmux session_name>your_command</tmux> (ONLY for background servers/bots)

CRITICAL RULES:
- You run as the 'zero' user. You MUST use 'sudo' for directories like /var/www/ or apt installs.
- NEVER chain sudo commands with '&&'. Do them one by one.
- You MUST wrap your commands in the XML tags. If you do not, the system will crash.

EXAMPLE CONVERSATION:
User: Create a folder in /var/www/ called my_test.
OpenZero: <bash>sudo mkdir -p /var/www/my_test</bash>
System: [Command executed successfully]
OpenZero: <bash>sudo chown -R zero:zero /var/www/my_test</bash>
System: [Command executed successfully]
OpenZero: <bash>echo "Hello" > /var/www/my_test/index.html</bash>

LOADED FRAMEWORKS:
{FRAMEWORKS}
"""

def call_llm(prompt):
    """Calls Ollama natively."""
    payload = {
        "model": ACTIVE_MODEL,
        "prompt": prompt,
        "system": SYSTEM_PROMPT,
        "stream": False
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        if response.status_code == 200:
            return response.json().get("response", "")
        return f"[ERROR] Engine returned status code {response.status_code}"
    except Exception as e:
        return f"[ERROR] Failed to connect to local brain: {str(e)}"

def process_agent_logic(user_input, history=""):
    """
    THE TRUE AUTONOMOUS LOOP.
    Feeds errors back into the LLM up to 5 times until success is achieved.
    """
    MAX_LOOPS = 5
    current_prompt = user_input
    full_output_log = ""
    
    for loop_count in range(1, MAX_LOOPS + 1):
        # 1. AI Thinks
        ai_response = call_llm(current_prompt)
        full_output_log += f"\n**[ZERO - ITERATION {loop_count}]**\n{ai_response}\n"
        
        # 2. Parse TMUX (Background Processes)
        tmux_match = re.search(r'<tmux\s+(.*?)>(.*?)</tmux>', ai_response, re.DOTALL)
        if tmux_match:
            session_name = tmux_match.group(1).strip()
            command = tmux_match.group(2).strip()
            full_output_log += f"\n[SPAWNING BACKGROUND PROCESS: {session_name}] -> {command}\n"
            
            output, code = execute_persistent(session_name, command)
            full_output_log += f"**[TERMINAL RESULT]**\n{output}\n"
            
            if code != 0:
                current_prompt = f"The background task failed to start:\n{output}\nCorrect your syntax and try again using the <tmux> tag."
                continue
            else:
                current_prompt = f"Background task '{session_name}' started successfully.\nWhat is the next step? If done, summarize for the user."
                continue

        # 3. Parse BASH (Standard Commands)
        bash_match = re.search(r'<bash>(.*?)</bash>', ai_response, re.DOTALL)
        if bash_match:
            command = bash_match.group(1).strip()
            full_output_log += f"\n[EXECUTING COMMAND]: {command}\n"
            
            output, code = execute_bash(command)
            full_output_log += f"**[TERMINAL RESULT]**\n{output}\n"
            
            if code != 0:
                # FATAL: Feed error back to AI invisibly
                current_prompt = f"Your previous command FAILED with exit code {code}.\nOutput: {output}\nAnalyze what went wrong, and issue a NEW <bash> command to fix it. Do not apologize."
                continue
            else:
                # SUCCESS: Tell AI it worked, ask what's next
                current_prompt = f"Command SUCCEEDED.\nOutput: {output}\nIf the task is complete, tell the user 'TASK COMPLETE' and summarize. If more steps are needed, issue the next <bash> command."
                continue
                
        # 4. If no tags deployed, AI is just talking. Break the loop and return to the web UI.
        break

    if loop_count == MAX_LOOPS:
        full_output_log += "\n[SYSTEM ALERT] Maximum autonomous iterations reached. Task paused to prevent infinite recursion."

    return full_output_log
