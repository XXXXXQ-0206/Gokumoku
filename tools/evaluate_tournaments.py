import argparse
import json
import math
import os
from collections import defaultdict


KNOWN_GOMOCUP_ELO = {
    "rapfi25": 3073,
    "katagomo26_f15": 2879,
    "alphagomoku_mk26": 2781,
    "jax25": 2662,
    "embryo26_f": 2402,
}


def iter_jsonl(path):
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit("%s:%d invalid JSON: %s" % (path, line_number, exc))


def game_score(row):
    winner = row.get("winner")
    moves = int(row.get("moves") or 0)
    if winner == "WHITE":
        return 1.0, "W", max(0, 1_000_000 - moves)
    if winner in ("DRAW", "MAX_MOVES"):
        return 0.5, "D", 500_000 + moves
    if winner == "BLACK":
        return 0.0, "L", moves
    return None, winner or "?", -1


def group_key(row, mode):
    settings = row.get("settings") or {}
    if mode == "black":
        return (row.get("black_player") or "",)
    if mode == "target":
        return (settings.get("white_target") or "", settings.get("resolved_white_target") or "")
    if mode == "black-target":
        return (
            row.get("black_player") or "",
            settings.get("white_target") or "",
            settings.get("resolved_white_target") or "",
        )
    raise ValueError("unknown grouping mode: %s" % mode)


def summarize(rows, mode):
    grouped = defaultdict(list)
    for row in rows:
        grouped[group_key(row, mode)].append(row)

    summaries = []
    for key, games in grouped.items():
        points = 0.0
        quality = 0
        outcomes = defaultdict(int)
        moves = []
        raw_games = []
        for row in games:
            score, tag, value = game_score(row)
            outcomes[tag] += 1
            if score is not None:
                points += score
            quality += value
            moves.append(int(row.get("moves") or 0))
            raw_games.append("%s/%s" % (row.get("winner"), row.get("moves")))
        count = len(games)
        summaries.append(
            {
                "key": key,
                "games": count,
                "wins": outcomes["W"],
                "draws": outcomes["D"],
                "losses": outcomes["L"],
                "other": count - outcomes["W"] - outcomes["D"] - outcomes["L"],
                "points": points,
                "score_pct": points / count if count else 0.0,
                "quality": quality,
                "avg_moves": sum(moves) / count if count else 0.0,
                "min_moves": min(moves) if moves else 0,
                "max_moves": max(moves) if moves else 0,
                "games_text": ", ".join(raw_games),
            }
        )
    summaries.sort(key=lambda item: (item["points"], item["quality"], item["avg_moves"]), reverse=True)
    return summaries


def performance_elo(rows):
    known_games = []
    for row in rows:
        black = row.get("black_player")
        if black not in KNOWN_GOMOCUP_ELO:
            continue
        score, _tag, _quality = game_score(row)
        if score is None:
            continue
        known_games.append((KNOWN_GOMOCUP_ELO[black], score))
    if not known_games:
        return None
    score_sum = sum(score for _elo, score in known_games)
    count = len(known_games)
    avg_opp = sum(elo for elo, _score in known_games) / count
    pct = score_sum / count
    clipped = min(0.999, max(0.001, pct))
    perf = avg_opp + 400 * math.log10(clipped / (1 - clipped))
    return {
        "known_games": count,
        "points": score_sum,
        "score_pct": pct,
        "avg_opp_elo": avg_opp,
        "performance_elo": perf,
        "note": "rough role-fixed performance estimate from known official Gomocup Elo opponents",
    }


def print_table(title, summaries):
    print("\n### %s" % title)
    for item in summaries:
        key = " / ".join(part for part in item["key"] if part)
        print(
            "%-54s games=%3d W-D-L-O=%2d-%2d-%2d-%2d pct=%5.1f%% quality=%8d avgMoves=%5.1f games=%s"
            % (
                key,
                item["games"],
                item["wins"],
                item["draws"],
                item["losses"],
                item["other"],
                item["score_pct"] * 100,
                item["quality"],
                item["avg_moves"],
                item["games_text"],
            )
        )


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--group", choices=["black", "target", "black-target"], default="black-target")
    parser.add_argument("--performance-elo", action="store_true")
    args = parser.parse_args(argv)

    all_rows = []
    by_file = []
    for path in args.paths:
        rows = list(iter_jsonl(path))
        all_rows.extend(rows)
        by_file.append((path, rows))

    for path, rows in by_file:
        print_table(os.path.basename(path), summarize(rows, args.group))
        if args.performance_elo:
            perf = performance_elo(rows)
            if perf:
                print(
                    "performance_elo knownGames=%d points=%.1f pct=%.1f%% avgOpp=%.1f perf=%.1f (%s)"
                    % (
                        perf["known_games"],
                        perf["points"],
                        perf["score_pct"] * 100,
                        perf["avg_opp_elo"],
                        perf["performance_elo"],
                        perf["note"],
                    )
                )

    if len(by_file) > 1:
        print_table("combined", summarize(all_rows, args.group))
        if args.performance_elo:
            perf = performance_elo(all_rows)
            if perf:
                print(
                    "combined_performance_elo knownGames=%d points=%.1f pct=%.1f%% avgOpp=%.1f perf=%.1f (%s)"
                    % (
                        perf["known_games"],
                        perf["points"],
                        perf["score_pct"] * 100,
                        perf["avg_opp_elo"],
                        perf["performance_elo"],
                        perf["note"],
                    )
                )


if __name__ == "__main__":
    main()
