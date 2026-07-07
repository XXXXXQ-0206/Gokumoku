[中文 README](README.zh-CN.md)

# Gokumoku

Gokumoku is an experimental, high-strength Gomoku AI lab focused on two goals:

- preserve fucusy-style black behavior when the proven first-move-win path is available
- build a stronger white defensive AI by combining resistance books, Rapfi analysis, Gomocup teacher voting, and calculator-style tactical routing

It is intended as a practical research system rather than a packaged engine with bundled networks and databases. Large third-party engines, fucusy proof data, and local benchmark traces are intentionally not included in this clean repository.

## What Is Included

- A Tornado web server with:
  - `/next_step` for black
  - `/white_next_step` for white
  - static frontend at `/gomoku.html`
- The adapted Gomoku web frontend with manual play, AI black, AI white, undo, restart, terminal detection, and a compact diagnostics table.
- Public test/benchmark helper tools.
- Configuration examples for local fucusy, Rapfi, and Gomocup engine paths.

## Current Local Results

These are local experimental checks, not official Elo ratings.

| Scenario | Settings | Result |
|---|---:|---|
| fucusy black invariant | `_h8_a1`, high level | black returns `i9` from LevelDB |
| calculator/Rapfi black vs calculator-route white | depth 64, 4 threads, 5000 ms/turn | BLACK/21 |
| calculator/Rapfi black vs current auto white | depth 64, 4 threads, 5000 ms/turn | BLACK/33 |
| 14-engine local single round | depth 4, 1 thread, 500 ms/turn | 8W-1D-5L |
| accepted 11-engine local single round | depth 4, 1 thread, 500 ms/turn | 5W-0D-6L |

The project is built to chase near-frontier public Gomoku strength, but it is not an official Gomocup #1 claim and it does not yet prove stable non-loss against every public engine.

## Run

Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

Configure the external engines and data:

```bash
cp .env.example .env
```

Then export the variables from `.env` in your shell, or set them manually.

Start the server:

```bash
cd server
python white_ai_server.py 8090
```

Open:

```text
http://127.0.0.1:8090/gomoku.html
```

For LAN play from another device, run a reverse proxy or use the helper:

```bash
node tools/lan_proxy.js --listen-host=<your-lan-ip> --listen-port=8090 --target-host=127.0.0.1 --target-port=8090
```

## Required External Assets

For full strength you need to provide:

- fucusy LevelDB/proof data in `server/leveldb.db` or another configured path
- fucusy `web_search` binary if you want exact original fallback search
- Rapfi executable and networks
- optional Gomocup PBrain engines under `GOMOCUP_ENGINE_ROOT`

Without these assets, the UI can still load, but the AI will not match the reported strength.

## Credits

Gokumoku stands on the shoulders of:

- [fucusy/gomoku-first-move-always-win](https://github.com/fucusy/gomoku-first-move-always-win)
- [dhbloo/gomoku-calculator](https://github.com/dhbloo/gomoku-calculator)
- [dhbloo/rapfi](https://github.com/dhbloo/rapfi)
- [Gomocup](https://gomocup.org/) and the Gomocup AI ecosystem
- jQuery

See [NOTICE.md](NOTICE.md) for license and redistribution notes.
