"""Generate no-guess Minesweeper boards and append them to a `.boards`
file named after their size.

  python make_boards.py 5x5_10 [--n 20] [-v]

The positional argument has the form `<w>x<h>_<m>`, e.g. `5x5_10`. The
output file is `<w>x<h>_<m>.boards`.

This module also owns `pregenerate_dense_board` (ported from the
gen_board.c routine that picks a mine layout where almost every cell is
adjacent to at least one mine).
"""

import argparse
import os
import random
import re
import sys
import time

from board import Board
from boardsfile import append_board
from generator import (
    build_reveal_set, minimize, _try_solve, interest_score)
from solver import SOLVED


# --- pregenerate_dense_board (Python port of gen_board.c) ---

def adjacent_square(sq, w, h, dir):
    """Neighbor index in the 3x3 around `sq` for dir 0..8, or None.

    Layout (dir=4 is the cell itself, matching gen_board.c):
        0 1 2
        3 4 5
        6 7 8
    """
    x = sq % w
    y = sq // w
    if dir == 0 and x > 0 and y > 0:       return sq - w - 1
    if dir == 1 and y > 0:                 return sq - w
    if dir == 2 and x < w - 1 and y > 0:   return sq - w + 1
    if dir == 3 and x > 0:                 return sq - 1
    if dir == 4:                           return sq
    if dir == 5 and x < w - 1:             return sq + 1
    if dir == 6 and x > 0 and y < h - 1:   return sq + w - 1
    if dir == 7 and y < h - 1:             return sq + w
    if dir == 8 and x < w - 1 and y < h - 1: return sq + w + 1
    return None


def pregenerate_dense_board(rng, w, h, mine_count, max_uncovered=0):
    """Return a list of mine cell indices for a dense board.

    Mirrors pregenerate_dense_board() in gen_board.c.
    """
    area = w * h
    assert 3 <= w and 3 <= h and area <= 121
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


# --- board generation outer loop ---

SPEC_RE = re.compile(r'^(\d+)x(\d+)_(\d+)$')


def parse_spec(s):
    m = SPEC_RE.match(s)
    if not m:
        raise argparse.ArgumentTypeError(
            f'expected <w>x<h>_<m>, got {s!r}')
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def default_max_uncovered(w, h):
    """Same heuristic the generator used: more 0-clue cells allowed on
    bigger boards so the solver's frontier stays tractable."""
    area = w * h
    if area <= 36:
        return 0
    if area <= 64:
        return 6
    return max(8, area // 15)


def generate_one(w, h, M, seed, max_reveals, min_interest, max_attempts,
                 max_uncovered, verbose):
    for attempt in range(max_attempts):
        a_seed = seed + attempt
        rng = random.Random(a_seed)
        mines = pregenerate_dense_board(
            rng, w, h, M, max_uncovered=max_uncovered)
        board = Board.from_mine_indices(w, h, mines)

        reveals, log = build_reveal_set(board, M, rng, max_reveals)
        if reveals is None:
            if verbose:
                print(f'    attempt {attempt} seed={a_seed}: forward pass FAILED',
                      flush=True)
            continue

        reveals = minimize(board, M, reveals)
        _, _, status, log = _try_solve(board, reveals, M)
        if status != SOLVED:
            if verbose:
                print(f'    attempt {attempt} seed={a_seed}: '
                      f'minimize broke solvability', flush=True)
            continue
        score = interest_score(log)
        if score < min_interest:
            if verbose:
                print(f'    attempt {attempt} seed={a_seed}: REJECTED '
                      f'score={score} < {min_interest} '
                      f'(reveals={len(reveals)}, '
                      f'enum_rounds={log.enum_rounds}, '
                      f'max_comp={log.max_component_size})', flush=True)
            continue
        if verbose:
            print(f'    attempt {attempt} seed={a_seed}: KEEP '
                  f'score={score} reveals={len(reveals)}', flush=True)
        return board, reveals, score, a_seed, attempt + 1
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('spec', type=parse_spec,
                   help='board size: <w>x<h>_<m>, e.g. 5x5_10')
    p.add_argument('--outdir', default='.',
                   help='directory for the .boards file')
    p.add_argument('--n', type=int, default=20,
                   help='boards to append')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--max-attempts', type=int, default=300)
    p.add_argument('--max-reveals', type=int, default=10)
    p.add_argument('--min-interest', type=int, default=5)
    p.add_argument('--max-uncovered', type=int, default=None,
                   help='cap on 0-clue cells in the dense layout '
                        '(default scales with board area)')
    p.add_argument('--verbose', '-v', action='store_true',
                   help='log every attempt including rejections')
    args = p.parse_args()

    w, h, M = args.spec
    mu = args.max_uncovered
    if mu is None:
        mu = default_max_uncovered(w, h)

    os.makedirs(args.outdir, exist_ok=True)
    path = os.path.join(args.outdir, f'{w}x{h}_{M}.boards')
    print(f'=== {w}x{h}_{M} (mines={M}, max_uncovered={mu}) -> {path} ===',
          flush=True)

    added = 0
    seed_cursor = args.seed
    t0 = time.perf_counter()
    while added < args.n:
        result = generate_one(
            w=w, h=h, M=M, seed=seed_cursor,
            max_reveals=args.max_reveals,
            min_interest=args.min_interest,
            max_attempts=args.max_attempts,
            max_uncovered=mu, verbose=args.verbose)
        if result is None:
            print(f'  give up after {args.max_attempts} attempts starting '
                  f'at seed={seed_cursor}', flush=True)
            seed_cursor += args.max_attempts
            continue
        board, reveals, score, used_seed, attempts_used = result
        mine_list = sorted(
            i for i in range(board.area) if (board.mines >> i) & 1)
        meta = {
            'w': w, 'h': h, 'mines': M,
            'score': score, 'reveals': len(reveals),
            'seed': used_seed,
        }
        append_board(path, w, h, mine_list, list(reveals), meta=meta)
        added += 1
        print(f'  [{added}/{args.n}] kept score={score} reveals={len(reveals)} '
              f'seed={used_seed} ({attempts_used} attempts)', flush=True)
        seed_cursor = used_seed + 1
    dt = time.perf_counter() - t0
    print(f'  appended {added} boards in {dt:.1f}s -> {path}', flush=True)


if __name__ == '__main__':
    main()
