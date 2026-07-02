import datetime
import os
import subprocess
import sys
import threading
import time
from typing import Dict

import requests
from colorama import Fore, Style, init

from brain.openzero_config import env_bool, load_env, resource_profile, save_env_value, save_env_values
from brain.voice_stack import VoiceStack
from brain.integrity import ensure_integrity_state, integrity_status, seal_json
import hivemind.bridge as hive


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG = load_env(BASE_DIR)
VOICE = VoiceStack(BASE_DIR, CONFIG)
ensure_integrity_state(BASE_DIR)
LATEST_UPLOAD_CONTENT = ""
CHAT_HISTORY = []
MAX_HISTORY = 10
CONFIG_LOCK = threading.Lock()


ZERO_SYSTEM_PROMPT = """You are OpenZero, a sovereign AI operator for local and air-gapped systems.
Rules:
- Help users who know nothing about the setup.
- Keep the answer grounded in OpenZero only.
- Prioritize safe, local-first actions.
- Keep explanations complete and direct.
"""


def reload_config() -> Dict[str, str]:
    global CONFIG
    with CONFIG_LOCK:
        CONFIG = load_env(BASE_DIR)
        VOICE.refresh(CONFIG)
        seal_json(
            BASE_DIR,
            "node_state",
            {
                "active_model": CONFIG.get("ACTIVE_MODEL"),
                "comp_mode": CONFIG.get("COMP_MODE"),
                "hive_enabled": CONFIG.get("HIVE_MIND_ENABLED"),
                "voice_enabled": CONFIG.get("VOICE_ENABLED"),
                "paid_hive_enabled": CONFIG.get("PAID_HIVE_ENABLED"),
                "p_good_threshold": CONFIG.get("P_GOOD_THRESHOLD"),
            },
        )
        return dict(CONFIG)


def save_config(updates: Dict[str, str]) -> Dict[str, str]:
    global CONFIG
    with CONFIG_LOCK:
        CONFIG = save_env_values(BASE_DIR, updates)
        VOICE.refresh(CONFIG)
        seal_json(
            BASE_DIR,
            "node_state",
            {
                "active_model": CONFIG.get("ACTIVE_MODEL"),
                "comp_mode": CONFIG.get("COMP_MODE"),
                "hive_enabled": CONFIG.get("HIVE_MIND_ENABLED"),
                "voice_enabled": CONFIG.get("VOICE_ENABLED"),
                "paid_hive_enabled": CONFIG.get("PAID_HIVE_ENABLED"),
                "p_good_threshold": CONFIG.get("P_GOOD_THRESHOLD"),
            },
        )
    hive.init_hive(CONFIG)
    return dict(CONFIG)


def get_config() -> Dict[str, str]:
    with CONFIG_LOCK:
        return dict(CONFIG)


def execute_system_command(command: str) -> str:
    config = get_config()
    if "rm -rf /" in command:
        return "ACTION DENIED: ethical hazard."

    process = subprocess.run(command, shell=True, text=True, capture_output=True)
    exit_code = process.returncode
    output = process.stdout if exit_code == 0 else process.stderr

    sudo_password = config.get("SUDO_PASS", "")
    if exit_code != 0 and sudo_password and ("Permission denied" in output or exit_code == 1):
        payload = f"{sudo_password}\n{command}\n"
        retry = subprocess.run(["sudo", "-S", "bash"], input=payload, text=True, capture_output=True)
        if retry.returncode == 0:
            return retry.stdout.strip() or "[ROOT OVERRIDE SUCCESS]"
        return retry.stderr.strip()

    return output.strip() or "[Success: command executed with no output]"


def build_prompt(user_prompt: str) -> str:
    config = get_config()
    profile = resource_profile(config)
    history = "\n".join(f"{item['role'].upper()}: {item['content']}" for item in CHAT_HISTORY[-(MAX_HISTORY * 2):])
    upload_block = f"\nUPLOADED FILE DATA:\n{LATEST_UPLOAD_CONTENT[:12000]}" if LATEST_UPLOAD_CONTENT else ""
    return (
        f"{ZERO_SYSTEM_PROMPT}\n"
        f"Node tier: {profile['node_tier']} | RAM: {profile['ram_gb']} GB | Recommended model: {profile['recommended_model']}\n"
        f"P(G) threshold: {config.get('P_GOOD_THRESHOLD')} | Voice: {config.get('VOICE_ENABLED')}\n"
        f"{upload_block}\n\n"
        f"HISTORY:\n{history}\n\nUSER: {user_prompt}\nOPENZERO:"
    )


