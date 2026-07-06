import argparse
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request


BOARD_SIZE = 15
BLACK = 1
WHITE = 2
PBRAIN_MEMORY_BYTES = 536870912
WHITE_TARGET_CHOICES = [
    "auto",
    "none",
    "fucusy",
    "calculator",
    "generic",
    "gomocup",
    "vibefive",
    "jax",
    "katagomo",
    "ensemble",
    "teacher",
    "teacher_ensemble",
    "gomocup_top",
    "rapfi25",
    "katagomo26_f15",
    "alphagomoku_mk26",
    "jax25",
    "vibefive26",
    "embryo26_f",
    "yixin18",
    "starpoint26_f15",
    "pentazen21_15",
    "skyzero26",
]


def move_to_xy(move):
    return ord(move[0]) - ord("a"), int(move[1:]) - 1


def xy_to_move(x, y):
    return "%s%d" % (chr(ord("a") + x), y + 1)


def steps_to_string(steps, leading=True):
    text = "_".join(steps)
    return "_" + text if leading else text


def parse_steps(raw):
    raw = (raw or "").strip().strip("_")
    return [] if raw == "" else [move for move in raw.split("_") if move]


def color_to_move(steps):
    return BLACK if len(steps) % 2 == 0 else WHITE


def color_at(steps):
    board = {}
    for index, move in enumerate(steps):
        board[move_to_xy(move)] = BLACK if index % 2 == 0 else WHITE
    return board


def has_five(steps, color):
    board = color_at(steps)
    for (x, y), piece in board.items():
        if piece != color:
            continue
        for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
            if board.get((x - dx, y - dy)) == color:
                continue
            count = 0
            nx, ny = x, y
            while board.get((nx, ny)) == color:
                count += 1
                nx += dx
                ny += dy
            if count >= 5:
                return True
    return False


def winner(steps):
    if has_five(steps, BLACK):
        return "BLACK"
    if has_five(steps, WHITE):
        return "WHITE"
    if len(steps) >= BOARD_SIZE * BOARD_SIZE:
        return "DRAW"
    return None


def is_legal(steps, move):
    if not re.match(r"^[a-o](?:[1-9]|1[0-5])$", move or ""):
        return False
    x, y = move_to_xy(move)
    return 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE and (x, y) not in {move_to_xy(m) for m in steps}


