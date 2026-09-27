# OpenZero 7.2.0

## Shipped

- Responsive conversation workspace, collapsible controls and clearer task status.
- Source improvement candidates with local model proposal generation, a source
  editor, actual diffs, recorded syntax/regression checks, reviewed apply and rollback.
- Training jobs, cancellation, metrics and hash-checked candidate artifact export.
- A real CPU adapter fixture and optional bounded local Hugging Face PEFT runner.
- Read-only policy verification and explicit reviewed migration of legacy policy.
- Authenticated workbench APIs with same-origin and JSON mutation checks.

## Verified

- 105 Python tests passed on Windows.
- Original and new JavaScript passed Node syntax checks.
- Workspace rendering and Training lab navigation were checked in a browser.
- A real candidate copied from OpenZero passed syntax checks and the 12-test
  workbench regression suite; it was not applied to production.
- The deployed Linux node completed a 250-step synthetic adapter job. Held-out
  MSE changed from 0.6266666674 to 0.000000228649, the base stayed unchanged and
  exported/reloaded predictions matched.
- Deployment preserved originals in a node backup and checked source hashes.

## Limits

The synthetic fixture is a small linear model, not an LLM or evidence of better
assistant intelligence. The optional Hugging Face training path is implemented
but was not executed because its training dependencies were not installed.
No 30B weights were trained, and no candidate replaces the active model automatically.

Source-candidate tests currently run the workbench regression suite plus Python
syntax checks. They are not full functional validation of arbitrary application
changes. Model proposal quality depends on the selected local model; live model
proposal quality was not benchmarked in this release.

TalkToAi Code receives the same training backend and usage guide in source.
Its existing installed 0.9.0 desktop binary is unchanged by this OpenZero release.

See [the workbench guide](WORKBENCH.md) and
[training setup](MODEL-TRAINING-WORKBENCH.md) for exact controls and limits.
