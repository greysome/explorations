"""Property-style tests for the generator."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from generator import generate, _try_solve
from solver import SOLVED, STUCK


def check_solvable(gb):
    _, _, status, _ = _try_solve(gb.board, gb.reveals, gb.board.mine_count)
    assert status == SOLVED, status


def check_minimal(gb):
    M = gb.board.mine_count
    for i in range(len(gb.reveals)):
        trial = gb.reveals[:i] + gb.reveals[i+1:]
        if not trial:
            continue
        _, _, status, _ = _try_solve(gb.board, trial, M)
        assert status != SOLVED, (
            f'removing reveal index {i} ({gb.reveals[i]}) still solves')


def test_generator_5x5():
    g = generate(5, 5, 10, seed=10, max_reveals=6, min_interest=3, max_attempts=80)
    assert g is not None
    check_solvable(g)
    check_minimal(g)


def test_generator_8x8():
    g = generate(8, 8, 26, seed=11, max_reveals=8, min_interest=3, max_attempts=80)
    assert g is not None
    check_solvable(g)
    check_minimal(g)


if __name__ == '__main__':
    test_generator_5x5()
    print('5x5 ok')
    test_generator_8x8()
    print('8x8 ok')
    print('All generator tests passed.')
