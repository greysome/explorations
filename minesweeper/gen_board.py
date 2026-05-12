"""Python port of pregenerate_dense_board from gen_board.c.

Generates "dense" Minesweeper layouts: mine placements where at most
`max_uncovered` cells have zero adjacent mines (i.e. almost every cell
shows a non-zero clue when revealed).
"""

import argparse
import random
import sys
import time


def adjacent_square(sq, w, h, dir):
    """Return neighbor index in the 3x3 around sq for dir 0..8, or None.

    dir layout (dir=4 is the cell itself, matching gen_board.c):
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

    # Initial pass: sequentially decide each cell.
    for sq in range(area):
        if len(mines) == mine_count:
            break
        # Same Bernoulli draw as the C: with probability
        # (mine_count - placed) / (area - sq), place a mine.
        if rng.randrange(area - sq) < mine_count - len(mines):
            mines.append(sq)
            for d in range(9):
                adj = adjacent_square(sq, w, h, d)
                if adj is not None:
                    covered_counts[adj] += 1

    # Swap phase: while too many cells have zero adjacent mines, move a
    # redundant mine onto one of them.
    while True:
        uncovered = [sq for sq in range(area) if covered_counts[sq] == 0]
        if len(uncovered) <= max_uncovered:
            break

        uncovered_sq = uncovered[rng.randrange(len(uncovered))]
        # Pretend to place a mine at uncovered_sq.
        for d in range(9):
            adj = adjacent_square(uncovered_sq, w, h, d)
            if adj is not None:
                covered_counts[adj] += 1

        # Find a redundant mine: one whose entire 3x3 is covered > 1.
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


def render_mines(w, h, mines):
    mines_set = set(mines)
    out = []
    for y in range(h):
        row = []
        for x in range(w):
            row.append('X' if y * w + x in mines_set else '.')
        out.append(''.join(row))
    return '\n'.join(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--w', type=int, default=11)
    p.add_argument('--h', type=int, default=11)
    p.add_argument('--mines', type=int, default=30)
    p.add_argument('--max-uncovered', type=int, default=0)
    p.add_argument('--n', type=int, default=100000)
    p.add_argument('--seed', type=int, default=None)
    p.add_argument('--dump', action='store_true',
                   help='print the first generated board')
    args = p.parse_args()

    rng = random.Random(args.seed)
    print(f'seed = {args.seed}', file=sys.stderr)

    first = None
    t0 = time.perf_counter_ns()
    for i in range(args.n):
        mines = pregenerate_dense_board(
            rng, args.w, args.h, args.mines, args.max_uncovered)
        if i == 0:
            first = mines
    t1 = time.perf_counter_ns()

    elapsed = (t1 - t0) / 1e9
    per_us = elapsed / args.n * 1e6
    print(f'{elapsed:f}s to generate {args.n} boards ({per_us:f}us per board)',
          file=sys.stderr)

    if args.dump and first is not None:
        print(render_mines(args.w, args.h, first))


if __name__ == '__main__':
    main()
