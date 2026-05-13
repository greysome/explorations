"""Parse/format `.boards` files.

A `.boards` file is a text file with one or more boards separated by blank
lines. Each board is:

    # w=5 h=5 mines=10 score=20 reveals=4 seed=12345
    .,.,.
    ,..,.
    .....
    1.,.2
    .....

The optional `# ...` header line carries metadata; everything after `#` is
free-form key=value pairs. The grid uses:

  ,           a mine (hidden from the player; ground truth)
  0-8         an initially-revealed safe cell, the digit being its clue
              (count of adjacent mines)
  .           a safe cell that is not initially revealed
"""

from dataclasses import dataclass


@dataclass
class StoredBoard:
    w: int
    h: int
    mines: list   # cell indices (sorted)
    reveals: list  # cell indices, in row-major order
    meta: dict


def _parse_header(line):
    line = line.lstrip('#').strip()
    meta = {}
    for tok in line.split():
        if '=' in tok:
            k, v = tok.split('=', 1)
            try:
                meta[k] = int(v)
            except ValueError:
                meta[k] = v
    return meta


def _count_adjacent_mines(w, h, mines_set, idx):
    r, c = divmod(idx, w)
    n = 0
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            rr, cc = r + dr, c + dc
            if 0 <= rr < h and 0 <= cc < w:
                if rr * w + cc in mines_set:
                    n += 1
    return n


def parse_boards(text):
    """Yield StoredBoard objects from text."""
    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        while i < n and not lines[i].strip():
            i += 1
        if i >= n:
            return
        meta = {}
        if lines[i].lstrip().startswith('#'):
            meta = _parse_header(lines[i])
            i += 1
        grid_lines = []
        while i < n and lines[i].strip():
            grid_lines.append(lines[i].rstrip())
            i += 1
        if not grid_lines:
            continue
        h = len(grid_lines)
        w = len(grid_lines[0])
        for r, line in enumerate(grid_lines):
            if len(line) != w:
                raise ValueError(
                    f'inconsistent row width at row {r}: '
                    f'{len(line)} != {w}')
        mines = []
        reveals = []
        revealed_digits = {}
        for r, line in enumerate(grid_lines):
            for c, ch in enumerate(line):
                idx = r * w + c
                if ch == ',':
                    mines.append(idx)
                elif ch == '.':
                    pass
                elif ch.isdigit():
                    revealed_digits[idx] = int(ch)
                    reveals.append(idx)
                else:
                    raise ValueError(f'unknown cell char {ch!r} at ({r},{c})')
        # Verify the revealed digits match the mine layout.
        mines_set = set(mines)
        for idx, claimed in revealed_digits.items():
            actual = _count_adjacent_mines(w, h, mines_set, idx)
            if claimed != actual:
                r, c = divmod(idx, w)
                raise ValueError(
                    f'revealed digit at ({r},{c}) is {claimed} '
                    f'but adjacent-mine count is {actual}')
        if 'w' in meta and meta['w'] != w:
            raise ValueError(f'header w={meta["w"]} disagrees with grid w={w}')
        if 'h' in meta and meta['h'] != h:
            raise ValueError(f'header h={meta["h"]} disagrees with grid h={h}')
        if 'mines' in meta and meta['mines'] != len(mines):
            raise ValueError(
                f'header mines={meta["mines"]} disagrees with grid {len(mines)}')
        yield StoredBoard(w=w, h=h, mines=mines, reveals=reveals, meta=meta)


def format_board(w, h, mines, reveals, meta=None, *, header=True):
    """Return the text encoding of one board (trailing newline).

    `mines` and `reveals` are cell indices. Revealed cells are written as
    their clue digit (count of adjacent mines). Pass header=False to omit
    the metadata comment line.
    """
    mines_set = set(mines)
    reveals_set = set(reveals)
    out = []
    if header:
        if meta is None:
            meta = {}
        meta_full = dict(meta)
        meta_full.setdefault('w', w)
        meta_full.setdefault('h', h)
        meta_full.setdefault('mines', len(mines))
        meta_full.setdefault('reveals', len(reveals))
        out.append('# ' + ' '.join(f'{k}={v}' for k, v in meta_full.items()))
    for r in range(h):
        row = []
        for c in range(w):
            idx = r * w + c
            if idx in mines_set:
                row.append(',')
            elif idx in reveals_set:
                row.append(str(_count_adjacent_mines(w, h, mines_set, idx)))
            else:
                row.append('.')
        out.append(''.join(row))
    return '\n'.join(out) + '\n'


def append_board(path, w, h, mines, reveals, meta=None):
    text = format_board(w, h, mines, reveals, meta)
    with open(path, 'a') as f:
        f.write(text)
        f.write('\n')


def load_boards(path):
    with open(path) as f:
        return list(parse_boards(f.read()))
