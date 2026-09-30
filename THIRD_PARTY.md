# Third-party dependencies and models

OpenZero's own source-available terms are in LICENSE. Those terms do not replace
the licences of upstream software, models, fonts, browser components or packages.

This release ZIP contains project source and static assets. It does not bundle
Ollama model weights, Python wheels, browser binaries or a Node installation.
Online installers fetch dependencies separately. Offline-bundle builders must
retain each downloaded component's licence/notices and review redistribution
rights before sharing their bundle.

Dependency declarations are in `openzero/requirements.txt` and the browser and
Node source directories. Principal optional upstream components include Ollama,
Brave/Chromium, Microsoft BitNet, Piper, Voicebox, Hugging Face Transformers and
PEFT. Their project licences apply to their own code and downloads.

Model selections have independent upstream model licences. An OpenZero runtime
template does not transfer ownership of model weights or broaden a model licence.
The default Ministral runtime-template edition uses upstream weights; operators
must consult its Hugging Face model card and upstream licence. Replacing a
download source with a mirror does not change redistribution obligations.