def brain_groq(prompt: str) -> str:
    config = get_config()
    api_key = config.get("GROQ_API_KEY", "")
    if len(api_key) < 10:
        return ""

    payload = {
        "model": config.get("ACTIVE_MODEL", "llama-3.3-70b-versatile"),
        "messages": [{"role": "system", "content": ZERO_SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception:
        return ""


def brain_local(prompt: str) -> str:
    config = get_config()
    profile = resource_profile(config)
    payload = {
        "model": config.get("ACTIVE_MODEL", profile["recommended_model"]),
        "prompt": build_prompt(prompt),
        "stream": False,
        "options": {"num_ctx": profile["context_window"]},
    }
    try:
        response = requests.post("http://127.0.0.1:11434/api/generate", json=payload, timeout=240)
        response.raise_for_status()
        return response.json()["response"]
    except Exception as error:
        return f"ALL SYSTEMS OFFLINE: {error}"


def route_response(user_prompt: str) -> str:
    config = get_config()
    comp_mode = config.get("COMP_MODE", "hybrid")
    active_model = config.get("ACTIVE_MODEL", "").lower()

    if comp_mode == "cloud":
        response = brain_groq(user_prompt)
        return response or brain_local(user_prompt)
    if comp_mode == "local":
        return brain_local(user_prompt)

    use_cloud = any(token in active_model for token in ["groq/", "gpt", "llama", "qwen", "compound"])
    if use_cloud:
        response = brain_groq(user_prompt)
        if response:
            return response
    return brain_local(user_prompt)


def run_daily_tasks() -> None:
    print(f"{Fore.CYAN}[TASK ENGINE] Running OpenZero health sweep...{Style.RESET_ALL}")
    tasks = {
        "Disk Check": "df -h | grep '/$'",
        "Memory Check": "free -m",
        "Failed Logins": "grep 'Failed password' /var/log/auth.log | wc -l",
        "Ports": "netstat -tuln",
        "OpenZero Services": "pm2 status",
    }
    report_lines = [f"OPENZERO DAILY REPORT // {datetime.datetime.now().isoformat()}"]
    for label, command in tasks.items():
        report_lines.append(f"\n--- {label} ---")
        report_lines.append(execute_system_command(command))

    report = "\n".join(report_lines)
    report_path = os.path.join(BASE_DIR, "daily_report.log")
    with open(report_path, "a", encoding="utf-8") as handle:
        handle.write(report + "\n" + ("=" * 60) + "\n")
    print(report)


def setup_cron() -> None:
    script_path = os.path.abspath(__file__)
    cron_line = f"0 8 * * * /usr/bin/python3 {script_path} --task daily"
    try:
        existing = subprocess.check_output("crontab -l", shell=True, stderr=subprocess.DEVNULL, text=True)
        if script_path in existing:
            print(f"{Fore.YELLOW}[TASK ENGINE] Daily tasks are already scheduled.{Style.RESET_ALL}")
            return
    except Exception:
        pass

    os.system(f'(crontab -l 2>/dev/null; echo "{cron_line}") | crontab -')
    print(f"{Fore.GREEN}[TASK ENGINE] Daily tasks scheduled for 08:00.{Style.RESET_ALL}")


def show_status() -> None:
    config = get_config()
    profile = resource_profile(config)
    hive_state = hive.status_snapshot(config)
    voice_state = VOICE.status()
    integrity = integrity_status(BASE_DIR)

    print(f"{Fore.GREEN}OpenZero 5.4 status{Style.RESET_ALL}")
    print(f"  Domain: {config.get('OPENZERO_DOMAIN')}")
    print(f"  Active model: {config.get('ACTIVE_MODEL')}")
    print(f"  Recommended model: {profile['recommended_model']}")
    print(f"  RAM tier: {profile['node_tier']} ({profile['ram_gb']} GB)")
    print(f"  Context window: {profile['context_window']}")
    print(f"  Hive: {'ONLINE' if hive_state['hive_enabled'] else 'OFFLINE'}")
    print(f"  Voice: {'ON' if voice_state['voice_enabled'] else 'OFF'}")
    print(f"  Paid hive: {config.get('PAID_HIVE_ENABLED')}")
    print(f"  P(G): {config.get('P_GOOD_THRESHOLD')}")
    print(f"  OZ token CA: {config.get('OZ_TOKEN_CA')}")
    print(f"  Solana address: {config.get('SOLANA_ADDRESS')}")
    print(f"  Integrity: {integrity['manifest']['status']} / ethics={integrity['ethics']['status']}")


def heartbeat_loop() -> None:
    while True:
        try:
            hive.refresh_registration(get_config())
        except Exception:
            pass
        time.sleep(300)


def handle_meta_command(user_input: str) -> bool:
    global LATEST_UPLOAD_CONTENT

    config = get_config()
    parts = user_input.split(" ", 1)
    command = parts[0].lower()
    argument = parts[1].strip() if len(parts) > 1 else ""

    if command in {"!help", "!?"}:
        print("Commands: !status, !tasks, !mode <local|cloud|hybrid>, !hive on/off/status, !setfee <amount>, !upload <path>, !voice on/off/status, !listen <audio-file>, !speak <text>, !paid on/off, !wallet <sol-address>, !pg <0.1>, !donate")
        return True
    if command == "!status":
        show_status()
        return True
    if command == "!tasks":
        setup_cron()
        return True
    if command == "!mode":
        if argument.lower() in {"local", "cloud", "hybrid"}:
            save_config({"COMP_MODE": argument.lower()})
            print(f"{Fore.GREEN}[SYSTEM] Computation mode set to {argument.upper()}.{Style.RESET_ALL}")
        else:
            print("Usage: !mode <local|cloud|hybrid>")
        return True
    if command == "!hive":
        if argument.lower() == "on":
            save_config({"HIVE_MIND_ENABLED": "true"})
            hive.set_hive_state(True, get_config())
            print(f"{Fore.GREEN}[HIVE MIND] OpenZero lattice enabled.{Style.RESET_ALL}")
        elif argument.lower() == "off":
            save_config({"HIVE_MIND_ENABLED": "false"})
            hive.set_hive_state(False, get_config())
            print(f"{Fore.YELLOW}[HIVE MIND] OpenZero lattice disabled.{Style.RESET_ALL}")
        else:
            state = hive.status_snapshot(get_config())
            print(state)
        return True
    if command == "!setfee":
        try:
            fee = float(argument)
            save_config({"FEE_OZ_COINS": str(fee), "FEE_ZERO_COINS": str(fee)})
            hive.set_compute_fee(fee, get_config())
            print(f"{Fore.GREEN}[HIVE MIND] Compute fee set to {fee} OZ.{Style.RESET_ALL}")
        except ValueError:
            print("Usage: !setfee <amount>")
        return True
    if command == "!upload":
        if not argument:
            print("Usage: !upload <path>")
            return True
        if os.path.exists(argument):
            with open(argument, "r", encoding="utf-8", errors="ignore") as handle:
                LATEST_UPLOAD_CONTENT = handle.read()
            print(f"{Fore.GREEN}[CORTEX] Indexed {os.path.basename(argument)} into short-term memory.{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}File not found: {argument}{Style.RESET_ALL}")
        return True
    if command == "!voice":
        if argument.lower() == "on":
            save_config({"VOICE_ENABLED": "true", "VOICE_TTS_ENABLED": "true"})
            print(f"{Fore.GREEN}[VOICE] Local voice enabled.{Style.RESET_ALL}")
        elif argument.lower() == "off":
            save_config({"VOICE_ENABLED": "false", "VOICE_TTS_ENABLED": "false"})
            print(f"{Fore.YELLOW}[VOICE] Local voice disabled.{Style.RESET_ALL}")
        else:
            print(VOICE.status())
        return True
    if command == "!listen":
        result = VOICE.transcribe_file(argument)
        print(result)
        if result.get("status") == "success" and result.get("text"):
            CHAT_HISTORY.append({"role": "user", "content": result["text"]})
        return True
    if command == "!speak":
        result = VOICE.speak_text(argument)
        if result.get("status") == "success":
            hive.broadcast_voice_event(argument, get_config())
        print(result)
        return True
    if command == "!paid":
        if argument.lower() in {"on", "off"}:
            save_config({"PAID_HIVE_ENABLED": "true" if argument.lower() == "on" else "false"})
            print(f"{Fore.GREEN}[PAID HIVE] Set to {argument.lower()}.{Style.RESET_ALL}")
        else:
            print(f"PAID_HIVE_ENABLED={config.get('PAID_HIVE_ENABLED')}")
        return True
    if command == "!wallet":
        if argument:
            save_config({"SOLANA_ADDRESS": argument, "PAID_HIVE_ADDRESS": argument})
            print(f"{Fore.GREEN}[WALLET] Solana address updated.{Style.RESET_ALL}")
        else:
            print("Usage: !wallet <solana-address>")
        return True
    if command == "!pg":
        try:
            threshold = max(0.1, min(float(argument), 0.99))
            save_config({"P_GOOD_THRESHOLD": f"{threshold:.2f}"})
            print(f"{Fore.GREEN}[ETHICS] P(G) threshold set to {threshold:.2f}.{Style.RESET_ALL}")
        except ValueError:
            print("Usage: !pg <0.10-0.99>")
        return True
    if command == "!donate":
        print(f"\n{Fore.GREEN}--- SUPPORT OPENZERO RESEARCH ---{Style.RESET_ALL}")
        print(f"Solana (SOL): {config.get('SOLANA_ADDRESS')}")
        print(f"$OZ Token CA: {config.get('OZ_TOKEN_CA')}")
        print("Thank you for supporting the OpenZero lattice.\n")
        return True
    if command.startswith("!"):
        print(execute_system_command(user_input[1:]))
        return True
    return False


def main() -> None:
    init(autoreset=True)
    reload_config()
    hive.init_hive(get_config())

    if len(sys.argv) > 2 and sys.argv[1] == "--task" and sys.argv[2] == "daily":
        run_daily_tasks()
        return

    threading.Thread(target=heartbeat_loop, daemon=True).start()

    print(f"{Fore.RED}███████ ███████ ██████  ██████{Style.RESET_ALL}")
    print(f"{Fore.WHITE}OPENZERO 5.4 // SOVEREIGN NODE ACTIVE{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}Local-first. Air-gapped ready. Hive aware. Voice optional.{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Type !help for commands.{Style.RESET_ALL}\n")

    while True:
        try:
            user_input = input(f"{Fore.RED}openzero@node:~$ {Style.RESET_ALL}").strip()
            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit"}:
                break
            if handle_meta_command(user_input):
                continue

            CHAT_HISTORY.append({"role": "user", "content": user_input})
            del CHAT_HISTORY[:- (MAX_HISTORY * 2)]

            cached = hive.search_hive_knowledge(user_input, minimum_p_good=float(get_config().get("P_GOOD_THRESHOLD", "0.10")))
            if cached and env_bool(get_config(), "HIVE_MIND_ENABLED"):
                print(f"\n{Fore.MAGENTA}[HIVE CACHE]{Style.RESET_ALL} {cached}\n")

            response = route_response(user_input)
            print(f"\n{Fore.GREEN}[OPENZERO]{Style.RESET_ALL} {response}\n")
            CHAT_HISTORY.append({"role": "assistant", "content": response})
            del CHAT_HISTORY[:- (MAX_HISTORY * 2)]

            if env_bool(get_config(), "VOICE_ENABLED") and env_bool(get_config(), "VOICE_TTS_ENABLED"):
                VOICE.speak_text(response[:400])
            hive.broadcast_to_hive(user_input, response, get_config(), metadata={"interface": "cli"})
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
