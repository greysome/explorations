"""Generate no-guess boards and append them to `<w>x<h>_<m>.boards`.

Each call adds to the corresponding file rather than overwriting it.
"""

import argparse
import os
import random
import sys
import time

from board import Board
from boardsfile import append_board
from gen_board import pregenerate_dense_board
from generator import (
    build_reveal_set, minimize, _try_solve, interest_score)
from solver import SOLVED


SETS = [
    (5, 5, 10),
    (8, 8, 26),
    (11, 11, 42),
]


def boards_filename(outdir, w, h, M):
    return os.path.join(outdir, f'{w}x{h}_{M}.boards')


def generate_one(w, h, M, seed, max_reveals, min_interest, max_attempts,
                 max_uncovered, verbose):
    """Run forward + minimize + score on attempts until a good board appears.

    Returns (board, reveals, score, seed, attempts_used) or None on give-up.
    """
    for attempt in range(max_attempts):
        a_seed = seed + attempt
        rng = random.Random(a_seed)
        mines = pregenerate_dense_board(rng, w, h, M, max_uncovered=max_uncovered)
        board = Board.from_mine_indices(w, h, mines)

        reveals, log = build_reveal_set(board, M, rng, max_reveals)
        if reveals is None:
            if verbose:
                print(f'    attempt {attempt} seed={a_seed}: forward pass FAILED', flush=True)
            continue

        reveals = minimize(board, M, reveals)
        _, _, status, log = _try_solve(board, reveals, M)
        if status != SOLVED:
            if verbose:
                print(f'    attempt {attempt} seed={a_seed}: minimize broke solvability', flush=True)
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
    p = argparse.ArgumentParser()
    p.add_argument('--outdir', default='.',
                   help='directory to write *.boards files in')
    p.add_argument('--n', type=int, default=20,
                   help='boards to append per size')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--max-attempts', type=int, default=300)
    p.add_argument('--max-reveals', type=int, default=10)
    p.add_argument('--min-interest', type=int, default=5)
    p.add_argument('--sets', nargs='*', default=None,
                   help='restrict to sizes like 5x5_10')
    p.add_argument('--verbose', '-v', action='store_true',
                   help='print every attempt including rejections')
    args = p.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    for w, h, M in SETS:
        name = f'{w}x{h}_{M}'
        if args.sets and name not in args.sets:
            continue
        print(f'=== {name} (w={w} h={h} mines={M}) ===', flush=True)
        path = boards_filename(args.outdir, w, h, M)
        if args.verbose:
            print(f'  appending to {path}', flush=True)
        # Heuristic max_uncovered (same as generator's default).
        if w * h <= 36:
            mu = 0
        elif w * h <= 64:
            mu = 6
        else:
            mu = max(8, w * h // 15)

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
                print(f'  give up after {args.max_attempts} attempts '
                      f'starting at seed={seed_cursor}', flush=True)
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
