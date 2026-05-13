"""Property-style tests for the generator."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from make_boards import generate, _try_solve
from solver import SOLVED, STUCK


def check_solvable(board, reveals):
    _, _, status, _ = _try_solve(board, reveals, board.mine_count)
    assert status == SOLVED, status


def check_minimal(board, reveals):
    M = board.mine_count
    for i in range(len(reveals)):
        trial = reveals[:i] + reveals[i+1:]
        if not trial:
            continue
        _, _, status, _ = _try_solve(board, trial, M)
        assert status != SOLVED, (
            f'removing reveal index {i} ({reveals[i]}) still solves')


def test_generator_5x5():
    result = generate(5, 5, 10, seed=10, max_attempts=80)
    assert result is not None
    board, reveals = result
    check_solvable(board, reveals)
    check_minimal(board, reveals)


def test_generator_8x8():
    result = generate(8, 8, 26, seed=11, max_attempts=80)
    assert result is not None
    board, reveals = result
    check_solvable(board, reveals)
    check_minimal(board, reveals)


if __name__ == '__main__':
    test_generator_5x5()
    print('5x5 ok')
    test_generator_8x8()
    print('8x8 ok')
    print('All generator tests passed.')
