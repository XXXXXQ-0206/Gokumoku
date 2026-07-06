# Notice

Gokumoku is an experimental integration project that combines and extends several open-source Gomoku components.

## Included Or Derived Components

- `fucusy/gomoku-first-move-always-win`: original black first-move-win solver, web UI assets, and LevelDB/web-search integration patterns. License: MIT. Copyright (c) 2024 Qiang Chen.
- jQuery 3.2.1: included in `server/web/js/jquery.js`. License: MIT.

## External Runtime Dependencies

These are not bundled in this clean repository:

- `dhbloo/rapfi`: Rapfi/PBrain engine used for analysis, teacher voting, and calculator-style fallback. Rapfi is GPL-3.0; follow its license when distributing binaries or modified code.
- Gomocup engines and Gomocup Manager ecosystem: used for local benchmarking and teacher signals. Check each engine's license before redistribution.
- `dhbloo/gomoku-calculator`: used as an algorithmic reference point and for calculator-style black/white routing. Check its repository license before vendoring code.
- `fucusy/gomoku-first-move-always-win` large LevelDB/proof data and `web_search` binary: not bundled here; configure paths locally if you use them.

## Benchmark Claims

Benchmark numbers in this repository are local experimental results, not official Gomocup rankings or official Elo ratings.
