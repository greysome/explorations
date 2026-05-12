"""Minimal tkinter Minesweeper UI.

  python play.py [board_or_dir ...]

Positional args:
  - a `.boards` file: load and pick a board from it.
  - a directory: list all `*.boards` in it.
  - no args: scan the current directory.

Controls:
  - Left click a hidden cell to reveal it.
  - Right click a hidden cell to toggle a flag.

A mine counter (`mines − flags`) shows in the top bar.
"""

import argparse
import glob
import os
import random
import sys
import tkinter as tk
from tkinter import ttk

from board import Board, neighbors8
from boardsfile import load_boards
from solver import _reveal_cell


DIGIT_COLORS = {
    1: '#1976d2', 2: '#388e3c', 3: '#d32f2f', 4: '#7b1fa2',
    5: '#f57c00', 6: '#0097a7', 7: '#212121', 8: '#616161',
}


def discover_files(args):
    if not args:
        args = ['.']
    files = []
    for a in args:
        if os.path.isdir(a):
            files.extend(sorted(glob.glob(os.path.join(a, '*.boards'))))
        elif os.path.isfile(a):
            files.append(a)
        else:
            print(f'warning: {a} not found', file=sys.stderr)
    return files


class Game:
    def __init__(self, root, files):
        self.root = root
        self.files = files
        self.boards = []           # list of StoredBoard for current file
        self._board_by_key = {}
        self.current_file = None
        self.board = None          # Board for current selection
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
            width=22, state='readonly')
        self.file_box.grid(row=0, column=1, padx=(2, 12))
        self.file_box.bind('<<ComboboxSelected>>', self._on_file_change)

        ttk.Label(bar, text='Board:').grid(row=0, column=2)
        self.board_var = tk.StringVar()
        self.board_box = ttk.Combobox(
            bar, textvariable=self.board_var, values=[],
            width=8, state='readonly')
        self.board_box.grid(row=0, column=3, padx=(2, 12))
        self.board_box.bind('<<ComboboxSelected>>', self._on_board_change)

        self.mines_label = ttk.Label(bar, text='Mines: --')
        self.mines_label.grid(row=0, column=4, padx=(0, 12))
        self.status_label = ttk.Label(bar, text='')
        self.status_label.grid(row=0, column=5)

        ttk.Button(bar, text='Restart', command=self._restart).grid(
            row=0, column=6, padx=(12, 0))

        self.grid_frame = ttk.Frame(root, padding=6)
        self.grid_frame.grid(row=1, column=0)

        if files:
            self.file_var.set(os.path.basename(files[0]))
            self._on_file_change()

    def _on_file_change(self, _evt=None):
        name = self.file_var.get()
        path = next((f for f in self.files if os.path.basename(f) == name),
                    None)
        if not path:
            return
        self.current_file = path
        try:
            self.boards = load_boards(path)
        except Exception as e:
            self.boards = []
            self.status_label.config(text=f'load error: {e}')
            return
        keys = [str(sb.meta.get('seed', i)) for i, sb in enumerate(self.boards)]
        self._board_by_key = dict(zip(keys, self.boards))
        self.board_box['values'] = keys
        if self.boards:
            self.board_var.set(keys[0])
            self._on_board_change()
        else:
            self.status_label.config(text='no boards in file')

    def _on_board_change(self, _evt=None):
        key = self.board_var.get()
        if not key:
            return
        sb = self._board_by_key.get(key)
        if sb is None:
            return
        self.board = Board.from_mine_indices(sb.w, sb.h, sb.mines)
        self.M = len(sb.mines)
        self.revealed = 0
        self.flagged = 0
        self.game_over = False
        self.won = False
        for r in sb.reveals:
            self.revealed = _reveal_cell(
                self.board, r, self.revealed, self.flagged)
        meta = sb.meta or {}
        bits = []
        for k in ('score', 'reveals', 'seed'):
            if k in meta:
                bits.append(f'{k}={meta[k]}')
        self.status_label.config(text='  '.join(bits))
        self._rebuild_grid()
        self._refresh()

    def _restart(self):
        if self.board_var.get():
            self._on_board_change()

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
            # Mark hit, reveal it as a mine; show all mines for post-mortem.
            self.revealed |= 1 << i
            self.game_over = True
            self.status_label.config(text='BOOM. You lose.')
            self._refresh(show_mines=True, hit=i)
            return
        self.revealed = _reveal_cell(
            self.board, i, self.revealed, self.flagged)
        self._refresh()
        if self._check_win():
            self.won = True
            self.game_over = True
            self.status_label.config(text='You win!')

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
        # Update counter.
        remaining = self.M - bin(self.flagged).count('1')
        self.mines_label.config(text=f'Mines: {remaining}')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('paths', nargs='*',
                   help='.boards files or directories to search')
    args = p.parse_args()
    files = discover_files(args.paths)
    if not files:
        print('no .boards files found', file=sys.stderr)
        sys.exit(1)
    root = tk.Tk()
    Game(root, files)
    root.mainloop()


if __name__ == '__main__':
    main()
