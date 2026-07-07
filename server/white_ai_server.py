import json
import math
import os
import platform
import queue
import re
# PBrain/proof engines are configured local executables and are always called without shell=True.
import subprocess  # nosec B404
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import leveldb
import tornado.ioloop
import tornado.web


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
UPSTREAM_SCRIPT_DIR = os.environ.get(
    "UPSTREAM_SCRIPT_DIR",
    os.path.join(PROJECT_ROOT, "upstream", "gomoku", "script"),
)
RAPFI_DIR = os.environ.get("RAPFI_DIR", os.path.join(PROJECT_ROOT, "engines", "rapfi"))
RAPFI_EXE = os.environ.get("RAPFI_EXE", os.path.join(RAPFI_DIR, "pbrain-rapfi"))
WEB_SEARCH_EXE = os.environ.get("WEB_SEARCH_EXE", os.path.join(BASE_DIR, "web_search"))
WHITE_RAPFI_MS = int(os.environ.get("WHITE_RAPFI_MS", os.environ.get("WHITE_TURN_TIME_MS", "5000")))
WHITE_RAPFI_DEPTH = int(os.environ.get("WHITE_RAPFI_DEPTH", "64"))
WHITE_RAPFI_THREADS = int(os.environ.get("WHITE_RAPFI_THREADS", "4"))
WHITE_RAPFI_HASH_KB = int(os.environ.get("WHITE_RAPFI_HASH_KB", "131072"))
SEARCH_BLACK_MS = int(
    os.environ.get(
        "SEARCH_BLACK_MS",
        os.environ.get("SEARCH_TURN_TIME_MS", "5000"),
    )
)
SEARCH_BLACK_DEPTH = int(os.environ.get("SEARCH_BLACK_DEPTH", "64"))
SEARCH_BLACK_THREADS = int(os.environ.get("SEARCH_BLACK_THREADS", "4"))
SEARCH_BLACK_HASH_KB = int(os.environ.get("SEARCH_BLACK_HASH_KB", "131072"))
SEARCH_BLACK_CAND_RANGE = int(os.environ.get("SEARCH_BLACK_CAND_RANGE", "3"))
GOMOCUP_ENGINE_ROOT = os.environ.get(
    "GOMOCUP_ENGINE_ROOT",
    os.path.join(PROJECT_ROOT, "engines", "gomocup"),
)
GOMOCUP_ADVISORS = [
    ("rapfi25", os.path.join(GOMOCUP_ENGINE_ROOT, "RAPFI25", "pbrain-rapfi_avx2.exe"), 350),
    ("katagomo26_f15", os.path.join(GOMOCUP_ENGINE_ROOT, "KATAGOMO26", "pbrain-katagomo_freestyle-15.exe"), 250),
    ("alphagomoku_mk26", os.path.join(GOMOCUP_ENGINE_ROOT, "ALPHAGOMOKU.MK26", "pbrain-AlphaGomoku.exe"), 170),
    ("jax25", os.path.join(GOMOCUP_ENGINE_ROOT, "JAX25", "pbrain-Jax.exe"), 100),
    ("vibefive26", os.path.join(GOMOCUP_ENGINE_ROOT, "VIBEFIVE", "pbrain-vibefive.exe"), 50),
    ("embryo26_f", os.path.join(GOMOCUP_ENGINE_ROOT, "EMBRYO26", "pbrain-embryo26_f.exe"), 30),
    ("yixin18", os.path.join(GOMOCUP_ENGINE_ROOT, "YIXIN18", "pbrain-Yixin2018.exe"), 20),
    ("starpoint26_f15", os.path.join(GOMOCUP_ENGINE_ROOT, "STARPOINT", "pbrain-starpoint_freestyle-15.exe"), 20),
    ("pentazen21_15", os.path.join(GOMOCUP_ENGINE_ROOT, "PENTAZEN21.15", "pbrain-PentaZen21_15.exe"), 15),
    ("skyzero26", os.path.join(GOMOCUP_ENGINE_ROOT, "SKYZERO", "pbrain-SkyZero.exe"), 10),
]
GOMOCUP_VOTING_EXCLUDE = {
    name.strip()
    for name in os.environ.get("GOMOCUP_VOTING_EXCLUDE", "embryo26_f").split(",")
    if name.strip()
}
GOMOCUP_VOTING_ADVISORS = [advisor for advisor in GOMOCUP_ADVISORS if advisor[0] not in GOMOCUP_VOTING_EXCLUDE]
GOMOCUP_ADVISOR_MAX_WORKERS = int(os.environ.get("GOMOCUP_ADVISOR_MAX_WORKERS", str(len(GOMOCUP_ADVISORS))))
GOMOCUP_ADVISOR_MEMORY_BYTES = int(os.environ.get("GOMOCUP_ADVISOR_MEMORY_BYTES", "536870912"))
GOMOCUP_ADVISOR_PERSISTENT = os.environ.get(
    "GOMOCUP_ADVISOR_PERSISTENT",
    "1",
).strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
)
GOMOCUP_ADVERSARY_VALIDATION = os.environ.get("GOMOCUP_ADVERSARY_VALIDATION", "0").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
)
GOMOCUP_ADVERSARY_TOP_N = int(os.environ.get("GOMOCUP_ADVERSARY_TOP_N", "4"))
GOMOCUP_ADVERSARY_ADVISORS = int(os.environ.get("GOMOCUP_ADVERSARY_ADVISORS", "3"))
ENGINE_WORKERS = int(os.environ.get("ENGINE_WORKERS", "1"))
ENGINE_EXECUTOR = ThreadPoolExecutor(max_workers=max(1, ENGINE_WORKERS))

# Benchmark-derived resistance moves. These are deliberately kept as a
# small, explicit book so the experimental white AI can prefer verified
# longest-resistance branches without changing either black engine.
GENERAL_SEARCH_RESISTANCE_BOOK = {}


def add_resistance_line(line, bonus, tag, book=None, overwrite=False, min_prefix_len=1):
    book = book if book is not None else GENERAL_SEARCH_RESISTANCE_BOOK
    moves = [move for move in line.strip().strip("_").split("_") if move]
    for i in range(1, len(moves), 2):
        if i < min_prefix_len:
            continue
        if overwrite:
            book[tuple(moves[:i])] = (moves[i], bonus, tag)
        else:
            book.setdefault(tuple(moves[:i]), (moves[i], bonus, tag))


GENERAL_SEARCH_RESISTANCE_BOOK[("h8",)] = ("i8", 420_000, "opening_probe")

add_resistance_line(
    "_h8_i8_i7_g9_j7_g7_j8_h6_j6_j5_k7_h7_l6_i9_k6_m6_l8_i5_j10_j9_l4_k5_l5_l7_m4_n3_n4_m5_k4_o4_j4",
    260_000,
    "proof_tree_book",
)
add_resistance_line(
    "_h8_g10_g7_i9_h7_h9_i7_j7_i8_j9_g9_j6_j8_g8_f7_e7_h6_g5_k9_l10_f10_e11_i5_j4_i4_i6_f8_e9_h5_h4_g6_j3_e8",
    300_000,
    "proof_tree_book",
)
add_resistance_line(
    "_h8_i8_j7_i6_i7_j6_h6_h7_g5_f4_g8_g4_g6_h4_e4_i5_g3_i4_j4_j5_h3_k4_l3_l5_g9_g7_k9_j8_f10_e11_k5_i3_i2_k7_l8_m6_n7_l6_k6_m5_n4_i9",
    520_000,
    "general_search_win_book",
)
add_resistance_line(
    "_h8_i8_j7_i6_i7_j6_h6_h7_g5_f4_g8_g4_g6_h4_i4_g7_f7_h5_e6_d5_c1_f3_e2_e4_d4_g2_h1_c6",
    650_000,
    "general_search_i4_win_book",
)
add_resistance_line(
    "_h8_i8_j7_i6_i7_j6_h6_h7_g5_f4_g8_g4_g6_h4_i4_g7_f7_h5_e6_d5_d6_f6_e4_h9_e8_f3_e2_e3_b1_f2_f5_g3_i5_d3_h3_c3",
    720_000,
    "general_search_i4_d6_fast_win_book",
)
add_resistance_line(
    "_h8_i8_j7_i6_i7_j6_h6_h7_g5_f4_g8_g4_g6_h4_i4_g7_f7_h5_e6_d5_e4_c1_k7_g3_a1_f3_e2_f2_i5_f5_f6_f1",
    740_000,
    "general_search_i4_e4_fast_win_book",
)
GENERAL_SEARCH_RESISTANCE_BOOK[
    (
        "h8",
        "i8",
        "j7",
        "i6",
        "i7",
        "j6",
        "h6",
        "h7",
        "g5",
        "f4",
        "g8",
        "g4",
        "g6",
        "h4",
        "i4",
        "g7",
        "f7",
        "h5",
        "e6",
        "d5",
        "e4",
    )
] = ("c1", 740_000, "general_search_i4_e4_fast_win_book")
add_resistance_line(
    "_h8_i8_j7_i6_i7_j6_h6_h7_g5_f4_g8_g4_g6_h4_i4_e4_d4_g7_f7_h5_a1_e6_f3_j8_k7_l7_b1_c1_e8_e5_e2_e3_e7_f8_d1_d9_e1_f1_g1_g3_h2_d6_c7_i5_f2_d2_h1_i1_j1_d7_i2_g2_h3_d8_d10_d5",
    760_000,
    "general_search_i4_long_win_book",
)
add_resistance_line(
    "_h8_i8_j7_i6_i7_j6_h6_h7_g5_f4_g8_g4_g6_h4_i4_g7_f7_h5_e6_d5_d6_f6_e4_h3_g3_i2_h2_f5_j1_f3_e2_f2",
    860_000,
    "general_search_e4_h3_fast_win_book",
    overwrite=True,
    min_prefix_len=23,
)
add_resistance_line(
    "_h8_i8_j7_i6_i7_j6_h6_h7_g5_f4_g8_g4_g6_h4_i4_g7_f7_h5_e6_d5_d6_f6_c1_f3_e2_e4_d4_g2_h1_c6",
    900_000,
    "general_search_30_fast_win_book",
    overwrite=True,
)
add_resistance_line(
    "_h8_i8_j7_i6_i7_j6_g6_h9_g7_f7_g5_g8_i10_h6_k7_h7_f9_g4_e6_h3_h4_j5_k4_k6_l6_i4_l7_g2",
    880_000,
    "general_search_early_g6_h9_win_book",
    overwrite=True,
    min_prefix_len=7,
)
add_resistance_line(
    "_h8_i8_j7_i6_i7_j6_h6_h7_g5_f4_g8_g4_g6_h4_i4_g7_f7_h5_e6_d5_d6_f6_f3_e8_f10_c5_c1_d4_e4_e5_c3_b5_f5_a5",
    870_000,
    "general_search_f3_e8_win_book",
    overwrite=True,
    min_prefix_len=23,
)
add_resistance_line(
    "_h8_i8_j7_i6_i7_j6_h6_h7_g5_f4_g8_g4_g6_h4_i4_g7_c1_f7_f5_e5_d6_e4_d4_e7_d7_e6_e8_e3",
    880_000,
    "general_search_early_c1_f5_e5_win_book",
    overwrite=True,
    min_prefix_len=19,
)
add_resistance_line(
    "_h8_i8_j7_i6_i7_j6_h6_h7_g5_f4_g8_g4_g6_h4_i4_g7_f7_h5_h9_i10_c1_e6_f9_f3_e2_f5_j8_k9_f1_h3_i2_d7",
    870_000,
    "general_search_h9_i10_win_book",
    overwrite=True,
    min_prefix_len=19,
)
add_resistance_line(
    "_h8_i8_j7_i6_i7_j6_h6_h7_g5_f4_g8_g4_g6_h4_i4_g7_f7_h5_e6_d5_d6_f6_e4_h3_f3_b1_e8_e5_a1_h2_h1_g3_i1_i5_k7_f2",
    870_000,
    "general_search_h3_f3_b1_win_book",
    overwrite=True,
    min_prefix_len=25,
)
add_resistance_line(
    "_h8_i8_j7_i6_i7_j6_h6_h7_g5_f4_g8_g4_g6_h4_i4_g7_f7_h5_e6_d5_e4_c1_k7_g3_f3_f6_a1_e5_h2_d4_c3_d6_c7_d3_d7_d2",
    870_000,
    "general_search_e4_c1_f3_f6_win_book",
    overwrite=True,
    min_prefix_len=25,
)
add_resistance_line(
    "_h8_i8_j7_i6_i7_j6_h6_h7_g5_f4_g8_g4_g6_h4_i4_g7_f7_h5_e6_d5_e4_c1_a1_j5_e5_k4_l3_e7_k7_l5_b1_f3_e2_e3_d1_i5_k5_g3_f2_d3_h3_c3",
    870_000,
    "general_search_e4_c1_a1_j5_win_book",
    overwrite=True,
    min_prefix_len=23,
)
add_resistance_line(
    "_h8_f6_i7_g5_i8_f8",
    220_000,
    "proof_tree_probe",
)
GENERAL_SEARCH_RESISTANCE_BOOK[
    (
        "h8",
        "f6",
        "g6",
        "e5",
        "h5",
        "f7",
        "h7",
        "h6",
        "f5",
        "i8",
        "g4",
        "i6",
        "b1",
        "g5",
        "h3",
        "i2",
        "i4",
        "f4",
        "i7",
    )
] = ("e3", 200_000, "general_search_probe")

