"""Show the seed-set diff across the four parallel_gen output files for a spec.

Usage: python seed_diff.py 5x5_10
"""

import argparse
import os
import sys

from boardsfile import load_boards


def load_seeds(path):
    if not os.path.exists(path):
        return None
    boards = load_boards(path)
    return [sb.meta.get('seed') for sb in boards]


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('spec', help='e.g. 5x5_10')
    args = p.parse_args()

    data = {}
    for tid in range(1, 5):
        path = f'{args.spec}_{tid}.boards'
        seeds = load_seeds(path)
        if seeds is None:
            print(f'  T{tid}: {path} not found', file=sys.stderr)
        else:
            data[tid] = seeds

    if not data:
        print('no files found', file=sys.stderr)
        sys.exit(1)

    sets = {tid: set(s for s in seeds if s is not None)
            for tid, seeds in data.items()}

    # Summary line
    print(f'{"thread":<8}  {"boards":>7}  {"with seed":>10}  '
          f'{"seed min":>10}  {"seed max":>10}')
    print('-' * 55)
    for tid, seeds in data.items():
        s = sets[tid]
        print(f'  T{tid}      {len(seeds):>7}  {len(s):>10}  '
              f'{min(s) if s else "":>10}  {max(s) if s else "":>10}')

    # Pairwise intersections
    tids = sorted(data)
    print()
    any_shared = False
    for i, a in enumerate(tids):
        for b in tids[i+1:]:
            shared = sets[a] & sets[b]
            if shared:
                any_shared = True
                print(f'  T{a} ∩ T{b}: {len(shared)} seeds — '
                      f'{sorted(shared)[:10]}{"..." if len(shared) > 10 else ""}')
    if not any_shared:
        print('  No seeds shared between any pair of threads.')

    # Seeds unique to each thread (vs union of all others)
    all_seeds = set().union(*sets.values())
    print()
    print(f'  Total distinct seeds across all threads: {len(all_seeds)}')
    for tid in tids:
        others = set().union(*(sets[t] for t in tids if t != tid))
        unique = sets[tid] - others
        print(f'  T{tid} unique (not in any other file): {len(unique)}')


if __name__ == '__main__':
    main()
