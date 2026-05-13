"""Four-threaded board generator strategy comparison.

Usage:
    python parallel_gen.py 5x5_10 [--seed 0] [--max-reveals 10] [--min-interest 3]

Writes to <spec>_1.boards ... <spec>_4.boards and prints running avg reveals.

Thread 1  forward only, no stagnation check, returns reveals even if not SOLVED
Thread 2  forward only, stagnation check, requires SOLVED
Thread 3  forward + backward minimize
Thread 4  forward + backward + interest score filter
"""

import argparse
import random
import re
import sys
import threading
import time

from board import Board
from boardsfile import append_board
from make_boards import (interest_score, _try_solve, minimize,
                         pregenerate_dense_board)
from solver import SOLVED

# ── per-thread behaviour flags ──────────────────────────────────────────────
# When REQUIRE_PROGRESS is True: if the best candidate only reveals itself
# (no new deductions), the forward pass gives up (returns None).
# When False: keep appending the best candidate regardless, and return
# whatever reveal set was built even if the solver didn't finish (SOLVED).

REQUIRE_PROGRESS = {1: False, 2: True,  3: True,  4: True}
DO_MINIMIZE      = {1: False, 2: False, 3: True,  4: True}
FILTER_INTEREST  = {1: False, 2: False, 3: False, 4: True}


