"""Read-only node independence configuration report. No network requests or writes."""
import argparse
import json
from pathlib import Path

from brain.model_routing import automatic_repair_allowed, select_model_route
from brain.openzero_config import env_bool, load_env


def independence_report(config):
    route = select_model_route(config.get("COMP_MODE", "local"), config.get("ACTIVE_MODEL", ""))
    hive_configured = bool(str(config.get("OPENZERO_HIVE_URL", "")).strip() or str(config.get("OPENZERO_HIVE_MIRRORS", "")).strip())
    hive_enabled = env_bool(config, "HIVE_MIND_ENABLED") and hive_configured
    loopback = str(config.get("OPENZERO_BIND_HOST", "127.0.0.1")).strip().lower() in {"127.0.0.1", "localhost", "::1"}
    return {
        "schema": "openzero-node-independence.v1",
        "evidence": "configuration-only; no network, inference or installed-model probe performed",
        "model_route": route,
        "cloud_model_route_selected": route == "cloud",
        "legacy_remote_hive_enabled": hive_enabled,
        "legacy_remote_lookup_enabled": hive_enabled and env_bool(config, "OPENZERO_HIVE_REMOTE_LOOKUP_ENABLED"),
        "automatic_runtime_repair_enabled": automatic_repair_allowed(config),
        "loopback_binding_configured": loopback,
        "public_binding_opt_in": env_bool(config, "OPENZERO_ALLOW_PUBLIC_BIND"),
        "owner_account_required": False,
        "owner_coordinator_required": False,
        "status": "configured-local" if route == "local" and not hive_enabled else "optional-remote-services-selected",
        "limits": [
            "Local inference still requires an installed model, runtime and dependencies.",
            "Web tools, voice services, optional direct peers, cloud routes and software downloads have their own network requirements.",
            "Disabling automatic runtime repair prevents model-error repair jobs; it is not an operating-system network firewall.",
            "This report does not inspect or export private peer state, API keys, prompts, endpoints or user records.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parent, help="Existing node directory containing .env")
    args = parser.parse_args()
    print(json.dumps(independence_report(load_env(str(args.directory.resolve()))), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