PROOF_TREE_RESISTANCE_BOOK = dict(GENERAL_SEARCH_RESISTANCE_BOOK)
PROOF_TREE_RESISTANCE_BOOK[("h8",)] = ("g6", 900_000, "proof_tree_g6_longest_probe")
add_resistance_line(
    "_h8_g6_g9_i7_h9_h7_i9_j9_i8_j7_g7_j10_j8_g8_f9_e9_h10_k7_l7_f8_h11_h12_g11_f12_i12_g10_l8_k8_l9_l10_i11_i10_f11_j11_e11",
    880_000,
    "proof_tree_g6_longest_probe",
    book=PROOF_TREE_RESISTANCE_BOOK,
)

VIBEFIVE_RESISTANCE_BOOK = dict(GENERAL_SEARCH_RESISTANCE_BOOK)
VIBEFIVE_RESISTANCE_BOOK[("h8",)] = ("g8", 900_000, "vibefive_h8_g8_longer_probe")
VIBEFIVE_RESISTANCE_BOOK[("h8", "i8", "j9", "i9", "h10")] = (
    "g10",
    940_000,
    "vibefive_h10_g10_draw_regression",
)
add_resistance_line(
    "_h8_g8_f7_g6_g9_f10_e7_g7_g5_f8_h6_i7_h4_d8_h5_h7_f5_e5_h3_h2_g4_j7_k7_c8_e8_e6_i5_j5_j6_l8_g3",
    700_000,
    "vibefive_h8_g8_longer_probe",
    book=VIBEFIVE_RESISTANCE_BOOK,
    overwrite=True,
)
add_resistance_line(
    "_h8_g8_f7_g6_g9_f6_h9_h6_i6_i7_h10_h11_i9_j9_i11_f8_i10_i8_i12_i13_k13_j12_k10_h7_f5_e6_d6_j10_j11_l9_k12_l13_k11_k14_k9",
    820_000,
    "vibefive_h8_g8_f6_35_probe",
    book=VIBEFIVE_RESISTANCE_BOOK,
    overwrite=True,
    min_prefix_len=5,
)

JAX_RESISTANCE_BOOK = dict(PROOF_TREE_RESISTANCE_BOOK)
JAX_RESISTANCE_BOOK[("g8",)] = ("h6", 900_000, "jax_g8_h6_31_probe")
JAX_RESISTANCE_BOOK[("h8",)] = ("j9", 920_000, "jax_h8_j9_33_probe")
JAX_RESISTANCE_BOOK[("h7",)] = ("g9", 900_000, "jax_h7_g9_35_probe")
JAX_RESISTANCE_BOOK[("i8",)] = ("j9", 900_000, "jax_i8_j9_33_probe")
add_resistance_line(
    "_g8_h6_f7_h9_h7_f9_g7_i7_g9_g6_e7_d7_f8_d6_e8_d8_d9_e10_h8_i8_e5_d4_d5_e6_f6_i9_f5_f4_g5_h5_c5",
    780_000,
    "jax_g8_h6_31_probe",
    book=JAX_RESISTANCE_BOOK,
    overwrite=True,
)
add_resistance_line(
    "_h8_j9_i7_g9_j8_h6_i9_i8_k7_l6_j10_k11_k10_i10_j7_h7_k8_k9_l9_m10_m8_n7_j6_g6_f5_n8_i5_h4_h5_i6_j5_j4_g5",
    800_000,
    "jax_h8_j9_33_probe",
    book=JAX_RESISTANCE_BOOK,
    overwrite=True,
)
JAX_RESISTANCE_BOOK[("h8", "j9", "h7")] = ("i7", 900_000, "jax_h8_j9_h7_i7_35_probe")
add_resistance_line(
    "_h8_j9_h7_i7_g8_h6_j8_i8_i9_h10_f9_i6_f6_g7_f8_f7_e8_d8_e10_d11_e9_e7_d9_d7_c7_c9_f11_g12_e11_e12_g9_h9_f10_f12_d12",
    860_000,
    "jax_h8_j9_h7_i7_35_probe",
    book=JAX_RESISTANCE_BOOK,
    overwrite=True,
    min_prefix_len=3,
)
JAX_RESISTANCE_BOOK[("h8", "j9", "h10")] = ("h7", 940_000, "jax_h8_j9_h10_h7_47_probe")
add_resistance_line(
    "_h8_j9_h10_h7_i8_g8_g9_i7_g7_f8_f10_i10_i9_j10_j8_g11_h9_f9_e10_g10_e8_e11_h11_h12_d9_i6_j5_k8_c10_f7_c8_f6_f5_l7_m6_f11_e6_g4_b9_d7_b10_d10_b7_a6_b8_b11_b6",
    900_000,
    "jax_h8_j9_h10_h7_47_probe",
    book=JAX_RESISTANCE_BOOK,
    overwrite=True,
    min_prefix_len=3,
)
JAX_RESISTANCE_BOOK[("h8", "j9", "i7", "g9", "j8")] = ("i9", 860_000, "jax_h8_j9_i7_g9_j8_i9_31_probe")
add_resistance_line(
    "_h8_j9_i7_g9_j8_i9_h9_h6_k10_g8_k8_i8_k9_k7_l10_m11_m10_j10_l9_j7_l11_l12_l8_l7_n8_m8_k11_k12_m9_o7_j12",
    760_000,
    "jax_h8_j9_i7_g9_j8_i9_31_probe",
    book=JAX_RESISTANCE_BOOK,
    overwrite=True,
    min_prefix_len=5,
)
add_resistance_line(
    "_i8_j9_k9_i7_j10_l8_h8_l7_k8_k7_j7_j6_i5_l6_l9_m9_n10_m10_i9_k11_h9_l5_l4_k6_g8_j8_g7_f6_f8_e8_h6_j4_e9",
    800_000,
    "jax_i8_j9_33_probe",
    book=JAX_RESISTANCE_BOOK,
    overwrite=True,
)
add_resistance_line(
    "_h7_g9_i8_g6_h9_h8_g10_f11_i7_j7_i10_i9_h11_g8_j10_h10_j9_k8_i12_j13_j11_g7_g5_f6_e5_i11_k10_l11_j12_j8_k12_l13_g12_h12_f13",
    820_000,
    "jax_h7_g9_35_probe",
    book=JAX_RESISTANCE_BOOK,
    overwrite=True,
)
JAX_RESISTANCE_BOOK[("h7", "g9", "h6")] = ("i8", 900_000, "jax_h7_g9_h6_i8_37_probe")
add_resistance_line(
    "_h7_g9_h6_i8_i7_j7_h9_h8_g8_f7_g5_j8_j5_i6_h5_i5_h4_h3_f4_e3_g4_e4_i3_j2_g3_g2_h2_k8_l8_l9_m10_e5_j4_i4_k5_l6_g1",
    860_000,
    "jax_h7_g9_h6_i8_37_probe",
    book=JAX_RESISTANCE_BOOK,
    overwrite=True,
    min_prefix_len=3,
)
JAX_RESISTANCE_BOOK[
    (
        "h8",
        "i7",
        "k10",
        "g7",
        "k7",
        "g8",
        "g6",
        "h7",
        "f7",
        "i6",
        "j5",
        "f9",
        "e10",
        "i5",
        "i4",
    )
] = ("h5", 900_000, "official_f15_opening2_jax_h5_39_probe")
JAX_RESISTANCE_BOOK[("h8", "j9", "i7")] = ("h9", 880_000, "jax_natural_h9_33_probe")
JAX_RESISTANCE_BOOK[("g7",)] = ("f9", 880_000, "jax_first_g7_f9_33_probe")
JAX_RESISTANCE_BOOK[("g8",)] = ("f8", 880_000, "jax_first_g8_f8_31_probe")
JAX_RESISTANCE_BOOK[("g8", "f8", "e9")] = ("f10", 880_000, "jax_g8_f8_e9_f10_29_probe")
JAX_RESISTANCE_BOOK[("g8", "f8", "e7", "e6", "f9", "h7", "e9")] = ("e8", 900_000, "jax_g8_f8_e7_e6_e9_e8_35_probe")
JAX_RESISTANCE_BOOK[("g9", "h8", "i8", "g10", "h7", "j9", "g7")] = ("f7", 880_000, "jax_g9_h8_i8_g10_g7_f7_29_probe")
JAX_RESISTANCE_BOOK[("g7", "f9", "h8", "e8", "g10")] = ("g8", 900_000, "jax_g7_f9_h8_e8_g10_g8_min25_avg27_r8")
JAX_RESISTANCE_BOOK[("h8", "j9", "i7", "h9", "g9", "j6", "h10")] = ("g10", 900_000, "jax_h8_j9_i7_h9_g9_j6_h10_g10_min23_avg27_r16")
JAX_RESISTANCE_BOOK[("h8", "j9", "h7", "i7", "g8", "h6", "i6", "f9", "g5", "j8", "h5")] = ("k9", 900_000, "jax_h8_j9_h7_i7_g8_h6_i6_f9_g5_j8_h5_k9_min27_avg29_r8")
JAX_RESISTANCE_BOOK[("h9", "h8", "g7", "f7", "i8", "g10", "g6", "f10", "i6", "e10", "h10")] = ("f9", 900_000, "jax_h9_h8_g7_f7_i8_g10_g6_f10_i6_e10_h10_f9_min29_avg30_r8")
JAX_RESISTANCE_BOOK[("h8", "j9", "g9", "i7", "g8", "i8", "h7", "i6", "i9", "g7", "f8", "i5", "i4")] = ("h6", 900_000, "jax_h8_j9_g9_i7_g8_i8_h7_i6_i9_g7_f8_i5_i4_h6_min25_avg27_r8")
JAX_RESISTANCE_BOOK[("h7", "g9", "i7", "f8", "h6")] = ("g5", 900_000, "jax_h7_g9_i7_f8_h6_g5_min27_avg27_r8")
JAX_RESISTANCE_BOOK[("h7", "g9", "h6")] = ("g6", 880_000, "jax_h7_g9_h6_g6_35_probe")
JAX_RESISTANCE_BOOK[("i8",)] = ("j8", 880_000, "jax_first_i8_j8_33_probe")
JAX_RESISTANCE_BOOK[("i8", "j8", "k7")] = ("j9", 880_000, "jax_i8_j8_k7_j9_33_probe")
JAX_RESISTANCE_BOOK[
    ("i8", "j8", "k7", "j9", "j10", "i10", "k9", "k8", "l7", "j7", "l8", "j6", "j5")
] = ("i11", 880_000, "jax_i8_j8_k7_j9_j5_i11_43_probe")
JAX_RESISTANCE_BOOK[("i9",)] = ("j10", 860_000, "jax_first_i9_j10_29_probe")
JAX_RESISTANCE_BOOK[("j8",)] = ("k7", 880_000, "jax_first_j8_k7_31_probe")

