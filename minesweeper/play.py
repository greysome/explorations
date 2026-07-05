"""Tkinter Minesweeper UI that loads JSON board specs.

  python play.py [path ...]

Positional args:
  - a `.json` file: add it to the picker.
  - a directory: add every `*.json` in it.
  - no args: scan the current directory.

Each JSON file describes exactly one board:

    {
      "w": 5,
      "h": 5,
      "mines":   [1, 4, 7, ...],    // cell indices (row-major)
      "reveals": [0, 8, ...],       // initially-revealed safe cells
      "difficulty": "hard",         // shown in the toolbar; string or number
      "seed": 12345,                // optional metadata (any keys allowed)
      ...
    }

Any keys other than the ones above are shown as a `key=value` string in the
status area.

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
from tkinter import ttk

from board import Board
from solver import _reveal_cell


DIGIT_COLORS = {
    1: '#1976d2', 2: '#388e3c', 3: '#d32f2f', 4: '#7b1fa2',
    5: '#f57c00', 6: '#0097a7', 7: '#212121', 8: '#616161',
}

REQUIRED_KEYS = ('w', 'h', 'mines', 'reveals')
DISPLAY_KEYS = {'w', 'h', 'mines', 'reveals', 'difficulty'}


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


def load_spec(path):
    """Load a JSON board spec. Returns a dict with validated required fields.

    Raises ValueError with a path-prefixed message on any problem.
    """
    with open(path) as f:
        try:
            spec = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f'{os.path.basename(path)}: invalid JSON: {e}') from None
    if not isinstance(spec, dict):
        raise ValueError(f'{os.path.basename(path)}: top-level must be an object')
    for key in REQUIRED_KEYS:
        if key not in spec:
            raise ValueError(
                f'{os.path.basename(path)}: missing required field {key!r}')
    try:
        w = int(spec['w'])
        h = int(spec['h'])
    except (TypeError, ValueError):
        raise ValueError(
            f'{os.path.basename(path)}: w/h must be integers') from None
    if w <= 0 or h <= 0:
        raise ValueError(
            f'{os.path.basename(path)}: invalid dimensions {w}x{h}')
    area = w * h

    def _validate_indices(field):
        vals = spec[field]
        if not isinstance(vals, list):
            raise ValueError(
                f'{os.path.basename(path)}: {field!r} must be a list')
        out = []
        for v in vals:
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError(
                    f'{os.path.basename(path)}: {field!r} contains '
                    f'non-integer {v!r}')
            if v < 0 or v >= area:
                raise ValueError(
                    f'{os.path.basename(path)}: {field!r} index {v} out '
                    f'of range [0, {area})')
            out.append(v)
        return out

    mines = _validate_indices('mines')
    reveals = _validate_indices('reveals')
    overlap = set(mines) & set(reveals)
    if overlap:
        raise ValueError(
            f'{os.path.basename(path)}: cells listed as both mine and '
            f'reveal: {sorted(overlap)}')
    spec['w'] = w
    spec['h'] = h
    spec['mines'] = mines
    spec['reveals'] = reveals
    return spec


class Game:
    def __init__(self, root, files):
        self.root = root
        self.files = files
        self.current_file = None
        self.spec = None
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
            width=28, state='readonly')
        self.file_box.grid(row=0, column=1, padx=(2, 12))
        self.file_box.bind('<<ComboboxSelected>>', self._on_file_change)

        self.difficulty_label = ttk.Label(bar, text='Difficulty: --')
        self.difficulty_label.grid(row=0, column=2, padx=(0, 12))

        self.mines_label = ttk.Label(bar, text='Mines: --')
        self.mines_label.grid(row=0, column=3, padx=(0, 12))

        self.status_label = ttk.Label(bar, text='')
        self.status_label.grid(row=0, column=4, sticky='w')

        ttk.Button(bar, text='Restart', command=self._restart).grid(
            row=0, column=5, padx=(12, 0))

        self.grid_frame = ttk.Frame(root, padding=6)
        self.grid_frame.grid(row=1, column=0)

        if files:
            self.file_var.set(os.path.basename(files[0]))
            self._on_file_change()

    def _on_file_change(self, _evt=None):
        name = self.file_var.get()
        path = next(
            (f for f in self.files if os.path.basename(f) == name), None)
        if not path:
            return
        self.current_file = path
        try:
            self.spec = load_spec(path)
        except ValueError as e:
            self.spec = None
            self.board = None
            for w in self.grid_frame.winfo_children():
                w.destroy()
            self.status_label.config(text=str(e))
            self.difficulty_label.config(text='Difficulty: --')
            self.mines_label.config(text='Mines: --')
            return
        self._load_board()

    def _load_board(self):
        sp = self.spec
        self.board = Board.from_mine_indices(sp['w'], sp['h'], sp['mines'])
        self.M = len(sp['mines'])
        self.revealed = 0
        self.flagged = 0
        self.game_over = False
        self.won = False
        for r in sp['reveals']:
            self.revealed = _reveal_cell(
                self.board, r, self.revealed, self.flagged)

        diff = sp.get('difficulty', '--')
        self.difficulty_label.config(text=f'Difficulty: {diff}')

        # Any extra metadata beyond the required + difficulty keys goes into
        # the status area so it doesn't get lost.
        bits = [f'{k}={v}' for k, v in sp.items() if k not in DISPLAY_KEYS]
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
