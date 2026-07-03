# Offline Release

The offline release path is for operators who want an OpenZero machine that can keep running after it is disconnected from the internet.

## What The Bundle Contains

The offline bundle may include:

- OpenZero source tree;
- Python wheelhouse;
- local Node.js runtime archive;
- PM2 package tarball;
- Moltbot node modules;
- Ollama binary;
- local Ollama model store;
- Chrome `.deb` when available;
- optional voice wheels.

Because model weights are included, the bundle is usually large.

## Build On A Connected Node

```bash
cd ~/openzero
chmod +x build_offline_release.sh
./build_offline_release.sh
```

With optional voice wheels:

```bash
./build_offline_release.sh --with-voice
```

## Move To Offline Target

Copy:

```text
openzero_offline_release.tar.gz
openzero_offline_release.tar.gz.sha256
```

Use USB, local LAN, or another secure transfer route.

## Install Offline

```bash
tar -xzf openzero_offline_release.tar.gz
cd openzero_offline_release
chmod +x install_offline.sh
./install_offline.sh
```

With optional voice wheels:

```bash
./install_offline.sh --voice
```

## Important Reality Check

The offline installer does not fetch internet packages. The offline target still needs a sane Linux base with Python 3, tar, and standard system libraries.

Voicebox is not bundled by default. If you want Voicebox offline, package it separately according to Voicebox's own instructions.