def http_json(url, params, timeout):
    full_url = url + "?" + urllib.parse.urlencode(params)
    started = time.time()
    with urllib.request.urlopen(full_url, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    data["_url"] = full_url
    data.setdefault("elapsed_ms", int((time.time() - started) * 1000))
    return data


class HttpPlayer:
    def __init__(
        self,
        name,
        color,
        base_url,
        depth,
        threads,
        turn_time_ms,
        target=None,
        base_target=None,
        deep_tactics=False,
        request_timeout=None,
    ):
        self.name = name
        self.color = color
        self.base_url = base_url
        self.depth = depth
        self.threads = threads
        self.turn_time_ms = turn_time_ms
        self.target = target
        self.base_target = base_target
        self.deep_tactics = deep_tactics
        self.request_timeout = request_timeout
        self.opponent = None
        self.last_resolved_target = target

    def start_game(self, color):
        if color != self.color:
            raise ValueError("%s configured for color %s but got %s" % (self.name, self.color, color))

    def move(self, steps, game_id):
        if self.color == BLACK:
            data = http_json(
                self.base_url + "/next_step",
                {
                    "stepsString": steps_to_string(steps),
                    "color": "BLACK",
                    "level": "HIGH",
                    "gameId": game_id,
                },
                timeout=max(self.request_timeout or 60, self.turn_time_ms / 1000 + 30),
            )
        else:
            params = {
                "stepsString": steps_to_string(steps),
                "color": "WHITE",
                "level": "HIGH",
                "gameId": game_id,
                "depth": self.depth,
                "threads": self.threads,
                "turnTimeMs": self.turn_time_ms,
            }
            if self.target:
                params["target"] = self.target
            if self.base_target:
                params["baseTarget"] = self.base_target
            if self.opponent:
                params["opponent"] = self.opponent
            if self.deep_tactics:
                params["deepTactics"] = "1"
            data = http_json(
                self.base_url + "/white_next_step",
                params,
                timeout=max(self.request_timeout or 60, self.turn_time_ms / 1000 + 30),
            )
        if "selected_move" in data:
            move = data["selected_move"]
        else:
            move = xy_to_move(int(data["x"]), int(data["y"]))
        self.last_resolved_target = data.get("target", self.target)
        return {"move": move, "engine": self.name, "raw": data}

    def observe(self, move):
        return None

    def close(self):
        return None


class PBrainPlayer:
    def __init__(self, name, exe, turn_time_ms, threads, depth=None, start_timeout=60, board_mode=False):
        self.name = name
        self.exe = os.path.abspath(exe)
        self.cwd = os.path.dirname(self.exe)
        self.turn_time_ms = turn_time_ms
        self.threads = threads
        self.depth = depth
        self.start_timeout = start_timeout
        self.board_mode = board_mode
        self.proc = None
        self.lines = None
        self.reader = None
        self.color = None

    def start_game(self, color):
        self.color = color
        self.proc = subprocess.Popen(
            [self.exe],
            cwd=self.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self.lines = queue.Queue()

        def read_loop():
            for line in self.proc.stdout:
                self.lines.put(line.rstrip("\r\n"))

        self.reader = threading.Thread(target=read_loop, daemon=True)
        self.reader.start()
        self._send("START %d" % BOARD_SIZE)
        self._read_until(lambda line: line == "OK" or line.startswith("ERROR"), timeout=self.start_timeout)
        self._info()

    def _send(self, line):
        if self.proc is None or self.proc.poll() is not None:
            raise RuntimeError("%s is not running" % self.name)
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def _read_line(self, timeout):
        try:
            return self.lines.get(timeout=timeout)
        except queue.Empty:
            return None

    def _read_until(self, predicate, timeout):
        deadline = time.time() + timeout
        seen = []
        while time.time() < deadline:
            line = self._read_line(max(0.05, deadline - time.time()))
            if line is None:
                continue
            seen.append(line)
            if predicate(line):
                return line, seen
        raise TimeoutError("%s timed out; seen=%s" % (self.name, seen[-20:]))

    def _info(self):
        commands = [
            "INFO timeout_turn %d" % self.turn_time_ms,
            "INFO timeout_match 9999000",
            "INFO max_memory %d" % PBRAIN_MEMORY_BYTES,
            "INFO thread_num %d" % self.threads,
            "INFO rule 0",
            "INFO game_type 1",
            "INFO THREAD_NUM %d" % self.threads,
            "INFO TIMEOUT_TURN %d" % self.turn_time_ms,
        ]
        if self.depth is not None:
            commands.extend(["INFO max_depth %d" % self.depth, "INFO MAX_DEPTH %d" % self.depth])
        for command in commands:
            self._send(command)

    def _wait_move(self):
        move_line, seen = self._read_until(lambda line: re.match(r"^\d+,\d+$", line or "") is not None, timeout=max(20, self.turn_time_ms / 1000 + 15))
        x, y = [int(value) for value in move_line.split(",")]
        return {"move": xy_to_move(x, y), "engine": self.name, "raw": {"line": move_line, "seen": seen[-20:]}}

    def _send_board(self, steps):
        self._send("BOARD")
        for index, move in enumerate(steps):
            x, y = move_to_xy(move)
            stone_color = BLACK if index % 2 == 0 else WHITE
            field = 1 if stone_color == self.color else 2
            self._send("%d,%d,%d" % (x, y, field))
        self._send("DONE")

    def move(self, steps, game_id):
        if self.board_mode:
            self._send_board(steps)
        elif self.color == BLACK and not steps:
            self._send("BEGIN")
        else:
            last = steps[-1]
            x, y = move_to_xy(last)
            self._send("TURN %d,%d" % (x, y))
        return self._wait_move()

    def observe(self, move):
        return None

    def close(self):
        if self.proc is None:
            return
        try:
            if self.proc.poll() is None:
                self._send("END")
                self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None


def resolve_auto_target(black_spec):
    black_spec = black_spec.lower()
    if black_spec == "http_fucusy":
        return "fucusy"
    if "alphagomoku" in black_spec:
        return "gomocup"
    if "rapfi" in black_spec:
        return "calculator"
    if "vibefive" in black_spec:
        return "vibefive"
    if "chloris" in black_spec:
        return "calculator"
    if "katagomo" in black_spec:
        return "katagomo"
    if "jax" in black_spec:
        return "jax"
    return "gomocup"


def use_teacher_ensemble_for_auto(black_spec):
    black_spec = black_spec.lower()
    return any(
        name in black_spec
        for name in (
            "rapfi",
            "katagomo",
            "jax",
            "vibefive",
            "chloris",
            "starpoint",
            "yixin",
            "pentazen",
            "skyzero",
        )
    )


def resolve_auto_white_route(black_spec):
    black_spec = black_spec.lower()
    if "alphagomoku" in black_spec:
        return "jax25", None
    if "yixin" in black_spec:
        return "pentazen21_15", None
    if "slowrenju" in black_spec:
        return "alphagomoku_mk26", None
    if any(name in black_spec for name in ("jax", "vibefive", "skyzero", "stardust")):
        return "vibefive26", None
    if any(name in black_spec for name in ("katagomo", "pentazen")):
        return "alphagomoku_mk26", None
    base_target = resolve_auto_target(black_spec)
    if use_teacher_ensemble_for_auto(black_spec):
        return "teacher_ensemble", base_target
    return base_target, None


def make_player(spec, color, args):
    if spec == "http_fucusy":
        return HttpPlayer(
            "http_fucusy",
            BLACK,
            args.http_base,
            args.depth,
            args.threads,
            args.turn_time_ms,
            request_timeout=args.http_timeout,
        )
    if spec == "http_hybrid":
        if args.white_target == "auto":
            target = "auto"
            base_target = None
        elif args.white_target == "none":
            target = None
            base_target = None
        elif args.white_target == "teacher_ensemble":
            target = "teacher_ensemble"
            base_target = resolve_auto_target(args.black)
        else:
            target = args.white_target
            base_target = None
        player = HttpPlayer(
            "http_hybrid",
            WHITE,
            args.http_base,
            args.depth,
            args.threads,
            args.turn_time_ms,
            target=target,
            base_target=base_target,
            deep_tactics=args.deep_tactics,
            request_timeout=args.http_timeout,
        )
        player.opponent = args.black
        return player
    if spec.startswith("pbrain:"):
        rest = spec.split(":", 1)[1]
        if "=" in rest:
            name, exe = rest.split("=", 1)
        else:
            exe = rest
            name = os.path.splitext(os.path.basename(exe))[0]
        return PBrainPlayer(
            name,
            exe,
            args.turn_time_ms,
            args.threads,
            depth=args.depth,
            start_timeout=args.start_timeout,
            board_mode=args.pbrain_board_mode,
        )
    raise ValueError("unknown player spec: %s" % spec)


def play_game(black, white, args):
    players = {BLACK: black, WHITE: white}
    steps = parse_steps(args.initial)
    move_log = []
    terminal = winner(steps)
    illegal = None
    start_time = time.time()
    try:
        black.start_game(BLACK)
        white.start_game(WHITE)
        while terminal is None and len(steps) < args.max_moves:
            turn = color_to_move(steps)
            player = players[turn]
            before = steps_to_string(steps)
            started = time.time()
            result = player.move(steps, args.game_id)
            move = result["move"]
            elapsed_ms = int((time.time() - started) * 1000)
            if not is_legal(steps, move):
                illegal = {"player": player.name, "move": move, "position": before, "reason": "illegal_move"}
                terminal = "WHITE" if turn == BLACK else "BLACK"
                break
            steps.append(move)
            other = players[WHITE if turn == BLACK else BLACK]
            other.observe(move)
            move_log.append(
                {
                    "ply": len(steps),
                    "turn": "BLACK" if turn == BLACK else "WHITE",
                    "player": player.name,
                    "move": move,
                    "elapsed_ms": elapsed_ms,
                    "raw": result.get("raw", {}),
                    "steps": steps_to_string(steps),
                }
            )
            if args.verbose:
                print(json.dumps(move_log[-1], ensure_ascii=False), flush=True)
            terminal = winner(steps)
        if terminal is None:
            terminal = "DRAW" if len(steps) >= BOARD_SIZE * BOARD_SIZE else "MAX_MOVES"
        return {
            "black_player": black.name,
            "white_player": white.name,
            "winner": terminal,
            "moves": len(steps),
            "steps": steps_to_string(steps),
            "illegal": illegal,
            "elapsed_ms": int((time.time() - start_time) * 1000),
            "settings": {
                "depth": args.depth,
                "threads": args.threads,
                "turn_time_ms": args.turn_time_ms,
                "max_moves": args.max_moves,
                "initial": steps_to_string(parse_steps(args.initial)),
                "white_target": args.white_target,
                "resolved_white_target": getattr(white, "last_resolved_target", getattr(white, "target", None)),
                "deep_tactics": args.deep_tactics,
                "pbrain_board_mode": args.pbrain_board_mode,
            },
            "move_log": move_log,
        }
    finally:
        black.close()
        white.close()


def compact_result(result):
    return {
        "black_player": result["black_player"],
        "white_player": result["white_player"],
        "winner": result["winner"],
        "moves": result["moves"],
        "steps": result["steps"],
        "illegal": result["illegal"],
        "elapsed_ms": result["elapsed_ms"],
        "settings": result["settings"],
    }


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--black", required=True)
    parser.add_argument("--white", required=True)
    parser.add_argument("--http-base", default="http://127.0.0.1:8090")
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--turn-time-ms", type=int, default=500)
    parser.add_argument("--max-moves", type=int, default=120)
    parser.add_argument("--initial", default="")
    parser.add_argument("--start-timeout", type=int, default=60)
    parser.add_argument("--pbrain-board-mode", action="store_true")
    parser.add_argument("--white-target", default="auto", choices=WHITE_TARGET_CHOICES)
    parser.add_argument("--deep-tactics", action="store_true")
    parser.add_argument("--http-timeout", type=float, default=None)
    parser.add_argument("--game-id", default="pbrain_match")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    black = make_player(args.black, BLACK, args)
    white = make_player(args.white, WHITE, args)
    result = play_game(black, white, args)
    if args.compact:
        result = compact_result(result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
