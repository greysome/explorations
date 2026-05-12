"""Generate boards.json with no-guess boards at the requested sizes."""

import argparse
import json
import sys
import time

from generator import generate


SETS = [
    ('5x5_10', 5, 5, 10),
    ('8x8_26', 8, 8, 26),
    ('11x11_42', 11, 11, 42),
]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('out', help='output JSON path')
    p.add_argument('--n', type=int, default=20,
                   help='boards per size (default 20)')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--max-attempts', type=int, default=2000)
    p.add_argument('--max-reveals', type=int, default=10)
    p.add_argument('--min-interest', type=int, default=3)
    p.add_argument('--sets', nargs='*', default=None,
                   help='subset of set names to generate')
    args = p.parse_args()

    out = {}
    for name, w, h, M in SETS:
        if args.sets and name not in args.sets:
            continue
        print(f'=== {name} (w={w} h={h} mines={M}) ===', file=sys.stderr)
        boards = []
        t0 = time.perf_counter()
        seed_base = args.seed
        while len(boards) < args.n:
            g = generate(
                w=w, h=h, M=M, seed=seed_base,
                max_reveals=args.max_reveals,
                min_interest=args.min_interest,
                max_attempts=args.max_attempts)
            seed_base += args.max_attempts + 1
            if g is None:
                print(f'  give up after {args.max_attempts} attempts at seed_base={seed_base}',
                      file=sys.stderr)
                break
            mine_list = [i for i in range(g.board.w * g.board.h)
                         if (g.board.mines >> i) & 1]
            boards.append({
                'w': g.board.w,
                'h': g.board.h,
                'mines': mine_list,
                'reveals': list(g.reveals),
                'score': g.score,
                'seed': g.seed,
            })
            print(f'  [{len(boards)}/{args.n}] score={g.score} '
                  f'reveals={len(g.reveals)} seed={g.seed}',
                  file=sys.stderr)
        dt = time.perf_counter() - t0
        print(f'  {len(boards)} boards in {dt:.1f}s', file=sys.stderr)
        out[name] = boards

    with open(args.out, 'w') as f:
        json.dump(out, f, indent=2)
    print(f'Wrote {args.out}', file=sys.stderr)


if __name__ == '__main__':
    main()
