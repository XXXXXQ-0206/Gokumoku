# Notice

Gokumoku is an experimental Gomoku engine that combines and extends several open-source Gomoku components.

## Included Or Derived Components

- `fucusy/gomoku-first-move-always-win`: first-player proof data, original web UI assets, and LevelDB/proof-search integration patterns. License: MIT. Copyright (c) 2024 Qiang Chen.
- jQuery 3.2.1: included in `server/web/js/jquery.js`. License: MIT.

## External Runtime Dependencies

These are not bundled in this clean repository:

- `dhbloo/rapfi`: Rapfi/PBrain engine used for local search, black fallback search, and optional white-side analysis. Rapfi is GPL-3.0; follow its license when distributing binaries or modified code.
- Gomocup engines and Gomocup Manager ecosystem: used for local benchmarking and optional multi-engine advice. Check each engine's license before redistribution.
- `dhbloo/gomoku-calculator`: used as an algorithmic reference project. Check its repository license before vendoring code.
- `fucusy/gomoku-first-move-always-win` large LevelDB/proof data and proof-search binary: not bundled here; configure paths locally if you use them.

## Benchmark Claims

Benchmark numbers in this repository are local experimental results, not official Gomocup rankings or official Elo ratings.
