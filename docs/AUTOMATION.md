# Automation And TUI

Gokumoku includes a small but practical local evaluation workflow. It is designed to make engine changes measurable before they are promoted.

## Match Runner

`tools/pbrain_match_runner.py` can run one fixed-setting game between:

- the local HTTP black endpoint;
- the local HTTP white endpoint;
- any Gomocup-compatible PBrain engine.

Example:

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

For a PBrain opponent:

```bash
python tools/pbrain_match_runner.py \
  --black pbrain:rapfi25=/path/to/pbrain-rapfi \
  --white http_gokumoku_white \
  --http-base http://127.0.0.1:8090 \
  --depth 4 \
  --threads 1 \
  --turn-time-ms 500 \
  --compact
```

The runner outputs JSON. Store repeated runs as JSONL files under a local `benchmarks/` directory when you want the evaluator and TUI to read them.

## Evaluator

`tools/evaluate_tournaments.py` summarizes JSONL match files by opponent, target, or opponent-target pair:

```bash
python tools/evaluate_tournaments.py benchmarks/*.jsonl \
  --group black-target \
  --performance-elo
```

The Elo estimate is role-fixed and local. It uses known Gomocup ratings only as anchors for the opponents present in the input files; it is not an official rating.

## TUI Dashboard

`tools/gokumoku_tui.py` is a Textual dashboard for watching the evaluation loop:

```bash
python tools/gokumoku_tui.py \
  --results "benchmarks/*.jsonl" \
  --steps "_h8"
```

The dashboard shows:

- one live board, updated from the latest result file;
- recent match evidence;
- the optimization workflow stages;
- a live log with refresh events.

It deliberately reads public JSONL artifacts rather than private local state. That keeps the workflow easy to resume, easy to copy to another machine, and safe to publish.

## Promotion Rule

Do not promote a white-policy change from a single attractive game. A change should survive:

- a repeated sample under fixed depth, thread count, and time budget;
- regression games against proof-tree black;
- regression games against general-search black;
- a repository scan confirming that no local paths, raw logs, or private engine files entered the clean tree.
