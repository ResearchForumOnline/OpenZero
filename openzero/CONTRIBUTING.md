# Contributing

Thanks for improving OpenZero.

Good contributions include:

- install fixes;
- docs improvements;
- CPU performance tuning;
- clearer error messages;
- safer defaults;
- UI polish;
- API examples;
- tests and diagnostics;
- platform compatibility notes.

## Before You Start

1. Open an issue or describe the change clearly.
2. Keep changes focused.
3. Avoid committing secrets.
4. Do not add premium/private source code to the public repo.
5. Keep public docs honest and practical.

## Development Checks

Python compile check:

```bash
python -m py_compile brain/app.py brain/openzero_config.py brain/voice_stack.py
```

Basic local run depends on your environment and installed services.

## Pull Request Notes

Include:

- what changed;
- why it changed;
- how it was tested;
- any compatibility impact;
- screenshots for UI changes;
- docs updates for user-facing behavior.