KATAGOMO_RESISTANCE_BOOK = dict(PROOF_TREE_RESISTANCE_BOOK)
KATAGOMO_RESISTANCE_BOOK[("i7",)] = ("j6", 900_000, "katagomo_i7_j6_29_probe")
add_resistance_line(
    "_i7_j6_i8_i9_h7_g7_j7_k7_h9_k6_h8_h6_h10_h11_g6_j9_i10_g10_g8_l6_i6_j8_m5_m6_n6_f7_j5_k4_f9",
    780_000,
    "katagomo_i7_j6_29_probe",
    book=KATAGOMO_RESISTANCE_BOOK,
    overwrite=True,
)
KATAGOMO_RESISTANCE_BOOK[("i7", "j6", "j8")] = ("h6", 900_000, "katagomo_i7_j6_j8_h6_47_probe")
add_resistance_line(
    "_i7_j6_j8_h6_k7_i9_i6_h7_h5_j7_h9_i4_g7_g4_h4_f5_e6_h3_j5_g3_f3_i2_j1_i3_k5_i5_i1_g2_g6_g5_g1_k1_f7_d5_k8_k4_i10_g8_k9_k6_l10_m11_k10_k11_j10_m10_h10",
    860_000,
    "katagomo_i7_j6_j8_h6_47_probe",
    book=KATAGOMO_RESISTANCE_BOOK,
    overwrite=True,
    min_prefix_len=3,
)

GOMOCUP_RESISTANCE_BOOK = {}
OFFICIAL_F15_OPENING2_BOOK = {
    ("h8", "i7", "k10", "g7", "k7"): ("g8", 950_000, "official_f15_opening2_g8_consensus"),
    ("h8", "i7", "k10", "g7", "k7", "g8", "g6"): ("h7", 950_000, "official_f15_opening2_h7_consensus"),
    ("h8", "i7", "k10", "g7", "k7", "g8", "g6", "h7", "f7"): ("i6", 950_000, "official_f15_opening2_i6_consensus"),
}
for _book in (GENERAL_SEARCH_RESISTANCE_BOOK, VIBEFIVE_RESISTANCE_BOOK, JAX_RESISTANCE_BOOK, KATAGOMO_RESISTANCE_BOOK, GOMOCUP_RESISTANCE_BOOK):
    _book.update(OFFICIAL_F15_OPENING2_BOOK)
add_resistance_line(
    "_h8_e5_b2_f5_g5_f4_f6_h4_g4_g3_h2_f3_f2_e4_g2_e2_e3_g6_h7_c4_d3_e8_i2_j2_e7_c6_d8_c9_c5_d5_b7_c7_d6_c10_c8_f7_d9_e6_b3_g8",
    920_000,
    "alphagomoku_natural_40_win_regression",
    book=GOMOCUP_RESISTANCE_BOOK,
    overwrite=True,
)
add_resistance_line(
    "_h8_i8_j7_i6_i7_j6_k7_h7_g6_l7_k6_g8_f9_m6_k4_k5_j9_n5_m5_l4_l6_n4_n2_k8_o4_i9_g5_i10_g4_g3_j11_j10_h10_i11_i12_h12_k9_l10_k10_l9_l11_g11_m12_n13_h6_j8_h4_i4_f6_i3_f4_e3_d4_e4_e5_g7_d6_e6_b8_c7_d8_e7_d5_d7_f5_f7",
    920_000,
    "chloris_natural_66_win_regression",
    book=GENERAL_SEARCH_RESISTANCE_BOOK,
    overwrite=True,
    min_prefix_len=19,
)
GOMOCUP_RESISTANCE_BOOK[("h8", "e5", "j10", "g7", "h10")] = (
    "d6",
    980_000,
    "starpoint_e5_d6_win_regression",
)
GOMOCUP_RESISTANCE_BOOK[("h8", "e5", "f9", "f5", "g9")] = (
    "e6",
    980_000,
    "embryo_e5_e6_win_regression",
)

TARGET_BOOKS = {
    "general_search": GENERAL_SEARCH_RESISTANCE_BOOK,
    "proof_tree": PROOF_TREE_RESISTANCE_BOOK,
    "vibefive": VIBEFIVE_RESISTANCE_BOOK,
    "jax": JAX_RESISTANCE_BOOK,
    "katagomo": KATAGOMO_RESISTANCE_BOOK,
    "generic": {},
    "gomocup": GOMOCUP_RESISTANCE_BOOK,
    "ensemble": {},
    "advisor": {},
    "advisor_ensemble": {},
    "auto": {},
}
DIRECT_ADVISOR_TARGETS = {name for name, _exe, _weight in GOMOCUP_ADVISORS}
DIRECT_ADVISOR_ALIASES = {
    "gomocup_top": "rapfi25",
}
for _direct_advisor_target in DIRECT_ADVISOR_TARGETS:
    TARGET_BOOKS[_direct_advisor_target] = {}
for _direct_advisor_alias in DIRECT_ADVISOR_ALIASES:
    TARGET_BOOKS[_direct_advisor_alias] = {}

ENSEMBLE_BOOKS = {
    "general_search": GENERAL_SEARCH_RESISTANCE_BOOK,
    "proof_tree": PROOF_TREE_RESISTANCE_BOOK,
    "vibefive": VIBEFIVE_RESISTANCE_BOOK,
    "jax": JAX_RESISTANCE_BOOK,
    "katagomo": KATAGOMO_RESISTANCE_BOOK,
}

WHITE_TARGET_ALIASES = {
    "proof": "proof_tree",
    "proof_tree_black": "proof_tree",
    "first_player": "proof_tree",
    "first_player_win": "proof_tree",
    "search": "general_search",
    "search_black": "general_search",
    "general_search_black": "general_search",
    "rapfi": "general_search",
}
DEFAULT_WHITE_TARGET = os.environ.get("WHITE_TARGET", "proof_tree").lower()
DB_REVERSE_TARGETS = {"general_search", "proof_tree", "vibefive", "jax", "katagomo"}
AUTO_DIRECT_EXACT_BOOK_BASE_TARGETS = {"vibefive"}
ADVISOR_TARGETS = {"advisor"}
ADVISOR_ENSEMBLE_TARGETS = {"advisor_ensemble"}
AUTO_TARGETS = {"auto"}


def normalize_white_target(target):
    target = (target or DEFAULT_WHITE_TARGET or "proof_tree").strip().lower()
    target = WHITE_TARGET_ALIASES.get(target, target)
    return target if target in TARGET_BOOKS else "proof_tree"


def direct_advisor_spec(target):
    target = DIRECT_ADVISOR_ALIASES.get(target, target)
    for name, exe, weight in GOMOCUP_ADVISORS:
        if name == target:
            return name, exe, weight
    return None


def resolve_auto_base_target(opponent):
    opponent = (opponent or "").strip().lower()
    if (
        opponent in ("", "proof_tree", "proof_tree_black", "first_player", "first_player_win")
        or "proof_tree" in opponent
        or "first_player" in opponent
    ):
        return "proof_tree"
    if "alphagomoku" in opponent:
        return "gomocup"
    if "rapfi" in opponent:
        return "general_search"
    if "general_search" in opponent or "search_black" in opponent:
        return "general_search"
    if "vibefive" in opponent:
        return "vibefive"
    if "chloris" in opponent:
        return "general_search"
    if "katagomo" in opponent:
        return "katagomo"
    if "jax" in opponent:
        return "jax"
    return "gomocup"


def resolve_auto_white_target(opponent):
    opponent = (opponent or "").strip().lower()
    if (
        opponent in ("", "proof_tree", "proof_tree_black", "first_player", "first_player_win")
        or "proof_tree" in opponent
        or "first_player" in opponent
    ):
        return "proof_tree", "proof_tree"
    if "alphagomoku" in opponent:
        return "jax25", "gomocup"
    if "yixin" in opponent:
        return "alphagomoku_mk26", "gomocup"
    if "embryo" in opponent:
        return "gomocup", "gomocup"
    if "general_search" in opponent or "search_black" in opponent or "rapfi" in opponent or "chloris" in opponent:
        return "advisor_ensemble", "general_search"
    if "slowrenju" in opponent:
        return "alphagomoku_mk26", resolve_auto_base_target(opponent)
    if any(name in opponent for name in ("jax", "vibefive", "skyzero", "stardust")):
        return "vibefive26", resolve_auto_base_target(opponent)
    if "pentazen" in opponent:
        return "vibefive26", resolve_auto_base_target(opponent)
    if "katagomo" in opponent:
        return "alphagomoku_mk26", resolve_auto_base_target(opponent)
    if any(name in opponent for name in ("rapfi", "chloris", "starpoint")):
        return "advisor_ensemble", resolve_auto_base_target(opponent)
    return "advisor_ensemble", resolve_auto_base_target(opponent)

sys.path.insert(0, UPSTREAM_SCRIPT_DIR)
from divided_solution_manager import find_next_steps_from_db  # noqa: E402


db = leveldb.LevelDB(os.path.join(BASE_DIR, "leveldb.db"))
db_cache = {}
resistance_cache = {}
MOVE_RE = re.compile(r"^[a-o](?:[1-9]|1[0-5])$")


def parse_steps(raw):
    raw = (raw or "").strip().strip("_")
    if raw == "":
        return []
    steps = [m for m in raw.split("_") if m]
    seen = set()
    for move in steps:
        if not MOVE_RE.match(move):
            raise ValueError("invalid move token: %s" % move)
        point = move_to_xy(move)
        if point in seen:
            raise ValueError("duplicate move: %s" % move)
        seen.add(point)
    return steps


def move_to_xy(move):
    return ord(move[0]) - ord("a"), int(move[1:]) - 1


def xy_to_move(x, y):
    return "%s%s" % (chr(ord("a") + x), y + 1)


def steps_to_string(steps):
    return "_".join(steps)


def occupied(steps):
    return {move_to_xy(m) for m in steps}


def legal_moves_near(steps, radius=2, limit=None):
    occ = occupied(steps)
    if not steps:
        return ["h8"]

    candidates = set()
    for x, y in occ:
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                nx, ny = x + dx, y + dy
                if 0 <= nx < 15 and 0 <= ny < 15 and (nx, ny) not in occ:
                    candidates.add((nx, ny))

    moves = [xy_to_move(x, y) for x, y in candidates]
    moves.sort(key=lambda m: candidate_heuristic(steps, m), reverse=True)
    return moves[:limit] if limit else moves


def color_at(steps):
    board = {}
    for i, move in enumerate(steps):
        board[move_to_xy(move)] = 1 if i % 2 == 0 else 2
    return board


