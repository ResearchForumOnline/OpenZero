# FAQ

## Is OpenZero a chatbot?

It includes chat, but it is better understood as a local AI node with tools, local model routing, a panel, APIs, browser support, optional voice, and a bridge to ZeroThink.

## Does it require a GPU?

No. OpenZero is CPU-first by default. GPU acceleration can help, but the project is designed around practical local/server installs.

## What model should I start with?

Start with the default Gemma local lane installed by the script. Use smaller models on small machines.

## How does ZeroThink use OpenZero?

OpenZero creates a local API key. You paste that key into ZeroThink Neural Vault. ZeroThink can then route suitable work through your OpenZero node.

## Is Voicebox bundled?

No. Voicebox is optional and installed separately from https://github.com/jamiepine/voicebox. OpenZero can connect to it when it is running locally.

## Can premium code be hidden on GitHub?

No. Public GitHub code is viewable and copyable. Premium code should live outside this public repository as private modules, hosted services, private packages, compiled bundles, or signed extensions.

## Is OpenZero safe to expose publicly?

Do not expose the admin panel directly without strong protection. Treat it like operator software.

## Can OpenZero run offline?

Yes, through the offline bundle path. Build the bundle on a connected machine, move it to the target, then run `install_offline.sh`.

## What is Moltbot?

Moltbot is the local browser/page inspection helper used for visual and text-based web tasks.

## Where do I report security issues?

Use the security policy in [../SECURITY.md](../SECURITY.md).

