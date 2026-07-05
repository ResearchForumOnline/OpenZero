# CallChat Zero Bot Bridge

OpenZero can power a Matrix room agent for CallChat ZERO.

The bridge runs as a Matrix bot account, usually:

```text
@zero:callchat.org
```

CallChat sends approved room prompts to OpenZero through the local OpenAI-compatible API, then posts the answer back into Matrix. Voicebox can optionally turn command-triggered answers into Matrix audio attachments.

## Architecture

```text
CallChat / Matrix room
  -> @zero:callchat.org
  -> OpenZero /v1/chat/completions
  -> optional Voicebox /generate
  -> Matrix text or audio response
```

## Why This Matters

- CallChat gets a 24/7 room agent without paying for every reply.
- OpenZero becomes the reusable local AI brain for web chat, business tools, and Matrix rooms.
- Voicebox can give the agent a local open-source voice route.
- The same server can also support FrontDeskAgent workflows.
- Private rooms can stay local-first instead of silently using hosted cloud AI.

## Recommended OpenZero Settings

Use the local API:

```env
OPENZERO_LLM_URL=http://127.0.0.1:1024/v1/chat/completions
OPENZERO_MODEL=gemma4:e4b
OPENZERO_API_KEY=your-local-openzero-api-key-if-required
```

For CPU-first public room use, pick a compact model that stays responsive. If the owner's current Fable model is faster or funnier on the actual server, use that as `OPENZERO_MODEL`.

## Voicebox Settings

Optional:

```env
VOICEBOX_URL=http://127.0.0.1:17493
VOICEBOX_ENDPOINT=/generate
VOICEBOX_PROFILE=callchat-zero
VOICEBOX_LANGUAGE=en
```

Start with command-triggered voice:

```text
!zero voice Say CallChat ZERO is online.
```

Do not auto-speak every reply in public rooms until spam limits and room rules are proven.

## Bot Side Settings

The CallChat bot bridge should store secrets outside Git:

```env
MATRIX_HOMESERVER=https://callchat.org
MATRIX_USER_ID=@zero:callchat.org
MATRIX_USERNAME=zero
MATRIX_PASSWORD=stored-outside-git
CALLCHAT_BOT_ALLOWED_ROOMS=#zero-bot-lab:callchat.org
CALLCHAT_BOT_ALLOW_ALL_ROOMS=false
```

OpenZero only needs to expose the local API to the bot process. Do not expose the OpenZero Super Panel publicly without strong network controls.

## Guardrails

The agent can be witty, sarcastic, and entertaining, but public Matrix rooms need boundaries:

- no spam;
- no harassment, threats, hate, or doxxing;
- no account theft, malware, or break-in help;
- no Matrix signing keys, database passwords, OpenZero API keys, Shield secrets, or private source in prompts;
- no hidden long-term room memory;
- no silent failover from local OpenZero to a paid external backend.

## FrontDeskAgent Link

FrontDeskAgent already supports OpenZero and Voicebox. A complete self-hosted stack can share:

- OpenZero for local AI replies;
- Voicebox for local speech output;
- CallChat for secure Matrix rooms and user messaging;
- FrontDeskAgent for business intake, forms, phone/SMS/email workflows, and receptionist logic.

## Testing

From a CallChat room where the bot is invited:

```text
!zero help
!zero about
!zero status
!zero explain-shield
!zero voice OpenZero voice test complete.
```

If OpenZero is down, the bot should use a local fallback and clearly say the local brain is unavailable.
