[中文 README](README.zh-CN.md)

# Gokumoku

Gokumoku is a practical hybrid Gomoku engine. It combines first-player proof data, strong general-purpose search, and a white-side defensive decision layer. The project also provides a browser play interface, an automated match framework, and a terminal dashboard (TUI) for human play, local evaluation, and iterative tuning.

## Engine Architecture

Gokumoku uses different decision strategies for black and white, because the two sides face fundamentally different problems.

**Black** combines two sources of strength: proof-database continuations from a first-player-win proof project for covered positions, and a general-purpose search engine for manually composed positions or other states outside the proof tree. The switch is transparent to the frontend, while the API reports the currently active black engine.

**White** is Gokumoku's own defensive decision layer. It uses an empirical response book built from historical self-play and multi-engine matches, checks immediate wins and losses first, evaluates candidate moves with strong engines such as Rapfi, and can consult multiple Gomocup-compatible engines when available. Its goal is to resist as long as possible, punish black deviations from the proof line, and counterattack when tactical chances appear.

## Features

- Browser board with manual play, AI black, AI white, undo, restart, and win detection.
- `/next_step` endpoint for black moves.
- `/white_next_step` endpoint for white moves.
- Position-aware black engine selection: proof data when available, strong search fallback otherwise.
- White engine that can use Rapfi and optional Gomocup-compatible engines for stronger decisions.
- Local benchmark helpers for engine-vs-engine testing.
- Optional LAN proxy for playing from another device on the same network.

## Run Locally

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Create a local configuration:

```bash
cp .env.example .env
```

Set the paths in `.env` for the proof data, Rapfi, and any Gomocup engines you want to use.

Start the server:

```bash
cd server
python white_ai_server.py 8090
```

Open:

```text
http://127.0.0.1:8090/gomoku.html
```

To play from another device on the same LAN:

```bash
node tools/lan_proxy.js --listen-host=<your-lan-ip> --listen-port=8090 --target-host=127.0.0.1 --target-port=8090
```

## External Assets

This clean release repository does not bundle large engine binaries, neural network weights, LevelDB proof databases, or raw benchmark logs.

For full strength, provide:

- first-player proof data, LevelDB files, and the related `web_search` binary from [fucusy/gomoku-first-move-always-win](https://github.com/fucusy/gomoku-first-move-always-win)
- Rapfi executable and network files from [dhbloo/rapfi](https://github.com/dhbloo/rapfi)
- optional Gomocup-compatible PBrain engines under `GOMOCUP_ENGINE_ROOT`

Without those assets, the web UI can still load and play, but the AI strength will not match the full local configuration.

## Credits

Gokumoku builds on and integrates ideas or components from:

- [fucusy/gomoku-first-move-always-win](https://github.com/fucusy/gomoku-first-move-always-win)
- [dhbloo/gomoku-calculator](https://github.com/dhbloo/gomoku-calculator)
- [dhbloo/rapfi](https://github.com/dhbloo/rapfi)
- [Gomocup](https://gomocup.org/) and the Gomocup AI ecosystem
- jQuery

See [NOTICE.md](NOTICE.md) for license and redistribution notes.
