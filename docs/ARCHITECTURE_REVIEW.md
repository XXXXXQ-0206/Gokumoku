# Architecture Review

Date: 2026-07-07

This review describes the public Gokumoku source tree and the boundaries that should be kept stable as the engine grows.

## Current Structure

```text
.
├─ server/
│  ├─ white_ai_server.py
│  └─ web/
│     ├─ gomoku.html
│     ├─ js/jquery.js
│     └─ pic/
├─ tools/
│  ├─ pbrain_match_runner.py
│  ├─ evaluate_tournaments.py
│  ├─ gokumoku_tui.py
│  └─ lan_proxy.js
├─ README.md
├─ README.zh-CN.md
├─ NOTICE.md
└─ requirements.txt
```

The repository is intentionally clean: large engines, neural-network files, proof databases, raw logs, and local benchmark state are not bundled.

## Engine Boundaries

Gokumoku currently has four major runtime roles:

- Rules and board state: coordinate parsing, legal move checks, win detection, and move-history conversion.
- Black engine routing: proof-tree play when a solved continuation is available, general-search play when a position is outside that tree.
- White decision layer: immediate win/loss checks, local search signals, advisor-engine signals when configured, and empirical response books from repeated local matches.
- HTTP and UI integration: `/next_step`, `/white_next_step`, the browser board, LAN proxy, match runner, evaluator, and TUI dashboard.
- Runtime isolation: heavy engine calls run in a dedicated executor. The default worker count is one, so engine state stays serialized while Tornado can still serve static pages and diagnostics during long searches.

The main technical debt is that `server/white_ai_server.py` still contains most of those roles in one file. That shape is workable for reproducing experiments, but it is not the best long-term architecture.

## Recommended Split

The next clean refactor should split the backend without changing behavior:

- `rules.py`: coordinates, board state, winner detection, and legality.
- `black_engine.py`: proof-tree lookup, proof-search binary adapter, and general-search fallback.
- `white_engine.py`: white move selection, target normalization, response books, and candidate scoring.
- `pbrain.py`: PBrain process management and Gomocup-compatible engine calls.
- `schema.py`: public response summaries and debug response shaping.
- `server.py`: Tornado handlers and static file serving only.

That split would make tests smaller, reduce accidental API changes, and make it easier to hide raw diagnostics unless `debug=1`.

## Public Naming Rules

The public code should use role names rather than account names or experiment nicknames:

- `proof_tree_black`: black move source backed by solved first-player continuations.
- `general_search_black`: black move source backed by full-strength search for positions outside the proof tree.
- `proof_tree`, `general_search`, `gomocup`, `advisor_ensemble`: white target or opponent categories.
- `Gokumoku white`: the project white decision layer.

External project names belong in credits, notices, and setup instructions. They should not become product concepts, UI labels, or default API values.

## Frontend Review

The frontend is still a single HTML file because it preserves the original board assets and coordinate logic. The current cleanup keeps that coordinate system intact and adds only an outer responsive layout.

Important state transitions:

- Undo removes exactly one move and can undo the initial center stone.
- Restart cancels in-flight requests, resets diagnostics, and rebuilds the configured opening.
- Machine-control buttons only block manual play for the controlled color.
- A terminal five-in-a-row sets the game state before displaying the win message, so later clicks are ignored.
- Black engine switching is reflected in the diagnostics table with public labels.

The next frontend refactor should split:

- `GameState`: history, legal moves, winner detection.
- `TurnController`: AI ownership, undo, restart, and terminal state.
- `ApiClient`: request ids, aborts, normalized responses.
- `InfoPanel`: display-only view model.

## Benchmark Hygiene

Local benchmark results should be reproducible from `tools/pbrain_match_runner.py` plus the configured external engines. A result belongs in README only when it records:

- black player and white player;
- depth, thread count, and per-turn time;
- opening or initial position;
- final winner and move count;
- whether the opponent has a published Gomocup rating.

Elo-like estimates from local games are useful for orientation, but they are not official Gomocup ratings and must be labeled as local estimates.

## Current Release Gate

Before publishing a stronger claim, run:

- Python syntax checks for backend and tools.
- Browser smoke tests for desktop and mobile widths.
- Black API consistency checks against the online-compatible proof-tree positions.
- White-vs-engine match samples with fixed time/depth/thread settings.
- A repository scan for private paths, raw local logs, and internal experiment labels.