def has_five(steps, color):
    board = color_at(steps)
    dirs = [(1, 0), (0, 1), (1, 1), (1, -1)]
    for (x, y), piece in board.items():
        if piece != color:
            continue
        for dx, dy in dirs:
            px, py = x - dx, y - dy
            if board.get((px, py)) == color:
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


def immediate_winning_moves(steps, color):
    board = color_at(steps)
    candidates = set()
    for (x, y), piece in board.items():
        if piece != color:
            continue
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if 0 <= nx < 15 and 0 <= ny < 15 and (nx, ny) not in board:
                    candidates.add((nx, ny))
    wins = []
    for x, y in candidates:
        move = xy_to_move(x, y)
        if has_five(steps + [move], color):
            wins.append(move)
    wins.sort()
    return wins


def white_has_near_safe_reply(after_black_steps, limit=72):
    for white_move in legal_moves_near(after_black_steps, radius=2, limit=limit):
        after_white = after_black_steps + [white_move]
        if has_five(after_white, 2):
            return True
        if not immediate_winning_moves(after_white, 1):
            return True
    return False


def black_two_step_threats(after_white_steps, black_limit=36, white_limit=72):
    threats = []
    for black_move in legal_moves_near(after_white_steps, radius=2, limit=black_limit):
        after_black = after_white_steps + [black_move]
        if has_five(after_black, 1):
            threats.append({"move": black_move, "type": "immediate"})
        elif not white_has_near_safe_reply(after_black, limit=white_limit):
            threats.append({"move": black_move, "type": "no_near_safe_white_reply"})
    return threats


def candidate_heuristic(steps, move):
    x, y = move_to_xy(move)
    board = color_at(steps)
    # White is the candidate side in this server. Add both attack and block pressure.
    center = 14 - (abs(x - 7) + abs(y - 7))
    dirs = [(1, 0), (0, 1), (1, 1), (1, -1)]
    score = center
    for color, weight in [(2, 10), (1, 8)]:
        for dx, dy in dirs:
            count = 1
            open_ends = 0
            for sign in [1, -1]:
                nx, ny = x + sign * dx, y + sign * dy
                while board.get((nx, ny)) == color:
                    count += 1
                    nx += sign * dx
                    ny += sign * dy
                if 0 <= nx < 15 and 0 <= ny < 15 and (nx, ny) not in board:
                    open_ends += 1
            if count >= 5:
                score += 100000 * weight
            elif count == 4 and open_ends:
                score += 10000 * weight
            elif count == 3 and open_ends == 2:
                score += 1000 * weight
            elif count == 3 and open_ends:
                score += 200 * weight
            elif count == 2 and open_ends == 2:
                score += 40 * weight
    return score


def min_chebyshev_distance(steps, move, recent_n=None):
    if not steps:
        return 0
    x, y = move_to_xy(move)
    source = steps[-recent_n:] if recent_n else steps
    return min(max(abs(x - sx), abs(y - sy)) for sx, sy in [move_to_xy(m) for m in source])


def line_profile(steps, move, color):
    x, y = move_to_xy(move)
    board = color_at(steps)
    dirs = [(1, 0), (0, 1), (1, 1), (1, -1)]
    best_count = 0
    best_open_ends = 0
    open_four = False
    closed_four = False
    open_three = False
    for dx, dy in dirs:
        count = 1
        open_ends = 0
        for sign in [1, -1]:
            nx, ny = x + sign * dx, y + sign * dy
            while board.get((nx, ny)) == color:
                count += 1
                nx += sign * dx
                ny += sign * dy
            if 0 <= nx < 15 and 0 <= ny < 15 and (nx, ny) not in board:
                open_ends += 1
        if count > best_count or (count == best_count and open_ends > best_open_ends):
            best_count = count
            best_open_ends = open_ends
        open_four = open_four or (count == 4 and open_ends == 2)
        closed_four = closed_four or (count == 4 and open_ends == 1)
        open_three = open_three or (count == 3 and open_ends == 2)
    return {
        "best_count": best_count,
        "best_open_ends": best_open_ends,
        "five": best_count >= 5,
        "open_four": open_four,
        "closed_four": closed_four,
        "open_three": open_three,
    }


def relevance_profile(steps, move):
    heuristic = candidate_heuristic(steps, move)
    nearest = min_chebyshev_distance(steps, move)
    recent_nearest = min_chebyshev_distance(steps, move, recent_n=10)
    white_profile = line_profile(steps, move, 2)
    black_profile = line_profile(steps, move, 1)
    urgent = white_profile["five"] or black_profile["five"]
    tactical = (
        urgent
        or white_profile["open_four"]
        or white_profile["closed_four"]
        or white_profile["open_three"]
        or black_profile["open_four"]
        or black_profile["closed_four"]
        or black_profile["open_three"]
    )
    local = nearest <= 2
    recent = recent_nearest <= 3
    usable_candidate = urgent or tactical or local or recent
    trusted_db_miss = urgent or tactical or (local and recent and heuristic >= 80) or (local and heuristic >= 300)
    return {
        "heuristic": heuristic,
        "nearest": nearest,
        "recent_nearest": recent_nearest,
        "white_profile": white_profile,
        "black_profile": black_profile,
        "urgent": urgent,
        "tactical": tactical,
        "local": local,
        "recent": recent,
        "usable_candidate": usable_candidate,
        "trusted_db_miss": trusted_db_miss,
    }


def rapfi_move_is_usable(steps, move, rapfi):
    if not move or move_to_xy(move) in occupied(steps):
        return False
    profile = relevance_profile(steps, move)
    if profile["usable_candidate"]:
        return True
    has_search_detail = bool(rapfi.get("bestline")) or rapfi.get("eval") is not None or rapfi.get("winrate") is not None
    return has_search_detail and profile["nearest"] <= 3


def black_db_replies(steps):
    key = steps_to_string(steps)
    if key in db_cache:
        return db_cache[key]
    if key == "":
        replies = ["h8"]
    else:
        try:
            replies = list(dict.fromkeys(find_next_steps_from_db(key, db)))
        except Exception:
            replies = []
    db_cache[key] = replies
    return replies


def is_legal_response_move(steps, move):
    if not move or not re.match(r"^[a-o](?:[1-9]|1[0-5])$", move):
        return False
    return move_to_xy(move) not in occupied(steps)


def general_search_black_best(
    steps,
    turn_time_ms=SEARCH_BLACK_MS,
    max_depth=SEARCH_BLACK_DEPTH,
    threads=SEARCH_BLACK_THREADS,
):
    board_line = "YXBOARD"
    side = 1
    for move in steps:
        x, y = move_to_xy(move)
        board_line += " %d,%d,%d" % (x, y, side)
        side = 3 - side
    board_line += " DONE"

    lines = [
        "START 15",
        "RELOADCONFIG config.toml",
        "INFO RULE 0",
        "INFO THREAD_NUM %d" % threads,
        "INFO CAUTION_FACTOR %d" % SEARCH_BLACK_CAND_RANGE,
        "INFO STRENGTH 100",
        "INFO TIMEOUT_TURN %d" % turn_time_ms,
        "INFO TIMEOUT_MATCH 9999000",
        "INFO MAX_DEPTH %d" % max_depth,
        "INFO MAX_NODE 0",
        "INFO SHOW_DETAIL 3",
        "INFO PONDERING 0",
        "INFO SWAPABLE 1",
        "INFO HASH_SIZE %d" % SEARCH_BLACK_HASH_KB,
        board_line,
        "YXNBEST 1",
        "END",
    ]
    started = time.time()
    # Configured local engine path; shell is not used.
    proc = subprocess.run(  # nosec B603
        [RAPFI_EXE],
        input="\n".join(lines) + "\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=RAPFI_DIR,
        timeout=max(5, turn_time_ms / 1000 + 8),
    )
    best = None
    bestline = []
    detail = {
        "eval": None,
        "winrate": None,
        "depth": None,
        "seldepth": None,
        "nodes": None,
        "totalnodes": None,
        "totaltime": None,
    }
    for line in proc.stdout.splitlines():
        line = line.strip()
        if re.match(r"^\d+,\d+$", line):
            x, y = [int(v) for v in line.split(",")]
            best = xy_to_move(x, y)
        elif line.startswith("INFO BESTLINE "):
            bestline = [xy_to_move(int(x), int(y)) for x, y in re.findall(r"(\d+),(\d+)", line)]
        elif line.startswith("INFO EVAL "):
            detail["eval"] = line.split(" ", 2)[2]
        elif line.startswith("INFO WINRATE "):
            try:
                detail["winrate"] = float(line.split(" ", 2)[2])
            except ValueError:
                detail["winrate"] = None
        elif line.startswith("INFO DEPTH "):
            detail["depth"] = int(line.split()[-1])
        elif line.startswith("INFO SELDEPTH "):
            detail["seldepth"] = int(line.split()[-1])
        elif line.startswith("INFO NODES "):
            detail["nodes"] = int(line.split()[-1])
        elif line.startswith("INFO TOTALNODES "):
            detail["totalnodes"] = int(line.split()[-1])
        elif line.startswith("INFO TOTALTIME "):
            detail["totaltime"] = int(line.split()[-1])
    if best is None:
        raise RuntimeError("general-search black did not return a move: " + proc.stdout[-2000:])
    return {
        "best": best,
        "bestline": bestline,
        "elapsed_ms": int((time.time() - started) * 1000),
        "settings": {
            "turn_time_ms": turn_time_ms,
            "max_depth": max_depth,
            "threads": threads,
            "hash_kb": SEARCH_BLACK_HASH_KB,
            "cand_range": SEARCH_BLACK_CAND_RANGE,
            "strength": 100,
        },
        **detail,
    }


def general_search_black_response(steps, reason, base_response=None, started_at=None):
    started_at = time.time() if started_at is None else started_at
    steps_url = steps_to_string(steps)
    request_move_count = len(steps)
    search_result = general_search_black_best(steps)
    move = search_result["best"]
    if not is_legal_response_move(steps, move):
        raise RuntimeError("general-search black returned illegal move: %s" % move)
    x, y = move_to_xy(move)
    response = {
        "input": steps_url,
        "request_steps_string": steps_url,
        "request_move_count": request_move_count,
        "x": x,
        "y": y,
        "selected_move": move,
        "source": "general_search_black",
        "source_detail": "full Rapfi general-search black fallback",
        "active_black_engine": "general_search_black",
        "fallback_reason": reason,
        "db_hit": False,
        "possible_moves_raw": [move],
        "possible_moves_unique": [move],
        "possible_move_count_raw": 1,
        "possible_move_count_unique": 1,
        "search_engine": search_result,
    }
    if base_response is not None:
        response["proof_tree_response_before_fallback"] = {
            key: base_response.get(key)
            for key in (
                "source",
                "source_detail",
                "selected_move",
                "web_search_returncode",
                "web_search_parse_error",
                "error",
                "message",
            )
            if base_response.get(key) is not None
        }
    response["elapsed_ms"] = int((time.time() - started_at) * 1000)
    return response


