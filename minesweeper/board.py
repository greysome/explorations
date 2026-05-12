"""Minesweeper board representation.

Bitsets are Python ints with bit `r*w + c` representing cell (r, c).
"""

from dataclasses import dataclass
from functools import lru_cache


@lru_cache(maxsize=None)
def neighbors8(w, h):
    """Return per-cell 8-neighbor index lists (no self)."""
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
    mines: int          # bitset of mine cells
    counts: list        # per-cell adjacent-mine count

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

    @property
    def mine_count(self):
        return self.mines.bit_count()


def iter_bits(bitset):
    """Yield set bit indices, lowest-first."""
    while bitset:
        b = bitset & -bitset
        yield b.bit_length() - 1
        bitset ^= b


def render(board, revealed, flagged, show_mines=False):
    """Return a string rendering of the board state."""
    lines = []
    # Column header: a b c ... (3-space gutter matches the 2-char row label
    # plus the join space).
    header = '   ' + ' '.join(chr(ord('a') + c) for c in range(board.w))
    lines.append(header)
    for r in range(board.h):
        row = [f'{r + 1:>2}']
        for c in range(board.w):
            i = r * board.w + c
            is_mine = (board.mines >> i) & 1
            if (flagged >> i) & 1:
                ch = 'F'
            elif (revealed >> i) & 1:
                if is_mine:
                    ch = '*'
                else:
                    n = board.counts[i]
                    ch = ' ' if n == 0 else str(n)
            elif show_mines and is_mine:
                ch = 'x'
            else:
                ch = '·'
            row.append(ch)
        lines.append(' '.join(row))
    return '\n'.join(lines)