def build_reveal_set(board, M, rng, max_reveals, *, require_progress):
    """Forward pass.

    With require_progress=False (thread 1): never gives up, returns the
    accumulated reveal list regardless of whether the board is SOLVED.
    With require_progress=True (threads 2-4): returns None if stagnant or
    not SOLVED within the budget.
    """
    area = board.area
    mines = board.mines
    safe_cells = [i for i in range(area) if not ((mines >> i) & 1)]
    if not safe_cells:
        return None, None

    zero_safe = [i for i in safe_cells if board.counts[i] == 0]
    if zero_safe:
        seed_cell = rng.choice(zero_safe)
    else:
        seed_pool = sorted(safe_cells, key=lambda i: board.counts[i])
        seed_cell = rng.choice(seed_pool[:max(3, len(seed_pool) // 4)])

    reveals = [seed_cell]
    revealed, flagged, status, log = _try_solve(board, reveals, M)
    if status == SOLVED:
        return reveals, log

    for _ in range(max_reveals - 1):
        if status == SOLVED:
            return reveals, log

        hidden_safe = [i for i in safe_cells if not ((revealed >> i) & 1)]
        if not hidden_safe:
            return reveals, log

        sample = hidden_safe if len(hidden_safe) <= 8 else rng.sample(hidden_safe, 8)
        current_covered = revealed.bit_count() + flagged.bit_count()

        best = None
        best_gain = -1
        best_log = None
        for cand in sample:
            trial = reveals + [cand]
            tr_rev, tr_fl, tr_status, tr_log = _try_solve(board, trial, M)
            gain = tr_rev.bit_count() + tr_fl.bit_count()
            if tr_status == SOLVED:
                gain += 10000
            if gain > best_gain:
                best_gain = gain
                best = cand
                best_log = tr_log
                best_rev, best_fl, best_status = tr_rev, tr_fl, tr_status

        if best is None:
            if require_progress:
                return None, None
            break

        if require_progress and best_gain <= current_covered + 1:
            # Candidate only reveals itself — no deduction progress.
            return None, None

        reveals.append(best)
        revealed, flagged, status, log = best_rev, best_fl, best_status, best_log

    if status == SOLVED:
        return reveals, log
    if not require_progress:
        return reveals, log
    return None, None


def worker(tid, w, h, M, max_reveals, min_interest,
           seed_start, out_path, stats, stats_lock, file_lock):
    req_progress = REQUIRE_PROGRESS[tid]
    do_min = DO_MINIMIZE[tid]
    filter_int = FILTER_INTEREST[tid]

    seed = seed_start
    while True:
        rng = random.Random(seed)
        mines = pregenerate_dense_board(rng, w, h, M, max_uncovered=0)
        board = Board.from_mine_indices(w, h, mines)

        reveals, log = build_reveal_set(
            board, M, rng, max_reveals, require_progress=req_progress)

        if reveals is None:
            seed += 1
            continue

        if do_min:
            reveals = minimize(board, M, reveals)
            _, _, status, log = _try_solve(board, reveals, M)
            if status != SOLVED:
                seed += 1
                continue

        score = interest_score(log) if log is not None else 0
        if filter_int and score < min_interest:
            seed += 1
            continue

        mine_list = sorted(i for i in range(board.area) if (board.mines >> i) & 1)
        meta = {'w': w, 'h': h, 'mines': M,
                'score': score, 'reveals': len(reveals), 'seed': seed}
        with file_lock:
            append_board(out_path, w, h, mine_list, list(reveals), meta=meta)

        with stats_lock:
            stats[tid]['count'] += 1
            stats[tid]['total_reveals'] += len(reveals)
            hist = stats[tid]['hist']
            hist[len(reveals)] = hist.get(len(reveals), 0) + 1

        seed += 1


SPEC_RE = re.compile(r'^(\d+)x(\d+)_(\d+)$')

_BARS = ' ▁▂▃▄▅▆▇█'

def _render_hist(hist):
    if not hist:
        return '    (no data)'
    lo, hi = min(hist), max(hist)
    mx = max(hist.values())
    parts = []
    for k in range(lo, hi + 1):
        v = hist.get(k, 0)
        level = round(v / mx * 8) if mx else 0
        parts.append(f'{k}:{_BARS[level]}')
    return '    ' + ' '.join(parts)

LABELS = {
    1: 'fwd (no-stagnation-check)',
    2: 'fwd',
    3: 'fwd+bwd',
    4: 'fwd+bwd+interest',
}


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('spec', help='e.g. 5x5_10')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--max-reveals', type=int, default=10)
    p.add_argument('--min-interest', type=int, default=3)
    p.add_argument('--print-interval', type=float, default=2.0,
                   help='seconds between stats lines')
    args = p.parse_args()

    m = SPEC_RE.match(args.spec)
    if not m:
        print(f'bad spec {args.spec!r}, want <w>x<h>_<m>', file=sys.stderr)
        sys.exit(1)
    w, h, M = int(m.group(1)), int(m.group(2)), int(m.group(3))

    stats = {tid: {'count': 0, 'total_reveals': 0, 'hist': {}} for tid in range(1, 5)}
    stats_lock = threading.Lock()

    threads = []
    for tid in range(1, 5):
        out_path = f'{args.spec}_{tid}.boards'
        file_lock = threading.Lock()
        t = threading.Thread(
            target=worker,
            args=(tid, w, h, M, args.max_reveals, args.min_interest,
                  args.seed, out_path,
                  stats, stats_lock, file_lock),
            daemon=True,
        )
        t.start()
        threads.append(t)

    NLINES = 8  # 2 lines per thread (summary + histogram)
    print(f'Generating {args.spec} — 4 threads — Ctrl-C to stop')
    print(f'{"Thread":<6}  {"strategy":<28}  {"boards":>7}  {"avg reveals":>12}')
    print('-' * 60)
    print('\n' * NLINES, end='')  # reserve space for the data block

    try:
        while True:
            time.sleep(args.print_interval)
            with stats_lock:
                snap = {tid: dict(v) for tid, v in stats.items()}
            print(f'\033[{NLINES}A', end='')  # move up to start of data block
            for tid in range(1, 5):
                c = snap[tid]['count']
                avg = snap[tid]['total_reveals'] / c if c else float('nan')
                print(f'  T{tid}    {LABELS[tid]:<28}  {c:>7}  {avg:>12.2f}')
                print(_render_hist(snap[tid]['hist']))
    except KeyboardInterrupt:
        pass

    with stats_lock:
        snap = {tid: dict(v) for tid, v in stats.items()}
    print('\nFinal:')
    for tid in range(1, 5):
        c = snap[tid]['count']
        avg = snap[tid]['total_reveals'] / c if c else float('nan')
        out = f'{args.spec}_{tid}.boards'
        print(f'  T{tid} {LABELS[tid]}: {c} boards, avg {avg:.2f} reveals -> {out}')
        print(_render_hist(snap[tid]['hist']))


if __name__ == '__main__':
    main()
