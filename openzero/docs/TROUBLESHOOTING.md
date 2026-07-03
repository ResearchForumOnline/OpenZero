# Troubleshooting

## Panel Does Not Open

Check the process:

```bash
pm2 list
pm2 logs openzero --lines 100
```

Check the port:

```bash
ss -lntp | grep 1024
```

## Ollama Not Ready

Check Ollama:

```bash
curl http://127.0.0.1:11434/api/tags
systemctl status ollama --no-pager
```

Use the Super Panel:

- Update Ollama;
- Repair Local Brain;
- Install Gemma 4 E2B/E4B;
- Refresh Models.

## Local Model Is Missing

Use the model install buttons or:

```bash
ollama pull gemma4:e4b
```

If Gemma 4 is not available on the machine's Ollama version, update Ollama first.

## ZeroThink Cannot Use OpenZero

Check:

1. OpenZero API key exists.
2. Key was copied into ZeroThink Neural Vault.
3. OpenZero is reachable from the ZeroThink server-side route.
4. The selected model is installed locally.
5. `/v1/chat/completions` returns with the key.

Do not rely on browser-supplied OpenZero URLs.

## Voicebox Offline

Check Voicebox separately:

```bash
curl http://127.0.0.1:17493/health
```

In OpenZero:

- set backend to `auto` if you want Piper fallback;
- click Check Voicebox;
- click List Profiles;
- confirm the URL and port.

## Moltbot Browser Issues

Check Node dependencies:

```bash
npm install express puppeteer --prefix moltbot
```

Restart the node:

```bash
pm2 restart all
```

## High CPU

Switch CPU profile to `compact`, reduce thread override, or use a smaller local model.

Recommended first move:

```text
OPENZERO_CPU_PROFILE=compact
OPENZERO_OLLAMA_THREADS=0
```

## API Key Lost

Rotate the OpenZero API key in the Super Panel. The old key will stop working.

