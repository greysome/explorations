"""No-guess Minesweeper board generator.

Usage:
    python make_boards.py 5x5_10 [--n 20] [--seed 0] [--outdir .] [-v]

Writes N board files named YYYY-MM-DD_WxH-M.board starting from today.
"""

import argparse
import datetime
import os
import random
import re
import sys
import time

from board import Board, iter_bits
from boardsfile import format_board
from solver import solve, SOLVED, STUCK, _reveal_cell


# ── dense layout generator (port of gen_board.c) ─────────────────────────────

def adjacent_square(sq, w, h, dir):
    x = sq % w
    y = sq // w
    if dir == 0 and x > 0 and y > 0:        return sq - w - 1
    if dir == 1 and y > 0:                  return sq - w
    if dir == 2 and x < w-1 and y > 0:      return sq - w + 1
    if dir == 3 and x > 0:                  return sq - 1
    if dir == 4:                            return sq
    if dir == 5 and x < w-1:               return sq + 1
    if dir == 6 and x > 0 and y < h-1:      return sq + w - 1
    if dir == 7 and y < h-1:               return sq + w
    if dir == 8 and x < w-1 and y < h-1:   return sq + w + 1
    return None


def pregenerate_dense_board(rng, w, h, mine_count, max_uncovered=0):
    """Return a list of mine cell indices for a dense board."""
    area = w * h
    assert 3 <= w and 3 <= h and area <= 1024
    assert 0 <= mine_count <= area

    covered_counts = [0] * area
    mines = []

    for sq in range(area):
        if len(mines) == mine_count:
            break
        if rng.randrange(area - sq) < mine_count - len(mines):
            mines.append(sq)
            for d in range(9):
                adj = adjacent_square(sq, w, h, d)
                if adj is not None:
                    covered_counts[adj] += 1

    while True:
        uncovered = [sq for sq in range(area) if covered_counts[sq] == 0]
        if len(uncovered) <= max_uncovered:
            break
        uncovered_sq = uncovered[rng.randrange(len(uncovered))]
        for d in range(9):
            adj = adjacent_square(uncovered_sq, w, h, d)
            if adj is not None:
                covered_counts[adj] += 1
        for i, mine_sq in enumerate(mines):
            is_redundant = True
            for d in range(9):
                adj = adjacent_square(mine_sq, w, h, d)
                if adj is not None and covered_counts[adj] == 1:
                    is_redundant = False
                    break
            if is_redundant:
                for d in range(9):
                    adj = adjacent_square(mine_sq, w, h, d)
                    if adj is not None:
                        covered_counts[adj] -= 1
                mines[i] = uncovered_sq
                break

    return mines


# ── solver interface ──────────────────────────────────────────────────────────

def _initial_revealed(board, reveals):
    revealed = 0
    flagged = 0
    for r in reveals:
        if not (revealed >> r) & 1:
            revealed = _reveal_cell(board, r, revealed, flagged)
    return revealed, flagged


def _try_solve(board, reveals, M):
    revealed, flagged = _initial_revealed(board, reveals)
    return solve(board, revealed, flagged, M)


def interest_score(log):
    """Kept for parallel_gen.py's T4 interest filter."""
    if log is None:
        return 0
    s = log.enum_rounds + log.max_component_size + log.enum_deductions
    if log.global_count_decisive:
        s += 5
    return s


# ── forward / backward reveal-set search ─────────────────────────────────────

def build_reveal_set(board, M, rng):
    """Forward pass: greedily add reveals until solver wins.

    Returns (reveals, log) or (None, None).
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

    while True:
        if status == SOLVED:
            return reveals, log

        hidden_safe = [i for i in safe_cells if not ((revealed >> i) & 1)]
        if not hidden_safe:
            return reveals, log

        sample = hidden_safe if len(hidden_safe) <= 8 else rng.sample(hidden_safe, 8)
        current_covered = revealed.bit_count() + flagged.bit_count()
        best, best_gain, best_log = None, -1, None
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

        if best is None or best_gain <= current_covered + 1:
            return None, None

        reveals.append(best)
        revealed, flagged, status, log = best_rev, best_fl, best_status, best_log


def minimize(board, M, reveals):
    """Backward pass: drop reveals that are now redundant."""
    result = list(reveals)
    i = len(result) - 1
    while i >= 0:
        trial = result[:i] + result[i+1:]
        if trial:
            _, _, status, _ = _try_solve(board, trial, M)
            if status == SOLVED:
                result = trial
        i -= 1
    return result


def generate(w, h, M, seed=0, max_attempts=500, verbose=False):
    """Generate one no-guess board. Returns (board, reveals) or None."""
    for attempt in range(max_attempts):
        rng = random.Random(seed * 1_000_003 + attempt)
        mines = pregenerate_dense_board(rng, w, h, M, max_uncovered=0)
        board = Board.from_mine_indices(w, h, mines)

        reveals, _ = build_reveal_set(board, M, rng)
        if reveals is None:
            if verbose:
                print(f'  attempt {attempt}: forward pass failed', flush=True)
            continue

        reveals = minimize(board, M, reveals)
        _, _, status, _ = _try_solve(board, reveals, M)
        if status != SOLVED:
            if verbose:
                print(f'  attempt {attempt}: minimize broke solvability', flush=True)
            continue

        if verbose:
            print(f'  attempt {attempt}: ok reveals={len(reveals)}', flush=True)
        return board, reveals

    return None


# ── CLI ───────────────────────────────────────────────────────────────────────

SPEC_RE = re.compile(r'^(\d+)x(\d+)_(\d+)$')


def parse_spec(s):
    m = SPEC_RE.match(s)
    if not m:
        raise argparse.ArgumentTypeError(f'expected <w>x<h>_<m>, got {s!r}')
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('spec', type=parse_spec, help='e.g. 5x5_10')
    p.add_argument('--n', type=int, default=20, help='number of boards to generate')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--max-attempts', type=int, default=500)
    p.add_argument('--outdir', default='.', help='output directory')
    p.add_argument('--verbose', '-v', action='store_true')
    args = p.parse_args()

    w, h, M = args.spec
    os.makedirs(args.outdir, exist_ok=True)
    today = datetime.date.today()
    t0 = time.perf_counter()

    for i in range(args.n):
        date = today + datetime.timedelta(days=i)
        filename = f'{date}_{w}x{h}-{M}.board'
        path = os.path.join(args.outdir, filename)

        if args.verbose:
            print(f'[{i+1}/{args.n}] {filename}', flush=True)

        result = generate(w, h, M, seed=args.seed + i,
                          max_attempts=args.max_attempts, verbose=args.verbose)
        if result is None:
            print(f'WARNING: failed to generate board for {date}', file=sys.stderr)
            continue

        board, reveals = result
        mine_list = sorted(
            j for j in range(board.area) if (board.mines >> j) & 1)
        with open(path, 'w') as f:
            f.write(format_board(w, h, mine_list, reveals, header=False))

        if not args.verbose:
            print(f'[{i+1}/{args.n}] {filename}  reveals={len(reveals)}', flush=True)

    dt = time.perf_counter() - t0
    print(f'done in {dt:.1f}s', flush=True)


if __name__ == '__main__':
    main()
