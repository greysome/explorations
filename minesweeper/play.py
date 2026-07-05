#!/usr/bin/env python3
"""Tkinter Minesweeper UI that loads JSON board specs.

  python play.py [path ...]

Standalone: only depends on the Python standard library (tkinter included).

Positional args:
  - a `.json` file: add it to the picker.
  - a directory: add every `*.json` in it.
  - no args: scan the current directory.

Each `.json` file is JSON Lines (one board per line). Each line:

    {
      "w": 5, "h": 5,
      "board":   "!!23!24!5!13!5!1!34!12!21",  // len w*h; '!' = mine,
                                               //          '0'..'8' = clue
      "reveals": [0, 8, ...],                  // initially-revealed cells
      "mines":   10,                           // optional: mine count check
      "difficulty": 0.42,                      // shown in the toolbar
      ...                                      // any extra metadata is kept
    }

The `difficulty` value is displayed as-is; floats are formatted to 3 decimals.
Any keys other than the ones above are shown as `key=value` in the status area.

Controls:
  - Left click a hidden cell to reveal it.
  - Right click a hidden cell to toggle a flag.

A mine counter (`mines - flags`) shows in the top bar.
"""

import argparse
import glob
import json
import os
import sys
import tkinter as tk
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from tkinter import ttk


# ---------------------------------------------------------------------------
# Board model (inlined from board.py so play.py stands alone).
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def neighbors8(w, h):
    """Per-cell 8-neighbor index lists (no self), row-major."""
    out = []
    for r in range(h):
        for c in range(w):
            ns = []
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < h and 0 <= cc < w:
                        ns.append(rr * w + cc)
            out.append(ns)
    return out


@dataclass
class Board:
    w: int
    h: int
    mines: int    # bitset of mine cells
    counts: list  # per-cell adjacent-mine count

    @classmethod
    def from_mine_indices(cls, w, h, mine_indices):
        mines = 0
        for i in mine_indices:
            mines |= 1 << i
        ns = neighbors8(w, h)
        counts = [
            sum(1 for j in ns[i] if (mines >> j) & 1)
            for i in range(w * h)
        ]
        return cls(w=w, h=h, mines=mines, counts=counts)

    @property
    def area(self):
        return self.w * self.h


def _reveal_cell(board, i, revealed, flagged):
    """Reveal cell i. If it's a 0-cell, cascade to all connected 0-cells."""
    if (board.mines >> i) & 1:
        raise RuntimeError(f'tried to reveal mine at {i}')
    if board.counts[i] != 0:
        return revealed | (1 << i)
    ns = neighbors8(board.w, board.h)
    q = deque([i])
    while q:
        j = q.popleft()
        jb = 1 << j
        if revealed & jb:
            continue
        revealed |= jb
        if board.counts[j] == 0:
            for k in ns[j]:
                kb = 1 << k
                if not (revealed & kb) and not (flagged & kb):
                    q.append(k)
    return revealed


DIGIT_COLORS = {
    1: '#1976d2', 2: '#388e3c', 3: '#d32f2f', 4: '#7b1fa2',
    5: '#f57c00', 6: '#0097a7', 7: '#212121', 8: '#616161',
}

REQUIRED_KEYS = ('w', 'h', 'board', 'reveals')
DISPLAY_KEYS = {'w', 'h', 'board', 'mines', 'reveals', 'difficulty'}


def discover_files(args):
    if not args:
        args = ['.']
    files = []
    seen = set()
    for a in args:
        matches = []
        if os.path.isdir(a):
            matches = sorted(glob.glob(os.path.join(a, '*.json')))
        elif os.path.isfile(a):
            matches = [a]
        else:
            print(f'warning: {a} not found', file=sys.stderr)
            continue
        for m in matches:
            resolved = os.path.abspath(m)
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(m)
    return files


def _parse_board_string(s, area):
    """Parse a `board` string. Returns (mines_indices, counts)."""
    if not isinstance(s, str) or len(s) != area:
        raise ValueError(f'board string must be length {area}, got {len(s)}')
    mines = []
    counts = [0] * area
    for i, ch in enumerate(s):
        if ch == '!':
            mines.append(i)
        elif '0' <= ch <= '8':
            counts[i] = int(ch)
        else:
            raise ValueError(f'unknown board char {ch!r} at index {i}')
    return mines, counts


