import argparse
import glob
import json
import os
import time

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, RichLog, Static

from pbrain_match_runner import BLACK, BOARD_SIZE, WHITE, color_at, parse_steps


PIPELINE_STEPS = [
    ("collect", "Collect engine games"),
    ("score", "Score wins, draws, and long losses"),
    ("compare", "Compare candidate policies"),
    ("verify", "Run regression matches"),
    ("promote", "Promote only reviewed changes"),
]


def load_jsonl(paths):
    rows = []
    for pattern in paths:
        for path in glob.glob(pattern):
            with open(path, "r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        row = {
                            "winner": "ERROR",
                            "moves": 0,
                            "black_player": os.path.basename(path),
                            "white_player": "parse error",
                            "steps": "",
                            "source": "%s:%d" % (path, line_number),
                        }
                    else:
                        row["source"] = "%s:%d" % (path, line_number)
                    rows.append(row)
    rows.sort(key=lambda row: row.get("source", ""))
    return rows


def score_key(row):
    winner = row.get("winner")
    moves = int(row.get("moves") or 0)
    if winner == "WHITE":
        return 3, -moves
    if winner in ("DRAW", "MAX_MOVES"):
        return 2, moves
    if winner == "BLACK":
        return 1, moves
    return 0, 0


def board_panel(steps):
    board = color_at(steps)
    last = None
    if steps:
        from pbrain_match_runner import move_to_xy

        last = move_to_xy(steps[-1])
    text = Text()
    text.append("    " + " ".join(chr(ord("a") + x) for x in range(BOARD_SIZE)) + "\n", style="bold cyan")
    for y in range(BOARD_SIZE - 1, -1, -1):
        text.append("%2d  " % (y + 1), style="bold cyan")
        for x in range(BOARD_SIZE):
            piece = board.get((x, y))
            if piece == BLACK:
                char, style = "B", "bold black on bright_white"
            elif piece == WHITE:
                char, style = "W", "bold bright_white on grey23"
            else:
                char, style = "+", "dim"
            if last == (x, y):
                style = "bold black on yellow" if piece == BLACK else "bold white on red"
            text.append(char, style=style)
            text.append(" ")
        text.append(" %2d\n" % (y + 1), style="bold cyan")
    text.append("    " + " ".join(chr(ord("a") + x) for x in range(BOARD_SIZE)), style="bold cyan")
    return Panel(text, title="Live board", border_style="bright_cyan")


def result_table(rows):
    table = Table(expand=True)
    table.add_column("Black", overflow="fold")
    table.add_column("White", overflow="fold")
    table.add_column("Result", justify="center")
    table.add_column("Moves", justify="right")
    table.add_column("Source", overflow="fold")
    for row in sorted(rows, key=score_key, reverse=True)[:8]:
        table.add_row(
            str(row.get("black_player") or "-"),
            str(row.get("white_player") or "-"),
            str(row.get("winner") or "-"),
            str(row.get("moves") or "-"),
            str(row.get("source") or "-"),
        )
    return Panel(table, title="Recent evidence", border_style="green")


def pipeline_panel(rows):
    total = max(1, len(rows))
    done = min(total, sum(1 for row in rows if row.get("winner") in ("WHITE", "BLACK", "DRAW", "MAX_MOVES")))
    pct = int(done * 100 / total)
    table = Table(expand=True, show_header=False)
    table.add_column("Step", ratio=2)
    table.add_column("State", ratio=1)
    for index, (_key, label) in enumerate(PIPELINE_STEPS):
        if not rows and index > 0:
            state = "waiting"
        elif index <= min(4, done):
            state = "ready"
        else:
            state = "queued"
        table.add_row(label, state)
    table.add_row("Evidence coverage", "[%s%s] %d%%" % ("#" * (pct // 10), "." * (10 - pct // 10), pct))
    return Panel(table, title="Optimization workflow", border_style="magenta")


class GokumokuTui(App):
    CSS = """
    Screen {
        background: #071018;
        color: #d8e2ea;
    }

    #top {
        height: 3;
        padding: 0 1;
        background: #10202e;
        border-bottom: solid #1f7a8c;
    }

    #body {
        height: 1fr;
    }

    #left {
        width: 42%;
        min-width: 52;
        padding: 1;
        border-right: solid #1f7a8c;
    }

    #right {
        width: 1fr;
        padding: 1;
    }

    #board {
        height: 24;
    }

    #pipeline {
        height: 13;
        margin-top: 1;
    }

    #results {
        height: 22;
        margin-bottom: 1;
    }

    #log {
        height: 1fr;
        background: #05090d;
        border: solid #355b6b;
    }

    Button {
        margin-right: 1;
    }
    """

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, args):
        super().__init__()
        self.args = args
        self.rows = []
        self.steps = parse_steps(args.steps)
        self.last_refresh = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="top"):
            yield Button("Refresh", id="refresh")
            yield Static("Gokumoku optimization cockpit", id="title")
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield Static(id="board")
                yield Static(id="pipeline")
            with Vertical(id="right"):
                yield Static(id="results")
                yield RichLog(id="log", wrap=True, highlight=True)
        yield Footer()

    def on_mount(self):
        self.refresh()
        self.set_interval(self.args.refresh_seconds, self.refresh)

    def on_button_pressed(self, event):
        if event.button.id == "refresh":
            self.refresh()

    def action_refresh(self):
        self.refresh()

    def refresh(self):
        self.rows = load_jsonl(self.args.results)
        if self.rows:
            latest = self.rows[-1]
            self.steps = parse_steps(latest.get("steps") or self.args.steps)
        self.query_one("#board", Static).update(board_panel(self.steps))
        self.query_one("#pipeline", Static).update(pipeline_panel(self.rows))
        self.query_one("#results", Static).update(result_table(self.rows))
        now = time.strftime("%H:%M:%S")
        self.query_one("#log", RichLog).write(
            "%s refreshed: %d result rows, %d stones on board"
            % (now, len(self.rows), len(self.steps))
        )
        self.last_refresh = time.time()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Gokumoku Textual dashboard")
    parser.add_argument(
        "--results",
        action="append",
        default=["benchmarks/*.jsonl"],
        help="JSONL match result glob. Can be passed multiple times.",
    )
    parser.add_argument("--steps", default="_h8", help="Initial board state when no result file is available.")
    parser.add_argument("--refresh-seconds", type=float, default=2.0)
    return parser.parse_args(argv)


def main(argv=None):
    GokumokuTui(parse_args(argv)).run()


if __name__ == "__main__":
    main()