def choose_proof_tree_black_move(steps, started_at):
    steps_url = steps_to_string(steps)
    request_move_count = len(steps)
    possible_moves = []

    if steps_url == "":
        return {
            "input": steps_url,
            "request_steps_string": steps_url,
            "request_move_count": request_move_count,
            "x": 7,
            "y": 7,
            "selected_move": "h8",
            "source": "opening_default",
            "source_detail": "frontend/original-opening",
            "active_black_engine": "proof_tree_black",
            "fallback_reason": None,
            "db_hit": False,
            "possible_moves_raw": ["h8"],
            "possible_moves_unique": ["h8"],
            "possible_move_count_raw": 1,
            "possible_move_count_unique": 1,
        }

    possible_moves = find_next_steps_from_db(steps_url, db)
    if len(possible_moves) > 0:
        next_move = possible_moves[0]
        x, y = move_to_xy(next_move)
        unique_moves = list(dict.fromkeys(possible_moves))
        return {
            "input": steps_url,
            "request_steps_string": steps_url,
            "request_move_count": request_move_count,
            "x": x,
            "y": y,
            "selected_move": next_move,
            "source": "leveldb",
            "source_detail": "leveldb.db",
            "active_black_engine": "proof_tree_black",
            "fallback_reason": None,
            "db_hit": True,
            "possible_moves_raw": possible_moves,
            "possible_moves_unique": unique_moves,
            "possible_move_count_raw": len(possible_moves),
            "possible_move_count_unique": len(unique_moves),
        }

    timeout_program = "timeout" if platform.system() == "Linux" else "gtimeout"
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = "/usr/local/clang_9.0.0/lib:" + env.get("LD_LIBRARY_PATH", "")
    # Configured local proof-search binary; shell is not used.
    proc = subprocess.run(  # nosec B603
        [timeout_program, "10s", WEB_SEARCH_EXE, steps_url],
        shell=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=BASE_DIR,
        env=env,
        timeout=12,
    )
    res = proc.stdout.strip()
    response = {
        "input": steps_url,
        "request_steps_string": steps_url,
        "request_move_count": request_move_count,
        "source": "web_search",
        "source_detail": "web_search",
        "active_black_engine": "proof_tree_black",
        "fallback_reason": None,
        "db_hit": False,
        "web_search_returncode": proc.returncode,
        "web_search_response_size": len(res),
    }
    try:
        parsed = json.loads(res)
        response.update(parsed)
        if "x" in parsed and "y" in parsed:
            response["selected_move"] = "%s%s" % (chr(int(parsed["x"]) + ord("a")), int(parsed["y"]) + 1)
    except json.JSONDecodeError:
        response["web_search_parse_error"] = "invalid_json"
    return response


def should_use_general_search_black(steps, proof_tree_response):
    if steps and steps[0] != "h8":
        return "first_black_is_not_h8"
    move = proof_tree_response.get("selected_move")
    if not is_legal_response_move(steps, move):
        return "proof_tree_no_legal_move"
    return None


def choose_black_move(steps):
    started_at = time.time()
    if steps and steps[0] != "h8":
        return general_search_black_response(steps, "first_black_is_not_h8", started_at=started_at)
    try:
        response = choose_proof_tree_black_move(steps, started_at)
    except Exception as exc:
        response = {
            "source": "proof_tree_black_error",
            "source_detail": "proof-tree black path raised before producing a legal move",
            "error": type(exc).__name__,
            "message": str(exc),
        }
        return general_search_black_response(
            steps,
            "proof_tree_black_exception:%s" % type(exc).__name__,
            base_response=response,
            started_at=started_at,
        )
    reason = should_use_general_search_black(steps, response)
    if reason:
        return general_search_black_response(steps, reason, base_response=response, started_at=started_at)
    response["elapsed_ms"] = int((time.time() - started_at) * 1000)
    return response


def resistance_value(after_white_steps, depth):
    key = (steps_to_string(after_white_steps), depth)
    if key in resistance_cache:
        return resistance_cache[key]

    black_replies = black_db_replies(after_white_steps)
    if not black_replies:
        result = (math.inf, "escape")
        resistance_cache[key] = result
        return result
    if depth <= 0:
        result = (0, "db_hit")
        resistance_cache[key] = result
        return result

    black_can_force = []
    for black_move in black_replies[:3]:
        line = after_white_steps + [black_move]
        if has_five(line, 1):
            black_can_force.append((1, "black_win"))
            continue
        white_candidates = legal_moves_near(line, radius=2, limit=14)
        best_white = (-1, "no_white_move")
        for white_move in white_candidates:
            child = line + [white_move]
            if has_five(child, 2):
                best_white = (math.inf, "white_win")
                break
            child_value, child_status = resistance_value(child, depth - 1)
            value = math.inf if math.isinf(child_value) else child_value + 2
            if value > best_white[0]:
                best_white = (value, child_status)
        black_can_force.append(best_white)

    finite = [x for x in black_can_force if not math.isinf(x[0])]
    result = min(finite, key=lambda x: x[0]) if finite else (math.inf, "escape")
    resistance_cache[key] = result
    return result


