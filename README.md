[中文 README](README.zh-CN.md)

# Gokumoku

Gokumoku is an experimental hybrid Gomoku engine. It combines proof-tree play for solved first-player positions, full-strength search for positions outside that tree, and an empirically tuned white decision layer in one measurable engine stack.

The browser board is the easiest way to play against the engine, but it is not the core of the project. The core is the engine stack, the match runner, and the local evaluation workflow used to keep engine changes measurable.

![Gokumoku desktop board](docs/assets/frontend-desktop.png)

![Gokumoku mobile board](docs/assets/frontend-mobile.png)

![Gokumoku TUI dashboard](docs/assets/tui-dashboard.png)

## Engine Architecture

Gokumoku treats black and white as different engineering problems.

For black, the engine combines two complementary sources. In positions covered by solved first-player proof data, it follows exact proof-tree continuations. In manually composed positions, abnormal openings, or positions where the proof tree no longer supplies a legal move, it switches to a general-search engine that can keep giving near-optimal practical moves.

For white, Gokumoku uses its own defensive decision layer. It checks immediate wins and immediate losses first, uses strong local search for tactical evaluation, can consult Gomocup-compatible engines when they are configured, and uses a historical match-response database built from repeated local engine games. The goal is not to block mechanically; the white side tries to resist longer under best black play, punish mistakes, and convert tactical chances when black leaves the strongest path.

## Features

- Hybrid black engine: proof-tree continuations plus general-search fallback.
- White engine with tactical checks, search signals, optional engine-vote signals, and empirical response data.
- Browser board for manual play, AI black, AI white, undo, restart, and terminal win detection.
- `/next_step` endpoint for black moves.
- `/white_next_step` endpoint for white moves.
- PBrain/Gomocup-compatible match runner.
- Local tournament evaluator with role-fixed Elo helper.
- Textual TUI dashboard for watching board state, match evidence, and the optimization workflow.
- Optional LAN proxy for playing from another device on the same network.

## Project Structure

```text
server/
  white_ai_server.py        HTTP service and current engine orchestration
  web/gomoku.html           browser board, using the original board assets and coordinate system
tools/
  pbrain_match_runner.py    fixed-setting matches against HTTP or PBrain engines
  evaluate_tournaments.py   JSONL summary and local performance-Elo helper
  gokumoku_tui.py           Textual dashboard for runs and match evidence
  lan_proxy.js              LAN access proxy
docs/
  ARCHITECTURE_REVIEW.md    current boundaries and refactor plan
  AUTOMATION.md             repeatable evaluation workflow and TUI usage
  assets/                   frontend and TUI screenshots
```

## Local Results

These numbers are local experimental results, not official Gomocup rankings.

The Elo anchors are taken from Gomocup's Freestyle20 rating page as checked on 2026-07-07: RAPFI 2025 3073, KATAGOMO 2026 2879, ALPHAGOMOKU (MK) 2026 2781, JAX 2025 2662, EMBRYO 2026 2372, YIXIN 2018 2217, VIBEFIVE 2026 2172, and PENTAZEN 2021 2171.

| Check | Settings | Result |
|---|---:|---|
| Online-compatible black sanity check | `https://gomoku.hula.ai/next_step`, `_h8_a1`, high level | returns `i9` |
| Local proof-tree black sanity check | same position and parameters, full local asset set | returns `i9` from LevelDB |
| General-search black vs baseline white policy | depth 64, 4 threads, 5000 ms/turn | BLACK/21 |
| General-search black vs Gokumoku white | depth 64, 4 threads, 5000 ms/turn | BLACK/33 |
| Proof-tree-compatible black vs Gokumoku white | local full-strength configuration | BLACK/35 |
| Local 11-engine acceptance round | depth 4, 1 thread, 500 ms/turn | 5W-0D-6L, local anchor performance about 2452 |
| Local 14-engine expanded checks | two single-round files, depth 4, 1 thread, 500 ms/turn | 13W-1D-16L across 30 games, local anchor performance about 2475 |
| Older 7-engine repeated check | 3 repeats, 500 ms/turn | 6W-0D-12L against known-rating engines, local anchor performance about 2536 |

Elo status: `tools/evaluate_tournaments.py` computes a role-fixed local performance estimate from the opponents present in a JSONL file. It is useful for comparing local model versions, but it is not a Gomocup rating and should not be read as a ladder placement.

## Run Locally

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Create a local configuration:

```bash
cp .env.example .env
```

Set the paths in `.env` for proof data, Rapfi, and optional Gomocup-compatible engines.

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

## Evaluation Workflow

Run a fixed-setting game:

```bash
python tools/pbrain_match_runner.py \
  --black http_proof_tree_black \
  --white http_gokumoku_white \
  --http-base http://127.0.0.1:8090 \
  --depth 4 \
  --threads 1 \
  --turn-time-ms 500 \
  --compact
```

Summarize JSONL results:

```bash
python tools/evaluate_tournaments.py benchmarks/*.jsonl --group black-target --performance-elo
```

Open the TUI dashboard:

```bash
python tools/gokumoku_tui.py --results "benchmarks/*.jsonl"
```

More detail: [Automation And TUI](docs/AUTOMATION.md) and [Architecture Review](docs/ARCHITECTURE_REVIEW.md).

## External Assets

This clean repository does not bundle large engines, neural-network weights, proof databases, or raw benchmark logs.

For full strength, provide:

- first-player proof data and LevelDB files from [`fucusy/gomoku-first-move-always-win`](https://github.com/fucusy/gomoku-first-move-always-win)
- the related proof-search binary if you want exact proof-search behavior beyond LevelDB hits
- Rapfi executable and network files
- optional Gomocup-compatible PBrain engines under `GOMOCUP_ENGINE_ROOT`

Without those assets, the web UI can still load, but the engine will not match the reported strength.

## Credits

Gokumoku builds on open-source work and public engine ecosystems, including:

- [`fucusy/gomoku-first-move-always-win`](https://github.com/fucusy/gomoku-first-move-always-win)
- [`dhbloo/gomoku-calculator`](https://github.com/dhbloo/gomoku-calculator)
- [`dhbloo/rapfi`](https://github.com/dhbloo/rapfi)
- [Gomocup](https://gomocup.org/) and the Gomocup AI ecosystem
- jQuery

See [NOTICE.md](NOTICE.md) for license and redistribution notes.
