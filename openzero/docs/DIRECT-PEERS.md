# Direct peers without a main node — OpenZero 7.3

Every installation can run alone or exchange manually published text notes with
other independently owned OpenZero installations. The same Flask service runs
on every node. There is no bootstrap server, coordinator, public membership
directory, automatic discovery, hosted login, database service or TalkToAI
backend in this protocol. Local work does not need any peer to be available.

This is a bounded direct note-exchange implementation, not distributed LLM
inference, consensus, automatic weight sharing or remote command execution.
The source and training workbenches remain local owner-reviewed operations.

## Start with local operation

Peer exchange is disabled by default. Leave it disabled to make no peer network
requests and reject inbound exchange. Models already installed on your machine,
local tools, notes and workbenches keep working without a peer network. Optional
web search, cloud APIs and downloading dependencies or models need their own
network access.

Open the local Super Panel and use **Direct peers — no main node** in settings.
Settings operations require the existing owner request boundary: a direct
loopback request with a loopback Host, or the administrator API bearer key.
Cross-origin browser requests are rejected. A peer receive key is never an
administrator key.

## Connect two independently owned nodes

1. On node B, create its dedicated **receive key**, then enable peer exchange.
   The full key is shown once. B stores a SHA-256 digest of its inbound key.
2. On node A, add B's origin and receive key. Adding the peer saves configuration
   locally and sends no request.
3. Enable peer exchange on A. Prepare a note, explicitly approve sharing and
   review the privacy-filtered text shown in **My published notes**.
4. Choose **Exchange latest batch with this peer**. A sends its latest published notes to B
   and receives B's latest published notes directly.
5. Read received notes in the review inbox. They remain untrusted text: they
   never become commands, settings, prompts, training data or published notes
   automatically. Nothing received is automatically forwarded.

To let B initiate exchange with A, repeat the setup with A's own receive key.
You decide the graph of peers. No machine is the primary or required node.

## Network setup

Use an HTTPS origin such as `https://node.example` with no path, credentials,
query string or fragment. TLS validation stays enabled and redirects are not
followed. OpenZero's production service continues to bind to loopback. Operators
can expose only `/api/peers/exchange` through an HTTPS reverse proxy while
keeping all administrative, model and tool routes private.

Alternatively, tunnel a second node's loopback service over SSH:

```sh
ssh -N -L 2024:127.0.0.1:1024 your-account@your-node
```

On the first node, configure `http://127.0.0.1:2024` as the second node's origin.
Remote plain HTTP and metadata/link-local destinations are rejected. There is
no automatic NAT traversal. HTTPS, firewall configuration and private tunnel
setup remain the operators' responsibility.

## API contract

All management routes require owner authority and JSON for writes:

| Route | Purpose |
|---|---|
| `GET /api/peers/status` | Local status, reviewed configuration and recent notes; no keys |
| `POST /api/peers/config` | `{ "enabled": true }` or `false` |
| `POST /api/peers/key` | `{ "revoke": false }` creates/rotates a dedicated receive key; `true` revokes |
| `POST /api/peers/add` | `{ "label": "My node", "origin": "https://node.example", "token": "recipient receive key" }` |
| `POST /api/peers/remove` | `{ "id": "configured peer ID" }` |
| `POST /api/peers/publish` | `{ "title": "Title", "text": "Reviewed note", "consent": true }` |
| `POST /api/peers/sync` | `{ "consent": true, "peer_ids": ["peer ID"] }`; optional `note_ids` selects older notes |
| `POST /api/peers/delete` | `{ "id": "note digest" }` removes a locally published note |
| `POST /api/peers/inbox/delete` | Removes a received note locally |

The remote endpoint is `POST /api/peers/exchange`. It accepts only a dedicated
`Authorization: Bearer ozpeer_…` receive key while exchange is enabled. Browser
Origin/cross-site requests are rejected even if they present such a key.

Request:

```json
{"schema":"openzero-peer-notes-v1","events":[]}
```

Response contains the same schema, a `received` count and an `events` list. Each
event contains exactly `id`, `content` and `created_at`. Content contains exactly
`schema`, `kind: "note"`, `title` and `text`. The event ID is the SHA-256 digest
of canonical UTF-8 JSON content. This detects content changes and duplicates;
it does **not** prove truth, authorship or trustworthiness. Authentication proves
possession of the receive key. Notes are not signed public research papers.

## Bounds and privacy

- At most 8 explicitly configured peers, 12 notes per exchange and 256 notes in
  each local published/inbox collection. Latest 12 published notes are used by
  default, with fewer notes when the 128,000-byte UTF-8 wire budget is full.
  **Exchange this exact note with all my peers** selects an older displayed
  note; the API can select particular older note IDs beyond the latest 40 shown
  in the panel. Total local peer state is capped at 6,000,000 bytes.
- At most 8,000 text characters, 160 title characters and 16,000 bytes per note.
  The existing public-sharing filter may further redact/truncate outgoing text.
- Requests/responses are capped at 128,000 bytes. Outbound calls use bounded
  connect/read timeouts, a six-second elapsed guard during one-byte response
  streaming and a single sync operation at a time. This guard is not a strict
  end-to-end deadline: DNS resolution and response headers are subject to the
  underlying network library and host configuration. Incoming authenticated
  exchanges are limited to 120 per minute.
- Receive-key rotation invalidates the earlier key. Disabling exchange prevents
  future requests and subsequent fan-out requests; a request already sent cannot
  be recalled. Deleting a published note cannot delete someone else's received
  copy.
- Keys are never included in status, note content, UI lists or returned network
  errors. Runtime state is kept in `.runtime/peer-mesh/mesh.json`, excluded from
  Git and public release archives. The file uses POSIX mode 0600; outbound peer
  credentials are stored locally in that file. This is **not encryption at
  rest**. Windows installations inherit their directory ACLs; protect your
  account and disk. Filesystem owners can read their own runtime credentials.
- Obvious bearer/credential/token patterns and the existing public-sharing
  privacy filter are applied before publication. No automatic filter can promise
  to identify every secret: review the displayed note and never publish private
  datasets, login details or personal information.
- The review inbox is separate from local model memory, training and agent tool
  execution. Only deliberately prepared local notes are sent to other nodes.

## Legacy migration

The former vendor Hive URL is removed from effective runtime configuration,
including the mirror list. A node with no remaining operator-specified legacy
endpoint becomes local-only; its actual `.env` file is not rewritten simply by
loading it. Custom operator-owned legacy services remain available under an
advanced compatibility section. Old queued events can replay only to endpoints
still present in the operator's current configuration.

No private Hive HQ server or database is required or included in this release.
Legacy Hive and direct peer notes are separate protocols.

## Verification

`tests/test_peer_mesh.py` includes a real HTTP loopback exchange between two
separate Flask node fixtures, content-digest and duplicate checks, disabled and
revoked key behavior, authorization separation, cross-origin/DNS-rebinding
request boundaries, caps, failure isolation and interrupted fan-out. Fixtures
use synthetic text and temporary state. They do not connect to user servers or
read an installed node's private runtime profile.
