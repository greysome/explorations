"""Interactive Minesweeper CLI for boards from boards.json."""

import argparse
import json
import random
import re
import sys

from board import Board, render, neighbors8
from solver import _reveal_cell


CMD_RE = re.compile(r'^([fF])?\s*([a-z])\s*(\d{1,2})\s*$')


def parse_command(line, w, h):
    """Return (action, idx) where action in {'reveal','flag'} or ('quit',None) etc."""
    line = line.strip()
    if not line:
        return None
    if line in ('q', 'quit', 'exit'):
        return ('quit', None)
    if line in ('h', 'help', '?'):
        return ('help', None)
    m = CMD_RE.match(line)
    if not m:
        return ('error', f'unrecognized: {line!r}')
    f, col, row = m.groups()
    col_i = ord(col) - ord('a')
    row_i = int(row) - 1
    if not (0 <= col_i < w and 0 <= row_i < h):
        return ('error', f'out of range: {line!r}')
    idx = row_i * w + col_i
    return ('flag' if f else 'reveal', idx)


def cascade_reveal_player(board, start, revealed, flagged):
    """Player-side reveal: handles mine hit and 0-cell cascade. Returns
    (revealed, hit_mine)."""
    if (board.mines >> start) & 1:
        return revealed, True
    revealed = _reveal_cell(board, start, revealed, flagged)
    return revealed, False


def has_won(board, revealed, flagged):
    area = board.area
    full = (1 << area) - 1
    safe_mask = full & ~board.mines
    return (revealed & safe_mask) == safe_mask


def print_help():
    print()
    print('Commands:')
    print('  <col><row>     reveal cell, e.g. b3')
    print('  f<col><row>    toggle flag, e.g. fb3')
    print('  h              show this help')
    print('  q              quit')
    print()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('boards_json')
    p.add_argument('--set', dest='setname', required=True,
                   help='one of 5x5_10, 8x8_26, 11x11_42')
    p.add_argument('--index', type=int, default=None)
    args = p.parse_args()

    with open(args.boards_json) as f:
        data = json.load(f)
    if args.setname not in data:
        print(f'unknown set; available: {list(data.keys())}', file=sys.stderr)
        sys.exit(1)
    boards = data[args.setname]
    if not boards:
        print('empty set', file=sys.stderr)
        sys.exit(1)
    idx = args.index if args.index is not None else random.randrange(len(boards))
    entry = boards[idx]

    board = Board.from_mine_indices(entry['w'], entry['h'], entry['mines'])
    revealed = 0
    flagged = 0
    for r in entry['reveals']:
        revealed, hit = cascade_reveal_player(board, r, revealed, flagged)
        if hit:
            print('initial reveal hit a mine; bug?', file=sys.stderr)
            sys.exit(2)

    print(f'Playing {args.setname} board {idx} (score={entry.get("score","?")}, '
          f'reveals={len(entry["reveals"])})')
    print_help()

    while True:
        print()
        print(render(board, revealed, flagged))
        if has_won(board, revealed, flagged):
            print()
            print('You win!')
            return
        try:
            line = input('> ')
        except EOFError:
            return
        cmd = parse_command(line, board.w, board.h)
        if cmd is None:
            continue
        if cmd[0] == 'quit':
            return
        if cmd[0] == 'help':
            print_help()
            continue
        if cmd[0] == 'error':
            print(cmd[1])
            continue
        action, i = cmd
        if action == 'flag':
            flagged ^= 1 << i
        else:  # reveal
            if (flagged >> i) & 1:
                print('that cell is flagged; unflag it first')
                continue
            if (revealed >> i) & 1:
                print('already revealed')
                continue
            revealed, hit = cascade_reveal_player(board, i, revealed, flagged)
            if hit:
                print()
                print(render(board, revealed | (1 << i), flagged, show_mines=True))
                print()
                print('BOOM. You lose.')
                return


if __name__ == '__main__':
    main()
