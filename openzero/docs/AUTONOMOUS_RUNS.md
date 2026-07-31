# Bounded Autonomous Runs

OpenZero can continue an authorized task after the browser disconnects or the
brain process restarts. This is durable continuation, not unlimited authority.
Every run has a fixed objective, explicit budgets, checkpoints, a redacted
trace, and operator-controlled stop/revoke controls.

## Safety Invariants

- The original objective is included in every model step. A tool result is a
  checkpoint, never a replacement user message.
- Session histories are isolated by Socket.IO session. Tool output is not
  inserted as a fabricated `USER` or `ASSISTANT` turn.
- Model calls, tool proposals, steps, elapsed time, and consecutive errors are
  bounded. User-supplied values are clamped to hard limits.
- A run cannot create, fork, or schedule another autonomous run. Root worker
  concurrency is configurable from one to four. Local model inference remains
  serialized so concurrent tool work cannot multiply model memory use.
- Future-action prose such as "I will now click" is not completion. OpenZero
  retries until it receives an executable action or a factual final result.
- An explicit browser objective cannot complete from a refusal or unsupported
  factual claim. A successful browser inspection is required, and a requested
  click/type requires separately recorded post-action evidence.
- Raw shell, remote commands, remote uploads, deletion, audible speech, and
  writes to persistent-access/startup locations pause before execution.
- A paused consequential action needs a fresh, short-lived confirmation tied
  to its exact SHA-256 fingerprint. Confirmation is consumed once.
- `stop` halts at the next safe boundary. `revoke` is permanent for that run and
  clears pending approval authority.
- Autonomous results stay local. They are not spoken or published to Hive
  automatically.

## Durable State

The runtime stores operator-owned state under:

```text
.runtime/autonomous-runs/
  runs/<run-id>.json
  traces/<run-id>.jsonl
```

Checkpoint writes use a temporary file, `fsync`, and atomic replacement. A
process restart changes an in-progress run to `interrupted`; an eligible
`auto_resume` run is then claimed by a bounded worker.

OpenZero records a tool as in flight before executing it. An interrupted
read-only action can be checked again automatically. An interrupted mutation is
marked `interrupted_action`, disables automatic resume, and requires operator
review because its outcome may be ambiguous. Consequential actions never gain a
second execution from an already-consumed confirmation.

Prompts, checkpoints, tool summaries, errors, and traces pass through credential
redaction before being persisted. Known API-key, token, password, authorization,
cookie, URL credential, and private-key patterns are replaced with
`[REDACTED]`. Traces have a fixed byte limit and record
`trace_limit_reached` when full.

Because secrets are not persisted, a task that genuinely needs a secret after a
restart must receive it again through an appropriate operator-controlled
channel. This is an intentional recovery boundary.

## API Authentication

All run-control endpoints require either:

- a direct loopback request without proxy forwarding headers; or
- `Authorization: Bearer <OpenZero API key>` when the local API is enabled.

The API is designed for a Super Panel, local CLI, or trusted local integration.

## Create A Run

```http
POST /api/agent/runs
Content-Type: application/json

{
  "objective": "Inspect the local service, repair safe files, and verify health.",
  "agent_mode": "terminal",
  "comp_mode": "local",
  "autonomy_profile": "standard",
  "auto_resume": true,
  "budgets": {
    "max_steps": 12,
    "max_model_calls": 12,
    "max_tool_calls": 10,
    "max_elapsed_seconds": 1800,
    "max_consecutive_errors": 3
  }
}
```

The response is `202 Accepted` and includes:

- `worker_started`;
- the public `run` state;
- `links` for status, stop, resume, revoke, and approval.

Hard caps are 32 steps, 32 model calls, 24 tool calls, four elapsed hours, and
five consecutive errors. Lower positive values are supported.

`autonomy_profile` is immutable for a run:

- `standard` preserves the original skill budgets.
- `ultra` doubles selected skill budgets while retaining the same global hard
  caps, tool allowlists, confirmations, redaction, stop/revoke behavior, and
  anti-recursion controls.

Moltbot actions use a fresh `snapshot_id` and inspected element IDs. Every
successful action invalidates the old snapshot and returns a new inspection.

Every Moltbot navigation, inspection, and action is also bound to the owning
32-character run ID. Browser runs are serialized around the shared headless
page. A click or type counts as completed only when its post-action inspection
shows an observable state change, the final URL remains compatible with the
objective, and the inspected element label matches an explicit click target.
A dispatched action with no observable change ends as an error and is never
replayed automatically.

## Inspect Runs

```http
GET /api/agent/runs
GET /api/agent/runs/<run-id>?trace_limit=50
```

The list response includes `active_count` and `max_concurrent_workers`. A single
run response includes its redacted objective, budget use, pending action,
checkpoint result, bounded trace tail, and control links.

Common states are:

- `queued`
- `running`
- `interrupted`
- `interrupted_action`
- `awaiting_confirmation`
- `paused_budget`
- `stopping`
- `stopped`
- `completed`
- `error`
- `revoked`

## Stop, Resume, And Revoke

```http
POST /api/agent/runs/<run-id>/stop
POST /api/agent/runs/<run-id>/resume
POST /api/agent/runs/<run-id>/revoke
```

`resume` can carry a new explicit `budgets` object. This is how an operator
deliberately extends a budget-paused run. It cannot resume a completed or
revoked run.

## Fresh Confirmation

When a model proposes a consequential action, OpenZero returns
`awaiting_confirmation` and a `pending_action` object. The action has not run.
After reviewing its action, reason, summary, and fingerprint:

```http
POST /api/agent/runs/<run-id>/approve
Content-Type: application/json

{
  "fingerprint": "<exact pending-action fingerprint>",
  "ttl_seconds": 300
}
```

Approval lasts for at most ten minutes, is valid for that exact fingerprint,
and is consumed by the first matching proposal. If the model changes the action,
OpenZero pauses again for a new confirmation.

For Moltbot actions, OpenZero reserves that run's browser snapshot during the
same short confirmation window. Approval resumes the exact run and snapshot;
an expired pending action releases the browser and must be inspected again.

Server-side Moltbot is separate from the Brave Tab Pilot extension. An objective
that explicitly names Brave, Tab Pilot, or an existing/current tab pauses with
`tab_pilot_bridge_unavailable` until a live extension task/evidence bridge is
available. It is never reported as completed from Moltbot-only evidence.

## Deterministic Validation

From the `openzero` directory:

```bash
python -m unittest discover -s tests -p "test_autonomous_runtime.py" -v
```

The tests cover restart recovery, explicit budgets, durable stop/revoke,
single-use confirmation, consequential-action policy, self-replication denial,
secret redaction, bounded traces, session-history isolation contracts, and the
authenticated API route surface.