def _validate_spec(spec):
    """Validate one board spec dict. Mutates the dict with normalized fields
    and returns it. Raises ValueError on any problem.

    On return, spec always has:
      w, h              : ints
      mines             : list of mine cell indices (parsed from `board`)
      counts            : list of per-cell adjacent-mine counts
      reveals           : list of ints (validated safe)
      difficulty        : whatever was in the JSON, or None
      board             : original board string (preserved)
    """
    if not isinstance(spec, dict):
        raise ValueError('top-level must be an object')
    for key in REQUIRED_KEYS:
        if key not in spec:
            raise ValueError(f'missing required field {key!r}')
    try:
        w = int(spec['w'])
        h = int(spec['h'])
    except (TypeError, ValueError):
        raise ValueError('w/h must be integers') from None
    if w <= 0 or h <= 0:
        raise ValueError(f'invalid dimensions {w}x{h}')
    area = w * h

    mines, counts = _parse_board_string(spec['board'], area)

    # Optional mine-count check.
    declared = spec.get('mines')
    if isinstance(declared, int) and not isinstance(declared, bool):
        if declared != len(mines):
            raise ValueError(
                f'declared mines={declared} != counted {len(mines)}')

    reveals = spec['reveals']
    if not isinstance(reveals, list):
        raise ValueError("'reveals' must be a list")
    validated_reveals = []
    mines_set = set(mines)
    for v in reveals:
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError(f"'reveals' contains non-integer {v!r}")
        if v < 0 or v >= area:
            raise ValueError(f"'reveals' index {v} out of range [0, {area})")
        if v in mines_set:
            raise ValueError(f"'reveals' index {v} is a mine")
        validated_reveals.append(v)

    spec['w'] = w
    spec['h'] = h
    spec['mines'] = mines
    spec['counts'] = counts
    spec['reveals'] = validated_reveals
    spec.setdefault('difficulty', None)
    return spec


def load_specs(path):
    """Load a JSON-Lines board file. Returns a list of validated specs.

    Blank lines are skipped. On error, raises ValueError with a
    `basename:lineno:` prefix so the caller can point at the offender.
    """
    specs = []
    with open(path) as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                spec = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f'{os.path.basename(path)}:{lineno}: '
                    f'invalid JSON: {e}') from None
            try:
                specs.append(_validate_spec(spec))
            except ValueError as e:
                raise ValueError(
                    f'{os.path.basename(path)}:{lineno}: {e}') from None
    return specs


def _format_difficulty(d):
    if d is None:
        return '--'
    if isinstance(d, float):
        return f'{d:.3f}'
    return str(d)


