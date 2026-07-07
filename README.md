[中文 README](README.zh-CN.md)

# Gokumoku

Gokumoku is a web-playable Gomoku AI project built around a hybrid engine design. It brings together a proof-oriented black engine, a strong general-purpose search engine, and a white-side defensive system tuned through local engine matches.

The goal is simple: make a Gomoku AI that is interesting to play against, strong enough to be tested against Gomocup-class engines, and easy to run locally with a browser frontend.

## Design

Gokumoku treats black and white differently, because they are different problems.

For black, the engine combines two complementary sources of strength. In positions covered by the first-move-win proof data, it follows exact winning continuations from the proof database. When the position falls outside that solved tree, it switches to a full-strength search engine so the game can continue with strong practical play instead of stalling.

For white, Gokumoku uses its own defensive decision layer. It looks for immediate tactical wins and losses, uses Rapfi-style search for local evaluation, consults multiple Gomocup-compatible engines when available, and prefers lines that have performed well in repeated local engine matches. The result is not a passive "block everything" player; it actively tries to survive longer, punish mistakes, and convert tactical chances when black leaves the proven path.

## Features

- Browser board with manual play, AI black, AI white, undo, restart, and win detection.
- `/next_step` endpoint for black moves.
- `/white_next_step` endpoint for white moves.
- Position-aware black engine selection: proof data when available, strong search fallback otherwise.
- White engine that can use Rapfi and optional Gomocup-compatible engines for stronger decisions.
- Local benchmark helpers for engine-vs-engine testing.
- Optional LAN proxy for playing from another device on the same network.

## Local Results

These are local experimental results, not official Gomocup ratings.

| Test | Settings | Result |
|---|---:|---|
| proof-data black sanity check | `_h8_a1`, high level | black returns `i9` from LevelDB |
| calculator/Rapfi black vs calculator-route white | depth 64, 4 threads, 5000 ms/turn | BLACK/21 |
| calculator/Rapfi black vs Gokumoku auto white | depth 64, 4 threads, 5000 ms/turn | BLACK/33 |
| local 14-engine single round | depth 4, 1 thread, 500 ms/turn | 8W-1D-5L |
| local 11-engine acceptance round | depth 4, 1 thread, 500 ms/turn | 5W-0D-6L |

Gokumoku is designed to push toward very strong public Gomoku play, but the numbers above are local reproducibility notes rather than official rankings.

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

This clean repository does not bundle large engines, neural network weights, proof databases, or raw benchmark logs.

For full strength, provide:

- first-move-win proof data and LevelDB files from `fucusy/gomoku-first-move-always-win`
- the related `web_search` binary if you want exact proof-search fallback behavior
- Rapfi executable and network files
- optional Gomocup-compatible PBrain engines under `GOMOCUP_ENGINE_ROOT`

Without those assets, the web UI can still load, but the AI will not match the reported strength.

## Credits

Gokumoku builds on and integrates ideas or components from:

- [fucusy/gomoku-first-move-always-win](https://github.com/fucusy/gomoku-first-move-always-win)
- [dhbloo/gomoku-calculator](https://github.com/dhbloo/gomoku-calculator)
- [dhbloo/rapfi](https://github.com/dhbloo/rapfi)
- [Gomocup](https://gomocup.org/) and the Gomocup AI ecosystem
- jQuery

See [NOTICE.md](NOTICE.md) for license and redistribution notes.
