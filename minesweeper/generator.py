"""No-guess Minesweeper board generator.

Combines a dense mine layout (via gen_board.pregenerate_dense_board)
with a greedy forward/backward search for a minimal reveal set such
that the solver can solve the board with no guessing.
"""

import random
from dataclasses import dataclass

from board import Board, iter_bits
from solver import solve, SOLVED, STUCK


@dataclass
class GeneratedBoard:
    board: Board
    reveals: list   # cell indices of the initial reveal set
    score: int
    seed: int


def interest_score(log):
    s = 0
    s += log.enum_rounds
    s += log.max_component_size
    s += log.enum_deductions
    if log.global_count_decisive:
        s += 5
    return s


def _initial_revealed(board, reveals):
    """Return (revealed, flagged) bitsets after applying initial reveals
    (with 0-cascade BFS for any 0-cell reveals)."""
    from solver import _reveal_cell
    revealed = 0
    flagged = 0
    for r in reveals:
        if not (revealed >> r) & 1:
            revealed = _reveal_cell(board, r, revealed, flagged)
    return revealed, flagged


def _try_solve(board, reveals, M):
    revealed, flagged = _initial_revealed(board, reveals)
    return solve(board, revealed, flagged, M)


def build_reveal_set(board, M, rng, max_reveals):
    """Forward pass: pick reveals greedily until the solver wins or budget runs out.

    Returns (reveals, log) or (None, None) on failure.
    """
    area = board.area
    mines = board.mines
    # Candidate safe cells: not mines.
    safe_cells = [i for i in range(area) if not ((mines >> i) & 1)]
    if not safe_cells:
        return None, None

    # Seed: prefer a 0-cell if one exists (cascades expose many clues,
    # shrinking the frontier the solver has to enumerate); otherwise pick a
    # low-count cell.
    zero_safe = [i for i in safe_cells if board.counts[i] == 0]
    if zero_safe:
        seed = rng.choice(zero_safe)
    else:
        seed_pool = sorted(safe_cells, key=lambda i: board.counts[i])
        seed = rng.choice(seed_pool[:max(3, len(seed_pool) // 4)])

    reveals = [seed]
    revealed, flagged, status, log = _try_solve(board, reveals, M)
    if status == SOLVED:
        return reveals, log

    for _ in range(max_reveals - 1):
        if status == SOLVED:
            return reveals, log
        # Candidate: hidden safe cells that solver couldn't deduce.
        hidden_safe = [
            i for i in safe_cells
            if not ((revealed >> i) & 1)
        ]
        if not hidden_safe:
            # All safe cells revealed but status not SOLVED? Shouldn't happen
            # unless some mines unflagged. Anyway, treat as SOLVED.
            return reveals, log

        # Try a sample of candidates; pick the one that maximizes deductions.
        sample = hidden_safe if len(hidden_safe) <= 8 else rng.sample(hidden_safe, 8)
        best = None
        best_gain = -1
        best_log = None
        for cand in sample:
            trial = reveals + [cand]
            tr_rev, tr_fl, tr_status, tr_log = _try_solve(board, trial, M)
            gain = tr_rev.bit_count() + tr_fl.bit_count()
            if tr_status == SOLVED:
                gain += 10000  # prefer solving
            if gain > best_gain:
                best_gain = gain
                best = cand
                best_log = tr_log
                best_rev, best_fl, best_status = tr_rev, tr_fl, tr_status

        # If even the best candidate doesn't change anything beyond just
        # revealing that one cell, we're stuck.
        if best is None:
            return None, None
        reveals.append(best)
        revealed, flagged, status, log = best_rev, best_fl, best_status, best_log

    if status == SOLVED:
        return reveals, log
    return None, None


def minimize(board, M, reveals):
    """Backward pass: drop reveals that are now redundant."""
    result = list(reveals)
    i = len(result) - 1
    while i >= 0:
        trial = result[:i] + result[i+1:]
        if not trial:
            i -= 1
            continue
        _, _, status, _ = _try_solve(board, trial, M)
        if status == SOLVED:
            result = trial
        i -= 1
    return result


def generate(w, h, M, seed=0, max_reveals=5, min_interest=3,
             max_attempts=500, verbose=False, max_uncovered=None):
    """Generate one no-guess board satisfying the parameters.

    max_uncovered controls the dense-board generator: with 0, every cell has
    at least one adjacent mine (no 0-clue cascades). Larger values allow
    some 0-cells, which makes the board easier to solve. Defaults to 0 for
    small boards and a small positive value for larger ones.
    """
    from make_boards import pregenerate_dense_board, default_max_uncovered
    if max_uncovered is None:
        max_uncovered = default_max_uncovered(w, h)
    for attempt in range(max_attempts):
        rng = random.Random(seed * 1_000_003 + attempt)
        mines = pregenerate_dense_board(rng, w, h, M, max_uncovered=max_uncovered)
        board = Board.from_mine_indices(w, h, mines)

        reveals, log = build_reveal_set(board, M, rng, max_reveals)
        if reveals is None:
            if verbose:
                print(f'attempt {attempt}: forward pass failed', flush=True)
            continue

        reveals = minimize(board, M, reveals)
        # Score is taken from the SOLVED log when run from the minimal set.
        _, _, status, log = _try_solve(board, reveals, M)
        if status != SOLVED:
            continue
        score = interest_score(log)
        if verbose:
            print(f'attempt {attempt}: score={score}, reveals={len(reveals)}, log={log}', flush=True)
        if score >= min_interest:
            return GeneratedBoard(
                board=board, reveals=reveals, score=score,
                seed=seed * 1_000_003 + attempt)
    return None