def int_setting(value, default, min_value=1, max_value=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    parsed = max(min_value, parsed)
    if max_value is not None:
        parsed = min(max_value, parsed)
    return parsed


def rapfi_best(steps, turn_time_ms=WHITE_RAPFI_MS, max_depth=WHITE_RAPFI_DEPTH, threads=WHITE_RAPFI_THREADS):
    board_line = "YXBOARD"
    side = 1 if len(steps) % 2 == 0 else 2
    for move in steps:
        x, y = move_to_xy(move)
        board_line += " %d,%d,%d" % (x, y, side)
        side = 3 - side
    board_line += " DONE"

    lines = [
        "START 15",
        "RELOADCONFIG config.toml",
        "INFO RULE 0",
        "INFO THREAD_NUM %d" % threads,
        "INFO CAUTION_FACTOR 3",
        "INFO STRENGTH 100",
        "INFO TIMEOUT_TURN %d" % turn_time_ms,
        "INFO TIMEOUT_MATCH 9999000",
        "INFO MAX_DEPTH %d" % max_depth,
        "INFO MAX_NODE 0",
        "INFO SHOW_DETAIL 3",
        "INFO PONDERING 0",
        "INFO SWAPABLE 1",
        "INFO HASH_SIZE %d" % WHITE_RAPFI_HASH_KB,
        board_line,
        "YXNBEST 1",
        "END",
    ]
    started = time.time()
    # Configured local engine path; shell is not used.
    proc = subprocess.run(  # nosec B603
        [RAPFI_EXE],
        input="\n".join(lines) + "\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=RAPFI_DIR,
        timeout=max(3, turn_time_ms / 1000 + 4),
    )
    best = None
    bestline = []
    last_eval = None
    last_winrate = None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if re.match(r"^\d+,\d+$", line):
            x, y = [int(v) for v in line.split(",")]
            best = xy_to_move(x, y)
        elif line.startswith("INFO BESTLINE "):
            bestline = [xy_to_move(int(x), int(y)) for x, y in re.findall(r"(\d+),(\d+)", line)]
        elif line.startswith("INFO EVAL "):
            last_eval = line.split(" ", 2)[2]
        elif line.startswith("INFO WINRATE "):
            try:
                last_winrate = float(line.split(" ", 2)[2])
            except ValueError:
                last_winrate = None
    return {
        "best": best,
        "bestline": bestline,
        "eval": last_eval,
        "winrate": last_winrate,
        "elapsed_ms": int((time.time() - started) * 1000),
    }


def _pbrain_send(proc, line):
    proc.stdin.write(line + "\n")
    proc.stdin.flush()


def _pbrain_read_line(lines, timeout):
    try:
        return lines.get(timeout=timeout)
    except queue.Empty:
        return None


def _pbrain_read_until(lines, predicate, timeout):
    deadline = time.time() + timeout
    seen = []
    while time.time() < deadline:
        line = _pbrain_read_line(lines, max(0.05, deadline - time.time()))
        if line is None:
            continue
        seen.append(line)
        if predicate(line):
            return line, seen
    raise TimeoutError("pbrain timed out; seen=%s" % seen[-20:])


def _pbrain_drain(lines):
    drained = []
    while True:
        try:
            drained.append(lines.get_nowait())
        except queue.Empty:
            return drained


def pbrain_info_commands(turn_time_ms, max_depth, threads):
    commands = [
        "INFO timeout_turn %d" % turn_time_ms,
        "INFO timeout_match 9999000",
        "INFO max_memory %d" % GOMOCUP_ADVISOR_MEMORY_BYTES,
        "INFO thread_num %d" % threads,
        "INFO rule 0",
        "INFO game_type 1",
        "INFO THREAD_NUM %d" % threads,
        "INFO TIMEOUT_TURN %d" % turn_time_ms,
        "INFO CAUTION_FACTOR 3",
        "INFO STRENGTH 100",
        "INFO PONDERING 0",
    ]
    if max_depth is not None:
        commands.extend(["INFO max_depth %d" % max_depth, "INFO MAX_DEPTH %d" % max_depth])
    return commands


def pbrain_send_board(proc, steps, own_color=2):
    _pbrain_send(proc, "BOARD")
    for index, move in enumerate(steps):
        x, y = move_to_xy(move)
        stone_color = 1 if index % 2 == 0 else 2
        field = 1 if stone_color == own_color else 2
        _pbrain_send(proc, "%d,%d,%d" % (x, y, field))
    _pbrain_send(proc, "DONE")


class PersistentPBrainAdvisor:
    def __init__(self, name, exe, weight):
        self.name = name
        self.exe = exe
        self.weight = weight
        self.proc = None
        self.lines = None
        self.reader = None
        self.lock = threading.Lock()
        self.start_count = 0

    def _start(self, turn_time_ms):
        if not os.path.exists(self.exe):
            raise FileNotFoundError(self.exe)
        # Configured local PBrain engine path; shell is not used.
        self.proc = subprocess.Popen(  # nosec B603
            [self.exe],
            cwd=os.path.dirname(self.exe),
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
        _pbrain_send(self.proc, "START 15")
        _pbrain_read_until(
            self.lines,
            lambda line: line == "OK" or (line or "").startswith("ERROR"),
            timeout=max(8, min(30, turn_time_ms / 1000 + 8)),
        )
        self.start_count += 1

    def _ensure_started(self, turn_time_ms):
        if self.proc is not None and self.proc.poll() is None:
            return
        self.close()
        self._start(turn_time_ms)

    def close(self):
        if self.proc is None:
            return
        try:
            if self.proc.poll() is None:
                _pbrain_send(self.proc, "END")
                self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
            except Exception as kill_exc:
                sys.stderr.write("failed to kill PBrain advisor %s: %s\n" % (self.name, kill_exc))
        self.proc = None
        self.lines = None
        self.reader = None

    def query(self, steps, turn_time_ms, max_depth, threads, own_color=2):
        started = time.time()
        seen_tail = []
        with self.lock:
            try:
                self._ensure_started(turn_time_ms)
                seen_tail.extend(_pbrain_drain(self.lines)[-10:])
                for command in pbrain_info_commands(turn_time_ms, max_depth, threads):
                    _pbrain_send(self.proc, command)
                pbrain_send_board(self.proc, steps, own_color=own_color)
                move_line, seen = _pbrain_read_until(
                    self.lines,
                    lambda line: re.match(r"^\d+,\d+$", line or "") is not None,
                    timeout=max(20, turn_time_ms / 1000 + 15),
                )
                seen_tail.extend(seen[-20:])
                x, y = [int(value) for value in move_line.split(",")]
                move = xy_to_move(x, y)
                if not (0 <= x < 15 and 0 <= y < 15):
                    status = "out_of_board"
                elif move_to_xy(move) in occupied(steps):
                    status = "occupied"
                else:
                    status = "ok"
                return {
                    "name": self.name,
                    "weight": self.weight,
                    "move": move,
                    "status": status,
                    "path": self.exe,
                    "raw_line": move_line,
                    "seen_tail": seen_tail[-20:],
                    "persistent": True,
                    "own_color": own_color,
                    "start_count": self.start_count,
                    "elapsed_ms": int((time.time() - started) * 1000),
                }
            except Exception as exc:
                self.close()
                return {
                    "name": self.name,
                    "weight": self.weight,
                    "status": "error",
                    "path": self.exe,
                    "error": type(exc).__name__,
                    "message": str(exc),
                    "seen_tail": seen_tail[-20:],
                    "persistent": True,
                    "own_color": own_color,
                    "start_count": self.start_count,
                    "elapsed_ms": int((time.time() - started) * 1000),
                }


PERSISTENT_ADVISORS = {}


def persistent_advisor_best(name, exe, weight, steps, turn_time_ms, max_depth, threads, own_color=2):
    advisor = PERSISTENT_ADVISORS.get(name)
    if advisor is None:
        advisor = PersistentPBrainAdvisor(name, exe, weight)
        PERSISTENT_ADVISORS[name] = advisor
    return advisor.query(steps, turn_time_ms, max_depth, threads, own_color=own_color)


def pbrain_advisor_best(name, exe, weight, steps, turn_time_ms, max_depth, threads, own_color=2):
    if GOMOCUP_ADVISOR_PERSISTENT:
        return persistent_advisor_best(name, exe, weight, steps, turn_time_ms, max_depth, threads, own_color=own_color)

    started = time.time()
    if not os.path.exists(exe):
        return {
            "name": name,
            "weight": weight,
            "status": "missing",
            "path": exe,
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    proc = None
    lines = queue.Queue()
    seen_tail = []
    try:
        # Configured local PBrain engine path; shell is not used.
        proc = subprocess.Popen(  # nosec B603
            [exe],
            cwd=os.path.dirname(exe),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        def read_loop():
            for line in proc.stdout:
                lines.put(line.rstrip("\r\n"))

        reader = threading.Thread(target=read_loop, daemon=True)
        reader.start()

        _pbrain_send(proc, "START 15")
        _, seen = _pbrain_read_until(
            lines,
            lambda line: line == "OK" or (line or "").startswith("ERROR"),
            timeout=max(8, min(30, turn_time_ms / 1000 + 8)),
        )
        seen_tail.extend(seen[-10:])

        for command in pbrain_info_commands(turn_time_ms, max_depth, threads):
            _pbrain_send(proc, command)

        pbrain_send_board(proc, steps, own_color=own_color)

        move_line, seen = _pbrain_read_until(
            lines,
            lambda line: re.match(r"^\d+,\d+$", line or "") is not None,
            timeout=max(20, turn_time_ms / 1000 + 15),
        )
        seen_tail.extend(seen[-20:])
        x, y = [int(value) for value in move_line.split(",")]
        move = xy_to_move(x, y)
        if not (0 <= x < 15 and 0 <= y < 15):
            status = "out_of_board"
        elif move_to_xy(move) in occupied(steps):
            status = "occupied"
        else:
            status = "ok"
        return {
            "name": name,
            "weight": weight,
            "move": move,
            "status": status,
            "path": exe,
            "raw_line": move_line,
            "seen_tail": seen_tail[-20:],
            "own_color": own_color,
            "elapsed_ms": int((time.time() - started) * 1000),
        }
    except Exception as exc:
        return {
            "name": name,
            "weight": weight,
            "status": "error",
            "path": exe,
            "error": type(exc).__name__,
            "message": str(exc),
            "seen_tail": seen_tail[-20:],
            "elapsed_ms": int((time.time() - started) * 1000),
        }
    finally:
        if proc is not None:
            try:
                if proc.poll() is None:
                    _pbrain_send(proc, "END")
                    proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception as kill_exc:
                    sys.stderr.write("failed to kill PBrain advisor %s: %s\n" % (name, kill_exc))


def gomocup_advisor_votes(steps, turn_time_ms, max_depth, threads):
    started = time.time()
    votes = []
    max_workers = max(1, min(GOMOCUP_ADVISOR_MAX_WORKERS, len(GOMOCUP_VOTING_ADVISORS)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(pbrain_advisor_best, name, exe, weight, steps, turn_time_ms, max_depth, threads)
            for name, exe, weight in GOMOCUP_VOTING_ADVISORS
        ]
        for future in as_completed(futures):
            votes.append(future.result())
    order = {name: index for index, (name, _exe, _weight) in enumerate(GOMOCUP_VOTING_ADVISORS)}
    votes.sort(key=lambda vote: order.get(vote.get("name"), 999))
    return {
        "votes": votes,
        "ok_votes": [vote for vote in votes if vote.get("status") == "ok"],
        "elapsed_ms": int((time.time() - started) * 1000),
        "settings": {
            "turn_time_ms": turn_time_ms,
            "max_depth": max_depth,
            "threads": threads,
            "max_workers": max_workers,
            "excluded": sorted(GOMOCUP_VOTING_EXCLUDE),
        },
    }


def gomocup_adversary_validations(steps, candidate_moves, turn_time_ms, max_depth, threads):
    started = time.time()
    tasks = []
    advisors = GOMOCUP_ADVISORS[: max(1, min(GOMOCUP_ADVERSARY_ADVISORS, len(GOMOCUP_ADVISORS)))]
    max_workers = max(1, min(GOMOCUP_ADVISOR_MAX_WORKERS, len(candidate_moves) * len(advisors)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for move in candidate_moves:
            after_white = steps + [move]
            for name, exe, weight in advisors:
                future = executor.submit(
                    pbrain_advisor_best,
                    name,
                    exe,
                    weight,
                    after_white,
                    turn_time_ms,
                    max_depth,
                    threads,
                    1,
                )
                tasks.append((move, future))

        by_move = {move: [] for move in candidate_moves}
        for move, future in tasks:
            reply = future.result()
            if reply.get("status") == "ok" and reply.get("move") and move_to_xy(reply["move"]) not in occupied(steps + [move]):
                after_black = steps + [move, reply["move"]]
                reply["black_has_five"] = has_five(after_black, 1)
                reply["black_next_wins"] = [] if reply["black_has_five"] else immediate_winning_moves(after_black, 1)[:8]
                reply["white_immediate_wins_after_reply"] = immediate_winning_moves(after_black, 2)[:8]
            by_move.setdefault(move, []).append(reply)
    return {
        "by_move": by_move,
        "elapsed_ms": int((time.time() - started) * 1000),
        "advisor_count": len(advisors),
    }


def ensemble_book_candidates(steps, include_targets=None):
    entries_by_move = {}
    key = tuple(steps)
    occ = occupied(steps)
    include_targets = set(include_targets) if include_targets is not None else None
    for name, book in ENSEMBLE_BOOKS.items():
        if include_targets is not None and name not in include_targets:
            continue
        entry = book.get(key)
        if not entry:
            continue
        move, bonus, tag = entry
        if move_to_xy(move) in occ:
            continue
        entries_by_move.setdefault(move, []).append(
            {
                "target": name,
                "bonus": bonus,
                "tag": tag,
            }
        )
    return entries_by_move


def choose_white_move(steps, settings=None):
    settings = settings or {}
    turn_time_ms = settings.get("turn_time_ms", WHITE_RAPFI_MS)
    max_depth = settings.get("max_depth", WHITE_RAPFI_DEPTH)
    threads = settings.get("threads", WHITE_RAPFI_THREADS)
    requested_target = normalize_white_target(settings.get("target"))
    opponent = (settings.get("opponent") or "").strip()
    if requested_target in AUTO_TARGETS:
        target, auto_base_target = resolve_auto_white_target(opponent)
        base_target = normalize_white_target(settings.get("base_target") or auto_base_target)
    else:
        target = requested_target
        base_target = normalize_white_target(settings.get("base_target") or DEFAULT_WHITE_TARGET)
    resistance_book = TARGET_BOOKS[target]
    use_black_db_reverse = target in DB_REVERSE_TARGETS
    use_deep_tactics = bool(settings.get("deep_tactics", False))
    started = time.time()
    if len(steps) % 2 == 0:
        raise ValueError("white AI can move only when it is WHITE's turn")
    if has_five(steps, 1) or has_five(steps, 2):
        raise ValueError("game already has a five-in-a-row")

    rapfi = rapfi_best(steps, turn_time_ms=turn_time_ms, max_depth=max_depth, threads=threads)
    direct_advisor = direct_advisor_spec(target)
    if requested_target in AUTO_TARGETS and direct_advisor is not None and base_target in AUTO_DIRECT_EXACT_BOOK_BASE_TARGETS:
        auto_book_entry = TARGET_BOOKS.get(base_target, {}).get(tuple(steps))
        if auto_book_entry and move_to_xy(auto_book_entry[0]) not in occupied(steps):
            move = auto_book_entry[0]
            x, y = move_to_xy(move)
            after = steps + [move]
            return {
                "input": steps_to_string(steps),
                "x": x,
                "y": y,
                "selected_move": move,
                "source": "white_auto_direct_exact_book",
                "source_detail": "exact base-target book override before direct Gomocup advisor",
                "target": target,
                "requested_target": requested_target,
                "opponent": opponent,
                "base_target": base_target,
                "direct_advisor": direct_advisor[0],
                "use_black_db_reverse": False,
                "use_deep_tactics": False,
                "rapfi": rapfi,
                "black_immediate_wins_after": immediate_winning_moves(after, 1)[:8],
                "white_has_five_after": has_five(after, 2),
                "rapfi_settings": {
                    "turn_time_ms": turn_time_ms,
                    "max_depth": max_depth,
                    "threads": threads,
                },
                "book_entry": {
                    "move": auto_book_entry[0],
                    "bonus": auto_book_entry[1],
                    "tag": auto_book_entry[2],
                    "target": base_target,
                },
                "ensemble_book_entries": {},
                "chosen": {
                    "move": move,
                    "score": auto_book_entry[1],
                    "status": "auto_direct_exact_book:%s" % auto_book_entry[2],
                },
                "candidates": [],
                "candidate_count": 1,
                "elapsed_ms": int((time.time() - started) * 1000),
            }
    if direct_advisor is not None:
        advisor_name, advisor_exe, advisor_weight = direct_advisor
        reply = pbrain_advisor_best(
            advisor_name,
            advisor_exe,
            advisor_weight,
            steps,
            turn_time_ms=turn_time_ms,
            max_depth=max_depth,
            threads=threads,
            own_color=2,
        )
        if reply.get("status") != "ok":
            raise RuntimeError(
                "direct Gomocup advisor %s failed: %s"
                % (advisor_name, reply.get("message") or reply.get("status"))
            )
        move = reply.get("move")
        if not move or move_to_xy(move) in occupied(steps):
            raise RuntimeError("direct Gomocup advisor %s returned illegal move: %s" % (advisor_name, move))
        x, y = move_to_xy(move)
        after = steps + [move]
        return {
            "input": steps_to_string(steps),
            "x": x,
            "y": y,
            "selected_move": move,
            "source": "white_gomocup_direct",
            "source_detail": "direct PBrain move from a Gomocup engine target; no heuristic fallback",
            "target": target,
            "requested_target": requested_target,
            "opponent": opponent,
            "direct_advisor": advisor_name,
            "use_black_db_reverse": False,
            "use_deep_tactics": False,
            "rapfi": rapfi,
            "advisor_reply": reply,
            "black_immediate_wins_after": immediate_winning_moves(after, 1)[:8],
            "white_has_five_after": has_five(after, 2),
            "rapfi_settings": {
                "turn_time_ms": turn_time_ms,
                "max_depth": max_depth,
                "threads": threads,
            },
            "book_entry": None,
            "ensemble_book_entries": {},
            "chosen": {
                "move": move,
                "score": None,
                "status": "direct_advisor:%s" % advisor_name,
            },
            "candidates": [],
            "candidate_count": 1,
            "elapsed_ms": int((time.time() - started) * 1000),
        }
    if target in ADVISOR_ENSEMBLE_TARGETS:
        base_resistance_book = TARGET_BOOKS.get(base_target, {})
        base_use_black_db_reverse = base_target in DB_REVERSE_TARGETS
        advisor_result = gomocup_advisor_votes(
            steps,
            turn_time_ms=turn_time_ms,
            max_depth=max_depth,
            threads=threads,
        )
        votes_by_move = {}
        for vote in advisor_result["ok_votes"]:
            move = vote.get("move")
            if not move or move_to_xy(move) in occupied(steps):
                continue
            votes_by_move.setdefault(move, []).append(vote)

        candidates = set(legal_moves_near(steps, radius=2, limit=36))
        candidates.update(votes_by_move.keys())
        candidates.update(immediate_winning_moves(steps, 2))
        candidates.update(immediate_winning_moves(steps, 1))
        book_entry = base_resistance_book.get(tuple(steps))
        if book_entry and move_to_xy(book_entry[0]) not in occupied(steps):
            candidates.add(book_entry[0])
        ensemble_entries_by_move = (
            ensemble_book_candidates(steps, include_targets={base_target})
            if base_target in ENSEMBLE_BOOKS
            else {}
        )
        candidates.update(ensemble_entries_by_move.keys())
        if rapfi.get("best") and move_to_xy(rapfi["best"]) not in occupied(steps):
            candidates.add(rapfi["best"])
        for move in rapfi.get("bestline", [])[:8]:
            if move_to_xy(move) not in occupied(steps):
                candidates.add(move)

        scored = []
        for move in candidates:
            if move_to_xy(move) in occupied(steps):
                continue
            profile = relevance_profile(steps, move)
            after = steps + [move]
            black_immediate_wins = immediate_winning_moves(after, 1)
            black_deep_threats = [] if black_immediate_wins or not use_deep_tactics else black_two_step_threats(after)
            db_replies = []
            move_votes = votes_by_move.get(move, [])
            vote_weight = sum(vote.get("weight", 0) for vote in move_votes)
            vote_names = [vote.get("name") for vote in move_votes]
            is_book_move = book_entry and move == book_entry[0]
            ensemble_entries = ensemble_entries_by_move.get(move, [])

            if has_five(after, 2):
                score = math.inf
                status = "white_immediate_win"
            else:
                score = min(profile["heuristic"], 2000)
                status = "advisor_ensemble"
                if base_use_black_db_reverse:
                    db_replies = black_db_replies(after)
                    if not db_replies:
                        if profile["trusted_db_miss"]:
                            score += 1_250_000
                            status += "+base_db_escape_candidate"
                        else:
                            score -= 120_000
                            status += "+base_db_miss_untrusted"
                    else:
                        value, db_status = resistance_value(after, depth=3)
                        score += (720_000 if math.isinf(value) else value * 800)
                        status += "+base_db_%s" % db_status
                if vote_weight:
                    score += vote_weight * 4_000
                    score += max(0, len(move_votes) - 1) * 90_000
                    status += "+advisor_votes"
                if is_book_move:
                    score += 3_000_000 + min(book_entry[1], 1_200_000)
                    status += "+base_book:%s" % book_entry[2]
                if ensemble_entries:
                    ensemble_bonus = 1_500_000 + min(1_200_000, max(entry["bonus"] for entry in ensemble_entries))
                    ensemble_bonus += max(0, len(ensemble_entries) - 1) * 100_000
                    score += ensemble_bonus
                    status += "+ensemble_book:" + ",".join(
                        "%s/%s" % (entry["target"], entry["tag"]) for entry in ensemble_entries
                    )
                if "rapfi25" in vote_names:
                    score += 180_000
                    status += "+rapfi25"
                if "katagomo26_f15" in vote_names:
                    score += 150_000
                    status += "+katagomo26"
                if "alphagomoku_mk26" in vote_names:
                    score += 130_000
                    status += "+alphagomoku"
                if {"rapfi25", "katagomo26_f15"}.issubset(set(vote_names)):
                    score += 260_000
                    status += "+rapfi_kata_consensus"
                if {"rapfi25", "katagomo26_f15", "alphagomoku_mk26"}.issubset(set(vote_names)):
                    score += 450_000
                    status += "+top3_consensus"
                if move == rapfi.get("best"):
                    score += 240_000
                    status += "+local_rapfi_best"
                elif rapfi.get("bestline") and move == rapfi["bestline"][0]:
                    score += 120_000
                    status += "+local_rapfi_principal"
                if profile["black_profile"]["five"]:
                    score += 1_600_000
                    status += "+must_block_five"
                elif profile["black_profile"]["open_four"]:
                    score += 380_000
                    status += "+block_open_four"
                elif profile["black_profile"]["closed_four"]:
                    score += 180_000
                    status += "+block_closed_four"
                if profile["white_profile"]["open_four"]:
                    score += 300_000
                    status += "+white_open_four"
                elif profile["white_profile"]["closed_four"]:
                    score += 140_000
                    status += "+white_closed_four"
                if black_immediate_wins:
                    score -= 9_000_000 + 120_000 * len(black_immediate_wins)
                    status += "+allows_black_immediate_win"
                elif black_deep_threats:
                    score -= 1_800_000 + 90_000 * len(black_deep_threats)
                    status += "+allows_black_two_step_threat"
                if not move_votes and not profile["usable_candidate"] and move != rapfi.get("best"):
                    score -= 500_000
                    status += "+low_relevance"

            scored.append(
                {
                    "move": move,
                    "score": score,
                    "status": status,
                    "advisor_vote_weight": vote_weight,
                    "advisor_vote_count": len(move_votes),
                    "advisor_votes": move_votes,
                    "black_db_replies": db_replies[:5],
                    "black_immediate_wins": black_immediate_wins[:8],
                    "black_two_step_threats": black_deep_threats[:8],
                    "heuristic": profile["heuristic"],
                    "relevance": {
                        "nearest": profile["nearest"],
                        "recent_nearest": profile["recent_nearest"],
                        "tactical": profile["tactical"],
                        "trusted_db_miss": profile["trusted_db_miss"],
                    },
                    "is_rapfi_best": move == rapfi.get("best"),
                    "ensemble_entries": ensemble_entries,
                }
            )

        if not scored:
            raise ValueError("no legal white move")
        scored.sort(key=lambda row: row["score"], reverse=True)
        adversary_validation = None
        if GOMOCUP_ADVERSARY_VALIDATION:
            validation_moves = [
                row["move"]
                for row in scored[: max(1, min(GOMOCUP_ADVERSARY_TOP_N, len(scored)))]
                if not math.isinf(row["score"])
            ]
            if validation_moves:
                adversary_validation = gomocup_adversary_validations(
                    steps,
                    validation_moves,
                    turn_time_ms=turn_time_ms,
                    max_depth=max_depth,
                    threads=threads,
                )
                for row in scored:
                    replies = adversary_validation["by_move"].get(row["move"], [])
                    if not replies:
                        continue
                    penalty = 0
                    danger_tags = []
                    for reply in replies:
                        if reply.get("status") != "ok":
                            continue
                        if reply.get("black_has_five"):
                            penalty += 4_000_000
                            danger_tags.append("%s:%s:black_five" % (reply.get("name"), reply.get("move")))
                            continue
                        if reply.get("white_immediate_wins_after_reply"):
                            continue
                        black_next_wins = reply.get("black_next_wins") or []
                        if len(black_next_wins) >= 2:
                            penalty += 2_200_000 + 250_000 * len(black_next_wins)
                            danger_tags.append("%s:%s:black_multi_win" % (reply.get("name"), reply.get("move")))
                        elif len(black_next_wins) == 1:
                            penalty += 260_000
                            danger_tags.append("%s:%s:black_single_win" % (reply.get("name"), reply.get("move")))
                    if penalty:
                        row["score"] -= penalty
                        row["status"] += "+adversary_validation_penalty"
                        row["adversary_penalty"] = penalty
                        row["adversary_dangers"] = danger_tags[:8]
                    row["adversary_validation"] = replies
                scored.sort(key=lambda row: row["score"], reverse=True)
        chosen = scored[0]
        x, y = move_to_xy(chosen["move"])
        return {
            "input": steps_to_string(steps),
            "x": x,
            "y": y,
            "selected_move": chosen["move"],
            "source": "white_advisor_ensemble",
            "source_detail": "weighted Gomocup advisor ensemble with immediate-win priority and immediate-loss veto",
            "target": target,
            "requested_target": requested_target,
            "opponent": opponent,
            "base_target": base_target,
            "use_black_db_reverse": base_use_black_db_reverse,
            "use_deep_tactics": use_deep_tactics,
            "rapfi": rapfi,
            "advisor_ensemble": advisor_result,
            "adversary_validation": adversary_validation,
            "ignored_rapfi_moves": [],
            "rapfi_settings": {
                "turn_time_ms": turn_time_ms,
                "max_depth": max_depth,
                "threads": threads,
            },
            "book_entry": {
                "move": book_entry[0],
                "bonus": book_entry[1],
                "tag": book_entry[2],
                "target": base_target,
            } if book_entry else None,
            "ensemble_book_entries": ensemble_entries_by_move,
            "chosen": chosen,
            "candidates": scored[:16],
            "candidate_count": len(scored),
            "elapsed_ms": int((time.time() - started) * 1000),
        }
    if target in ADVISOR_TARGETS:
        advisor_candidates = []
        if rapfi.get("best"):
            advisor_candidates.append(rapfi["best"])
        advisor_candidates.extend(rapfi.get("bestline", [])[:6])
        advisor_candidates.extend(legal_moves_near(steps, radius=2, limit=28))
        seen_advisor = set()
        advisor_scored = []
        for index, move in enumerate(advisor_candidates):
            if move in seen_advisor or not move or move_to_xy(move) in occupied(steps):
                continue
            seen_advisor.add(move)
            profile = relevance_profile(steps, move)
            after = steps + [move]
            black_immediate_wins = immediate_winning_moves(after, 1)
            status = "advisor_rapfi_best" if move == rapfi.get("best") else "advisor_fallback"
            score = 1_000_000 - index * 10_000 + min(profile["heuristic"], 1200)
            if black_immediate_wins:
                score -= 5_000_000 + 100_000 * len(black_immediate_wins)
                status += "+allows_black_immediate_win"
            advisor_scored.append(
                {
                    "move": move,
                    "score": score,
                    "status": status,
                    "black_db_replies": [],
                    "black_immediate_wins": black_immediate_wins[:8],
                    "black_two_step_threats": [],
                    "heuristic": profile["heuristic"],
                    "relevance": {
                        "nearest": profile["nearest"],
                        "recent_nearest": profile["recent_nearest"],
                        "tactical": profile["tactical"],
                        "trusted_db_miss": profile["trusted_db_miss"],
                    },
                    "is_rapfi_best": move == rapfi.get("best"),
                    "ensemble_entries": [],
                }
            )
        if not advisor_scored:
            raise ValueError("no legal white move")
        advisor_scored.sort(key=lambda r: r["score"], reverse=True)
        chosen = advisor_scored[0]
        x, y = move_to_xy(chosen["move"])
        return {
            "input": steps_to_string(steps),
            "x": x,
            "y": y,
            "selected_move": chosen["move"],
            "source": "white_advisor",
            "source_detail": "Rapfi-best advisor policy with immediate-loss veto and legal fallback",
            "target": target,
            "requested_target": requested_target,
            "opponent": opponent,
            "use_black_db_reverse": False,
            "use_deep_tactics": False,
            "rapfi": rapfi,
            "ignored_rapfi_moves": [],
            "rapfi_settings": {
                "turn_time_ms": turn_time_ms,
                "max_depth": max_depth,
                "threads": threads,
            },
            "book_entry": None,
            "ensemble_book_entries": {},
            "chosen": chosen,
            "candidates": advisor_scored[:12],
            "candidate_count": len(advisor_scored),
            "elapsed_ms": int((time.time() - started) * 1000),
        }
    candidates = set(legal_moves_near(steps, radius=2, limit=28))
    book_entry = resistance_book.get(tuple(steps))
    if book_entry and move_to_xy(book_entry[0]) not in occupied(steps):
        candidates.add(book_entry[0])
    ensemble_entries_by_move = ensemble_book_candidates(steps) if target == "ensemble" else {}
    candidates.update(ensemble_entries_by_move.keys())
    ignored_rapfi_moves = []
    rapfi_primary_usable = rapfi_move_is_usable(steps, rapfi.get("best"), rapfi)
    rapfi_has_search_detail = bool(rapfi.get("bestline")) or rapfi.get("eval") is not None or rapfi.get("winrate") is not None
    if rapfi_primary_usable:
        candidates.add(rapfi["best"])
    elif rapfi.get("best"):
        ignored_rapfi_moves.append({"move": rapfi["best"], "reason": "outside_battlefield_or_no_search_detail"})
    for move in rapfi["bestline"][:6]:
        if rapfi_move_is_usable(steps, move, rapfi):
            candidates.add(move)
        elif move_to_xy(move) not in occupied(steps):
            ignored_rapfi_moves.append({"move": move, "reason": "outside_battlefield"})

    ordered_candidates = list(candidates)
    ordered_candidates.sort(
        key=lambda m: (
            1 if m == rapfi["best"] else 0,
            candidate_heuristic(steps, m),
            m,
        ),
        reverse=True,
    )

    scored = []
    for move in ordered_candidates:
        if move_to_xy(move) in occupied(steps):
            continue
        is_book_move = book_entry and move == book_entry[0]
        ensemble_entries = ensemble_entries_by_move.get(move, [])
        is_ensemble_book_move = bool(ensemble_entries)
        profile = relevance_profile(steps, move)
        if not profile["usable_candidate"] and not is_book_move and not is_ensemble_book_move:
            continue
        after = steps + [move]
        if has_five(after, 2):
            score = math.inf
            status = "white_immediate_win"
            db_replies = []
            black_immediate_wins = []
            black_deep_threats = []
        elif use_black_db_reverse:
            black_immediate_wins = immediate_winning_moves(after, 1)
            black_deep_threats = [] if black_immediate_wins or not use_deep_tactics else black_two_step_threats(after)
            db_replies = black_db_replies(after)
            if not db_replies:
                if profile["trusted_db_miss"]:
                    score = 1_000_000 + min(profile["heuristic"], 1200)
                    status = "black_db_miss_escape_candidate"
                else:
                    score = profile["heuristic"] - 10_000
                    status = "black_db_miss_untrusted"
            else:
                value, status = resistance_value(after, depth=3)
                score = (900_000 if math.isinf(value) else value * 1000) + min(profile["heuristic"], 1200)
        else:
            black_immediate_wins = immediate_winning_moves(after, 1)
            black_deep_threats = [] if black_immediate_wins or not use_deep_tactics else black_two_step_threats(after)
            db_replies = []
            score = profile["heuristic"]
            status = "generic_rapfi_tactical"
            if profile["black_profile"]["five"]:
                score += 1_400_000
                status += "+must_block_five"
            elif profile["black_profile"]["open_four"]:
                score += 320_000
                status += "+block_open_four"
            elif profile["black_profile"]["closed_four"]:
                score += 160_000
                status += "+block_closed_four"
            if profile["white_profile"]["open_four"]:
                score += 240_000
                status += "+white_open_four"
            elif profile["white_profile"]["closed_four"]:
                score += 120_000
                status += "+white_closed_four"
            if move == rapfi.get("best"):
                score += 900_000
                status += "+rapfi_best"
            elif rapfi.get("bestline") and move == rapfi["bestline"][0]:
                score += 500_000
                status += "+rapfi_principal"
        if rapfi.get("bestline") and move == rapfi["bestline"][0]:
            score += 65_000
        if move == rapfi["best"]:
            score += 50_000
        if is_book_move:
            score = max(score + book_entry[1], 1_500_000 + book_entry[1])
            status += "+" + book_entry[2]
        if is_ensemble_book_move:
            ensemble_bonus = min(360_000, 90_000 + max(entry["bonus"] for entry in ensemble_entries) // 5)
            if len(ensemble_entries) > 1:
                ensemble_bonus += 45_000 * (len(ensemble_entries) - 1)
            score += ensemble_bonus
            status += "+ensemble_book:" + ",".join(
                "%s/%s" % (entry["target"], entry["tag"]) for entry in ensemble_entries
            )
        if black_immediate_wins:
            score -= 5_000_000 + 100_000 * len(black_immediate_wins)
            status += "+allows_black_immediate_win"
        elif black_deep_threats:
            score -= 1_400_000 + 80_000 * len(black_deep_threats)
            status += "+allows_black_two_step_threat"
        scored.append(
            {
                "move": move,
                "score": score,
                "status": status,
                "black_db_replies": db_replies[:5],
                "black_immediate_wins": black_immediate_wins[:8],
                "black_two_step_threats": black_deep_threats[:8],
                "heuristic": profile["heuristic"],
                "relevance": {
                    "nearest": profile["nearest"],
                    "recent_nearest": profile["recent_nearest"],
                    "tactical": profile["tactical"],
                    "trusted_db_miss": profile["trusted_db_miss"],
                },
                "is_rapfi_best": move == rapfi["best"],
                "ensemble_entries": ensemble_entries,
            }
        )
        if move == rapfi["best"] and status == "white_immediate_win":
            break

    if not scored:
        raise ValueError("no legal white move")

    scored.sort(key=lambda r: r["score"], reverse=True)
    chosen = scored[0]
    x, y = move_to_xy(chosen["move"])
    return {
        "input": steps_to_string(steps),
        "x": x,
        "y": y,
        "selected_move": chosen["move"],
        "source": "white_hybrid",
        "source_detail": "strong local search + normalized opponent target + optional proof-tree reverse check + empirical response book + resistance search(depth=3)",
        "target": target,
        "requested_target": requested_target,
        "opponent": opponent,
        "use_black_db_reverse": use_black_db_reverse,
        "use_deep_tactics": use_deep_tactics,
        "rapfi": rapfi,
        "ignored_rapfi_moves": ignored_rapfi_moves[:8],
        "rapfi_settings": {
            "turn_time_ms": turn_time_ms,
            "max_depth": max_depth,
                "threads": threads,
        },
        "book_entry": {
            "move": book_entry[0],
            "bonus": book_entry[1],
            "tag": book_entry[2],
            "target": target,
        } if book_entry else None,
        "ensemble_book_entries": ensemble_entries_by_move,
        "chosen": chosen,
        "candidates": scored[:12],
        "candidate_count": len(scored),
        "elapsed_ms": int((time.time() - started) * 1000),
    }


def json_safe_value(value):
    if isinstance(value, float):
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        if math.isnan(value):
            return None
        return value
    if isinstance(value, list):
        return [json_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe_value(item) for item in value]
    if isinstance(value, dict):
        return {key: json_safe_value(item) for key, item in value.items()}
    return value


def safe_json_bytes(value):
    return json.dumps(json_safe_value(value), ensure_ascii=False, allow_nan=False).encode("utf-8")


def infer_black_engine(result):
    source = str(result.get("source") or "")
    if source.startswith("general_search_black"):
        return "general_search_black"
    if source.startswith("proof_tree_black"):
        return "proof_tree_black"
    if source in ("leveldb", "web_search", "opening_default"):
        return "proof_tree_black"
    return result.get("active_black_engine") or "proof_tree_black"


def attach_public_summary(result, color):
    source = result.get("source")
    summary = {
        "color": color,
        "source": source,
        "selected_move": result.get("selected_move"),
        "elapsed_ms": result.get("elapsed_ms"),
    }
    if color == "BLACK":
        active_black_engine = infer_black_engine(result)
        result["active_black_engine"] = active_black_engine
        summary.update(
            {
                "active_black_engine": active_black_engine,
                "fallback_reason": result.get("fallback_reason"),
                "db_hit": result.get("db_hit"),
            }
        )
    else:
        chosen = result.get("chosen") or {}
        summary.update(
            {
                "target": result.get("target"),
                "requested_target": result.get("requested_target"),
                "opponent": result.get("opponent"),
                "status": chosen.get("status"),
                "candidate_count": result.get("candidate_count"),
            }
        )
    result["summary"] = summary
    return result


class BaseHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "x-requested-with")
        self.set_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

    def options(self):
        self.set_status(204)
        self.finish()


class BlackNextStepHandler(BaseHandler):
    async def get(self):
        self.set_header("Content-Type", "application/json")
        try:
            steps = parse_steps(self.get_argument("stepsString", ""))
            result = await tornado.ioloop.IOLoop.current().run_in_executor(
                ENGINE_EXECUTOR,
                lambda: attach_public_summary(choose_black_move(steps), "BLACK"),
            )
            self.write(safe_json_bytes(result))
        except Exception as exc:
            self.set_status(400)
            self.write(safe_json_bytes({
                "error": type(exc).__name__,
                "message": str(exc),
                "input": self.get_argument("stepsString", ""),
            }))


class WhiteNextStepHandler(BaseHandler):
    async def get(self):
        self.set_header("Content-Type", "application/json")
        try:
            steps = parse_steps(self.get_argument("stepsString", ""))
            settings = {
                "turn_time_ms": int_setting(
                    self.get_argument("turnTimeMs", self.get_argument("turn_time_ms", None)),
                    WHITE_RAPFI_MS,
                    min_value=100,
                    max_value=600000,
                ),
                "max_depth": int_setting(
                    self.get_argument("depth", self.get_argument("maxDepth", None)),
                    WHITE_RAPFI_DEPTH,
                    min_value=1,
                    max_value=256,
                ),
                "threads": int_setting(
                    self.get_argument("threads", None),
                    WHITE_RAPFI_THREADS,
                    min_value=1,
                    max_value=64,
                ),
                "target": self.get_argument("target", None),
                "base_target": self.get_argument("baseTarget", self.get_argument("base_target", None)),
                "opponent": self.get_argument("opponent", ""),
                "deep_tactics": self.get_argument("deepTactics", "0").strip().lower() in ("1", "true", "yes", "on"),
            }
            result = await tornado.ioloop.IOLoop.current().run_in_executor(
                ENGINE_EXECUTOR,
                lambda: attach_public_summary(choose_white_move(steps, settings=settings), "WHITE"),
            )
            self.write(safe_json_bytes(result))
        except Exception as exc:
            self.set_status(400)
            self.write(
                json.dumps(
                    {
                        "error": type(exc).__name__,
                        "message": str(exc),
                        "input": self.get_argument("stepsString", ""),
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
            )


def make_app():
    return tornado.web.Application(
        [
            (r"/next_step", BlackNextStepHandler),
            (r"/white_next_step", WhiteNextStepHandler),
            (r"/(.*)", tornado.web.StaticFileHandler, {"path": os.path.join(BASE_DIR, "web"), "default_filename": "gomoku.html"}),
        ]
    )


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8090
    app = make_app()
    app.listen(port)
    print("Gokumoku listening on http://127.0.0.1:%d/gomoku.html" % port, flush=True)
    tornado.ioloop.IOLoop.current().start()
