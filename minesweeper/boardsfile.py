"""Parse/format `.boards` files.

A `.boards` file is a text file with one or more boards separated by blank
lines. Each board is:

    # w=5 h=5 mines=10 score=20 reveals=4 seed=12345
    .X.X.
    X..X.
    .....
    o.X.X
    .....

The optional `# ...` header line carries metadata; everything after `#` is
free-form key=value pairs. The grid uses:

  .  safe, hidden
  X  mine
  o  safe, initially revealed (a member of the initial reveal set)

The header is mandatory for the writer (so file consumers can find w/h
without inferring from the first board), and parsed when present by the
reader.
"""

from dataclasses import dataclass


@dataclass
class StoredBoard:
    w: int
    h: int
    mines: list   # cell indices (sorted)
    reveals: list  # cell indices (in original add order if available)
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


def parse_boards(text):
    """Yield StoredBoard objects from text."""
    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        # Skip blank lines.
        while i < n and not lines[i].strip():
            i += 1
        if i >= n:
            return
        meta = {}
        if lines[i].lstrip().startswith('#'):
            meta = _parse_header(lines[i])
            i += 1
        # Collect non-blank grid lines.
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
        for r, line in enumerate(grid_lines):
            for c, ch in enumerate(line):
                idx = r * w + c
                if ch == 'X':
                    mines.append(idx)
                elif ch == 'o':
                    reveals.append(idx)
                elif ch == '.':
                    pass
                else:
                    raise ValueError(f'unknown cell char {ch!r} at ({r},{c})')
        # If the header recorded w/h/mines, sanity-check them.
        if 'w' in meta and meta['w'] != w:
            raise ValueError(f'header w={meta["w"]} disagrees with grid w={w}')
        if 'h' in meta and meta['h'] != h:
            raise ValueError(f'header h={meta["h"]} disagrees with grid h={h}')
        if 'mines' in meta and meta['mines'] != len(mines):
            raise ValueError(
                f'header mines={meta["mines"]} disagrees with grid {len(mines)}')
        yield StoredBoard(w=w, h=h, mines=mines, reveals=reveals, meta=meta)


def format_board(w, h, mines, reveals, meta=None):
    """Return the text encoding of one board (with trailing newline,
    no separating blank line)."""
    mines_set = set(mines)
    reveals_set = set(reveals)
    out = []
    if meta is None:
        meta = {}
    meta_full = dict(meta)
    meta_full.setdefault('w', w)
    meta_full.setdefault('h', h)
    meta_full.setdefault('mines', len(mines))
    meta_full.setdefault('reveals', len(reveals))
    header = '# ' + ' '.join(f'{k}={v}' for k, v in meta_full.items())
    out.append(header)
    for r in range(h):
        row = []
        for c in range(w):
            idx = r * w + c
            if idx in mines_set:
                row.append('X')
            elif idx in reveals_set:
                row.append('o')
            else:
                row.append('.')
        out.append(''.join(row))
    return '\n'.join(out) + '\n'


def append_board(path, w, h, mines, reveals, meta=None):
    """Append one board to a .boards file (creating it if needed)."""
    text = format_board(w, h, mines, reveals, meta)
    with open(path, 'a') as f:
        f.write(text)
        f.write('\n')  # blank separator


def load_boards(path):
    with open(path) as f:
        return list(parse_boards(f.read()))
