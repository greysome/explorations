"""Hand-built positions exercising the solver."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from board import Board
from solver import solve, SOLVED, STUCK


def revealed_bits(*idx):
    r = 0
    for i in idx:
        r |= 1 << i
    return r


def test_trivial_single_mine():
    # 3x3, mine at center. Reveal corner cell 0; trivial alone can't deduce.
    # But with M=1 set, interior cells {2,5,6,7} are all safe (every valid
    # frontier assignment has 1 mine in {1,3,4}, so interior has 0).
    b = Board.from_mine_indices(3, 3, [4])
    revealed, flagged, status, log = solve(b, revealed_bits(0), 0, M=1)
    assert status == SOLVED, status
    assert (flagged >> 4) & 1


def test_stuck_corners():
    # Center cell shows 2; mines could be any 2 of 8 neighbors -> STUCK.
    b = Board.from_mine_indices(3, 3, [0, 8])
    revealed, flagged, status, log = solve(b, revealed_bits(4), 0, M=2)
    assert status == STUCK, status


def test_1_2_1_pattern():
    # 5x3 with mines at idx 6 and 8; reveal top and bottom rows.
    b = Board.from_mine_indices(5, 3, [6, 8])
    rev = 0
    for i in list(range(5)) + list(range(10, 15)):
        rev |= 1 << i
    revealed, flagged, status, log = solve(b, rev, 0, M=2)
    assert status == SOLVED
    assert flagged == (1 << 6) | (1 << 8)


def test_global_count_forces_interior():
    # 4x4: place a single mine far in a corner; reveal a distant cell that's
    # not adjacent. With M=1 and seeing a clue elsewhere, the global mine
    # count should force the unrelated interior to be safe.
    b = Board.from_mine_indices(4, 4, [0])
    # Reveal cell 5 (1,1) which has count 1 (adjacent to mine 0).
    revealed, flagged, status, log = solve(b, revealed_bits(5), 0, M=1)
    assert status == SOLVED, status
    # The single mine must be flagged at 0.
    assert flagged == 1


if __name__ == '__main__':
    test_trivial_single_mine()
    test_stuck_corners()
    test_1_2_1_pattern()
    test_global_count_forces_interior()
    print('All solver tests passed.')
