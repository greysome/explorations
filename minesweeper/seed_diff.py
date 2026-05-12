"""Show seeds accepted by T1 but rejected by T2/T3/T4.

Run parallel_gen.py first (all four threads share the same seed range).
Then this script identifies which seeds T1 accepted but other threads
filtered out — i.e. what each stricter strategy rejects.

Usage: python seed_diff.py 5x5_10
"""

import argparse
import os
import sys

from boardsfile import load_boards


def load_seeds(path):
    if not os.path.exists(path):
        return None
    return [sb.meta.get('seed') for sb in load_boards(path)
            if sb.meta.get('seed') is not None]


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('spec', help='e.g. 5x5_10')
    p.add_argument('--show', type=int, default=20,
                   help='max number of rejected seeds to list per thread')
    args = p.parse_args()

    sets = {}
    for tid in range(1, 5):
        path = f'{args.spec}_{tid}.boards'
        seeds = load_seeds(path)
        if seeds is None:
            print(f'  T{tid}: {path} not found', file=sys.stderr)
            sets[tid] = set()
        else:
            sets[tid] = set(seeds)

    print(f'{"thread":<8}  {"accepted":>10}')
    print('-' * 22)
    for tid in range(1, 5):
        print(f'  T{tid}      {len(sets[tid]):>10}')

    t1 = sets[1]
    if not t1:
        print('\nno T1 data')
        return

    # Threads progress through seeds at different rates (T1 is slowest per
    # seed since it always runs the full max_reveals loop). Restrict the
    # comparison to the seed range every thread has reached.
    common_max = min(max(sets[t]) for t in range(1, 5) if sets[t])
    common_min = max(min(sets[t]) for t in range(1, 5) if sets[t])
    in_range = lambda s: common_min <= s <= common_max
    print(f'\nComparing common seed range [{common_min}, {common_max}]')

    t1_in = {s for s in t1 if in_range(s)}
    for tid in (2, 3, 4):
        other_in = {s for s in sets[tid] if in_range(s)}
        rejected = sorted(t1_in - other_in)
        kept_anyway = sorted(other_in - t1_in)
        pct = 100 * len(rejected) / len(t1_in) if t1_in else 0
        print(f'\nT1 \\ T{tid}: {len(rejected)}/{len(t1_in)} '
              f'({pct:.1f}%) — accepted by T1 but rejected by T{tid}')
        if rejected:
            shown = rejected[:args.show]
            tail = f'  (+{len(rejected) - len(shown)} more)' if len(rejected) > len(shown) else ''
            print(f'  {shown}{tail}')
        if kept_anyway:
            # T1 should be a strict superset within the common range.
            print(f'  WARNING: {len(kept_anyway)} seeds in T{tid} but not T1 '
                  f'(unexpected): {kept_anyway[:args.show]}')


if __name__ == '__main__':
    main()