class Game:
    def __init__(self, root, files):
        self.root = root
        self.files = files
        self.current_file = None
        self.specs = []         # loaded from current file
        self.spec = None        # currently selected board
        self.board = None
        self.M = 0
        self.revealed = 0
        self.flagged = 0
        self.cell_buttons = []
        self.game_over = False
        self.won = False

        root.title('Minesweeper')
        root.option_add('*Font', 'TkFixedFont 12')

        bar = ttk.Frame(root, padding=6)
        bar.grid(row=0, column=0, sticky='ew')

        ttk.Label(bar, text='File:').grid(row=0, column=0)
        self.file_var = tk.StringVar()
        self.file_box = ttk.Combobox(
            bar, textvariable=self.file_var,
            values=[os.path.basename(f) for f in files],
            width=24, state='readonly')
        self.file_box.grid(row=0, column=1, padx=(2, 12))
        self.file_box.bind('<<ComboboxSelected>>', self._on_file_change)

        ttk.Label(bar, text='Board:').grid(row=0, column=2)
        self.board_var = tk.StringVar()
        self.board_box = ttk.Combobox(
            bar, textvariable=self.board_var, values=[],
            width=18, state='readonly')
        self.board_box.grid(row=0, column=3, padx=(2, 12))
        self.board_box.bind('<<ComboboxSelected>>', self._on_board_change)

        self.difficulty_label = ttk.Label(bar, text='Difficulty: --')
        self.difficulty_label.grid(row=0, column=4, padx=(0, 12))

        self.mines_label = ttk.Label(bar, text='Mines: --')
        self.mines_label.grid(row=0, column=5, padx=(0, 12))

        self.status_label = ttk.Label(bar, text='')
        self.status_label.grid(row=0, column=6, sticky='w')

        ttk.Button(bar, text='Restart', command=self._restart).grid(
            row=0, column=7, padx=(12, 0))

        self.grid_frame = ttk.Frame(root, padding=6)
        self.grid_frame.grid(row=1, column=0)

        if files:
            self.file_var.set(os.path.basename(files[0]))
            self._on_file_change()

    def _board_labels(self):
        """Return a list of picker labels — one per spec in the current file.

        Format `#N diff=X.XXX` so difficulty is visible in the picker itself.
        """
        return [
            f'#{i + 1} diff={_format_difficulty(sp.get("difficulty"))}'
            for i, sp in enumerate(self.specs)
        ]

    def _on_file_change(self, _evt=None):
        name = self.file_var.get()
        path = next(
            (f for f in self.files if os.path.basename(f) == name), None)
        if not path:
            return
        self.current_file = path
        try:
            self.specs = load_specs(path)
        except ValueError as e:
            self.specs = []
            self.spec = None
            self.board = None
            for w in self.grid_frame.winfo_children():
                w.destroy()
            self.status_label.config(text=str(e))
            self.difficulty_label.config(text='Difficulty: --')
            self.mines_label.config(text='Mines: --')
            self.board_box['values'] = []
            self.board_var.set('')
            return
        labels = self._board_labels()
        self.board_box['values'] = labels
        if labels:
            self.board_var.set(labels[0])
            self._on_board_change()
        else:
            self.status_label.config(text='no boards in file')

    def _on_board_change(self, _evt=None):
        label = self.board_var.get()
        try:
            idx = self._board_labels().index(label)
        except ValueError:
            return
        self.spec = self.specs[idx]
        self._load_board()

    def _load_board(self):
        sp = self.spec
        # Build Board directly from spec-derived data. The spec's `board`
        # string is the source of truth for counts; no need to recompute
        # them from mine indices.
        mines_bitmask = 0
        for m in sp['mines']:
            mines_bitmask |= 1 << m
        self.board = Board(w=sp['w'], h=sp['h'],
                           mines=mines_bitmask, counts=sp['counts'])
        self.M = len(sp['mines'])
        self.revealed = 0
        self.flagged = 0
        self.game_over = False
        self.won = False
        for r in sp['reveals']:
            self.revealed = _reveal_cell(
                self.board, r, self.revealed, self.flagged)

        self.difficulty_label.config(
            text=f'Difficulty: {_format_difficulty(sp.get("difficulty"))}')

        # Any extra metadata beyond the standard keys goes into the status
        # area so it isn't lost. Skip internal helpers.
        skip = DISPLAY_KEYS | {'counts'}
        bits = [f'{k}={v}' for k, v in sp.items() if k not in skip]
        self.status_label.config(text='  '.join(bits))

        self._rebuild_grid()
        self._refresh()

    def _restart(self):
        if self.spec is not None:
            self._load_board()

    def _rebuild_grid(self):
        for w in self.grid_frame.winfo_children():
            w.destroy()
        self.cell_buttons = []
        for r in range(self.board.h):
            row = []
            for c in range(self.board.w):
                i = r * self.board.w + c
                btn = tk.Label(
                    self.grid_frame, text='', width=2, height=1,
                    relief='raised', borderwidth=2,
                    bg='#bdbdbd', fg='black')
                btn.grid(row=r, column=c, padx=0, pady=0)
                btn.bind('<Button-1>', lambda e, idx=i: self._reveal(idx))
                btn.bind('<Button-3>', lambda e, idx=i: self._toggle_flag(idx))
                row.append(btn)
            self.cell_buttons.append(row)

    def _reveal(self, i):
        if self.game_over:
            return
        if (self.revealed >> i) & 1 or (self.flagged >> i) & 1:
            return
        if (self.board.mines >> i) & 1:
            self.revealed |= 1 << i
            self.game_over = True
            self._append_status('BOOM. You lose.')
            self._refresh(show_mines=True, hit=i)
            return
        self.revealed = _reveal_cell(
            self.board, i, self.revealed, self.flagged)
        self._refresh()
        if self._check_win():
            self.won = True
            self.game_over = True
            self._append_status('You win!')

    def _append_status(self, msg):
        cur = self.status_label.cget('text')
        self.status_label.config(text=(msg if not cur else f'{msg}  {cur}'))

    def _toggle_flag(self, i):
        if self.game_over:
            return
        if (self.revealed >> i) & 1:
            return
        self.flagged ^= 1 << i
        self._refresh()

    def _check_win(self):
        area = self.board.area
        full = (1 << area) - 1
        safe_mask = full & ~self.board.mines
        return (self.revealed & safe_mask) == safe_mask

    def _refresh(self, show_mines=False, hit=None):
        b = self.board
        for r in range(b.h):
            for c in range(b.w):
                i = r * b.w + c
                btn = self.cell_buttons[r][c]
                is_mine = (b.mines >> i) & 1
                is_revealed = (self.revealed >> i) & 1
                is_flagged = (self.flagged >> i) & 1
                if is_flagged:
                    btn.config(text='⚑', fg='#c62828', bg='#bdbdbd',
                               relief='raised')
                elif is_revealed:
                    if is_mine:
                        bg = '#ff5252' if i == hit else '#ffcdd2'
                        btn.config(text='✸', fg='black', bg=bg,
                                   relief='sunken')
                    else:
                        n = b.counts[i]
                        text = '' if n == 0 else str(n)
                        color = DIGIT_COLORS.get(n, 'black')
                        btn.config(text=text, fg=color, bg='#e0e0e0',
                                   relief='sunken')
                elif show_mines and is_mine:
                    btn.config(text='✸', fg='black', bg='#eeeeee',
                               relief='raised')
                else:
                    btn.config(text='', fg='black', bg='#bdbdbd',
                               relief='raised')
        remaining = self.M - bin(self.flagged).count('1')
        self.mines_label.config(text=f'Mines: {remaining}')


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('paths', nargs='*',
                   help='.json files or directories to search')
    args = p.parse_args()
    files = discover_files(args.paths)
    if not files:
        print('no .json board files found', file=sys.stderr)
        sys.exit(1)
    root = tk.Tk()
    Game(root, files)
    root.mainloop()


if __name__ == '__main__':
    main()
