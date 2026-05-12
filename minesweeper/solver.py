"""Minesweeper solver: constraint propagation + DFS frontier enumeration.

The solver mutates `revealed` and `flagged` bitsets given a ground-truth
`Board` and a known total mine count `M`. It does not "guess" -- if it
cannot prove a cell safe or mined, it stops with status STUCK.

The solver is permitted to look at the ground truth `Board.mines` when
revealing safe cells (so that revealing a new safe cell exposes the
correct clue). It does not, however, peek at any mine cell that it has
not first proved to be a mine: STUCK is reported instead of guessing.
"""

from collections import deque
from math import comb

from board import iter_bits, neighbors8


SOLVED = 'SOLVED'
STUCK = 'STUCK'
CONTRADICTION = 'CONTRADICTION'


LEAF_CAP = 50_000   # per-component leaf count cap
NODE_CAP = 400_000  # per-component DFS node-visit cap


class Log:
    """Records which deduction rules fired, for scoring."""

    def __init__(self):
        self.trivial_rounds = 0
        self.trivial_deductions = 0
        self.enum_rounds = 0
        self.enum_deductions = 0
        self.max_component_size = 0
        self.global_count_decisive = False

    def __repr__(self):
        return (
            f'Log(trivial_rounds={self.trivial_rounds}, '
            f'trivial_deductions={self.trivial_deductions}, '
            f'enum_rounds={self.enum_rounds}, '
            f'enum_deductions={self.enum_deductions}, '
            f'max_component_size={self.max_component_size}, '
            f'global_count_decisive={self.global_count_decisive})'
        )


def _bfs_reveal_zero(board, start, revealed, flagged):
    """Cascade reveal from a 0-cell. Returns new revealed bitset.

    Assumes start is safe (not a mine).
    """
    ns = neighbors8(board.w, board.h)
    q = deque([start])
    while q:
        i = q.popleft()
        bit = 1 << i
        if revealed & bit:
            continue
        revealed |= bit
        # Cannot reveal a flagged cell -- but if it was flagged it was
        # presumably proved a mine, and a 0-cascade wouldn't reach it.
        if board.counts[i] == 0:
            for j in ns[i]:
                jb = 1 << j
                if not (revealed & jb) and not (flagged & jb):
                    q.append(j)
    return revealed


def _reveal_cell(board, i, revealed, flagged):
    """Reveal cell i. If it's a 0-cell, cascade. Returns new revealed."""
    if (board.mines >> i) & 1:
        # Should never happen if solver only reveals proven-safe cells.
        raise RuntimeError(f'tried to reveal mine at {i}')
    if board.counts[i] == 0:
        return _bfs_reveal_zero(board, i, revealed, flagged)
    return revealed | (1 << i)


def _trivial_pass(board, revealed, flagged, log):
    """Run trivial propagation to a fixpoint. Returns (revealed, flagged)."""
    ns = neighbors8(board.w, board.h)
    changed_any_round = False
    while True:
        changed = False
        log.trivial_rounds += 1
        # Iterate over revealed numbered cells.
        for i in iter_bits(revealed):
            n = board.counts[i]
            if n == 0:
                continue
            hidden_bits = 0
            flagged_count = 0
            for j in ns[i]:
                jb = 1 << j
                if flagged & jb:
                    flagged_count += 1
                elif not (revealed & jb):
                    hidden_bits |= jb
            if hidden_bits == 0:
                continue
            need = n - flagged_count
            num_hidden = hidden_bits.bit_count()
            if need == 0:
                # All hidden neighbors are safe.
                for j in iter_bits(hidden_bits):
                    if not (revealed & (1 << j)):
                        revealed = _reveal_cell(board, j, revealed, flagged)
                        log.trivial_deductions += 1
                        changed = True
            elif need == num_hidden:
                # All hidden neighbors are mines.
                flagged |= hidden_bits
                log.trivial_deductions += hidden_bits.bit_count()
                changed = True
            elif need < 0 or need > num_hidden:
                return revealed, flagged, True  # contradiction flag
        if not changed:
            break
        changed_any_round = True
    if not changed_any_round:
        # We did one no-op round; don't count it.
        log.trivial_rounds -= 1
    return revealed, flagged, False


def _build_frontier(board, revealed, flagged):
    """Return (frontier_set, constraints).

    constraints: list of (need:int, frontier_neighbors:frozenset[int])
    derived from revealed numbered cells touching hidden non-flagged cells.
    """
    ns = neighbors8(board.w, board.h)
    frontier = set()
    constraints = []
    for i in iter_bits(revealed):
        if board.counts[i] == 0:
            continue
        hidden_neighbors = []
        flagged_count = 0
        for j in ns[i]:
            jb = 1 << j
            if flagged & jb:
                flagged_count += 1
            elif not (revealed & jb):
                hidden_neighbors.append(j)
        if hidden_neighbors:
            need = board.counts[i] - flagged_count
            constraints.append((need, frozenset(hidden_neighbors)))
            frontier.update(hidden_neighbors)
    return frontier, constraints


def _split_components(frontier, constraints):
    """Split (frontier, constraints) into connected components.

    Two frontier cells are connected if they share a constraint.
    Returns list of (cells:list[int], cons:list[(need, frozenset)]).
    """
    parent = {c: c for c in frontier}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for need, cells in constraints:
        cells_list = list(cells)
        for k in range(1, len(cells_list)):
            union(cells_list[0], cells_list[k])

    groups = {}
    for c in frontier:
        r = find(c)
        groups.setdefault(r, set()).add(c)

    # Assign each constraint to the component containing its cells.
    comp_cons = {r: [] for r in groups}
    for need, cells in constraints:
        any_cell = next(iter(cells))
        r = find(any_cell)
        comp_cons[r].append((need, cells))

    return [(sorted(groups[r]), comp_cons[r]) for r in groups]


def _enumerate_component(cells, constraints):
    """DFS enumeration of mine/safe assignments satisfying constraints.

    Returns:
      per_total_cell_counts: dict[total_mines -> [count per cell of leaves
        with that cell = mine]]
      per_total_leaves: dict[total_mines -> num leaves]
    or (None, None) if the leaf cap was exceeded.
    """
    k = len(cells)
    idx = {c: i for i, c in enumerate(cells)}

    # Per-constraint state: [remaining_need, set(unassigned_cell_positions)].
    cons = []
    for need, cs in constraints:
        cons.append([need, set(idx[c] for c in cs)])

    cons_of_cell = [[] for _ in range(k)]
    for ci, (_, cs) in enumerate(constraints):
        for c in cs:
            cons_of_cell[idx[c]].append(ci)

    # Order cells by constraint membership count (most-constrained first).
    order = sorted(range(k), key=lambda i: -len(cons_of_cell[i]))

    assignment = [None] * k
    per_total_cell_counts = {}
    per_total_leaves = {}
    leaves = [0]
    nodes = [0]
    capped = [False]

    def assign(cell, value):
        assignment[cell] = value
        undo = []
        for ci in cons_of_cell[cell]:
            entry = cons[ci]
            if cell in entry[1]:
                entry[1].discard(cell)
                undo.append(ci)
                if value:
                    entry[0] -= 1
        return undo

    def unassign(cell, value, undo):
        for ci in undo:
            entry = cons[ci]
            entry[1].add(cell)
            if value:
                entry[0] += 1
        assignment[cell] = None

    def consistent():
        for need, un in cons:
            if need < 0 or need > len(un):
                return False
            if not un and need != 0:
                return False
        return True

    def record_leaf():
        leaves[0] += 1
        if leaves[0] > LEAF_CAP:
            capped[0] = True
            return
        total = sum(assignment)
        arr = per_total_cell_counts.get(total)
        if arr is None:
            arr = [0] * k
            per_total_cell_counts[total] = arr
            per_total_leaves[total] = 0
        per_total_leaves[total] += 1
        for i in range(k):
            if assignment[i]:
                arr[i] += 1

    def dfs():
        if capped[0]:
            return
        nodes[0] += 1
        if nodes[0] > NODE_CAP:
            capped[0] = True
            return
        # Find a forced assignment from any constraint.
        forced_cell = None
        forced_val = None
        for need, un in cons:
            if not un:
                continue
            if need == 0:
                forced_cell = next(iter(un))
                forced_val = 0
                break
            if need == len(un):
                forced_cell = next(iter(un))
                forced_val = 1
                break

        if forced_cell is not None:
            undo = assign(forced_cell, forced_val)
            if consistent():
                dfs()
            unassign(forced_cell, forced_val, undo)
            return

        # No forced assignment. Find next unassigned cell by `order`.
        branch_cell = None
        for c in order:
            if assignment[c] is None:
                branch_cell = c
                break
        if branch_cell is None:
            record_leaf()
            return

        for value in (1, 0):
            undo = assign(branch_cell, value)
            if consistent():
                dfs()
                if capped[0]:
                    unassign(branch_cell, value, undo)
                    return
            unassign(branch_cell, value, undo)

    dfs()
    if capped[0]:
        return None, None
    return per_total_cell_counts, per_total_leaves


def _convolve(distributions):
    """Convolve per-component leaf-count distributions into a global dict.

    distributions: list of dict[mine_total -> leaf_count].
    Returns dict[combined_total -> product_of_leaf_counts_per_combination].

    Also returns, for each component, the per-total per-cell mine counts
    so callers can compute weighted per-cell probabilities.
    """
    # Just convolve totals; cell-level aggregation handled by caller.
    result = {0: 1}
    for d in distributions:
        new = {}
        for t1, w1 in result.items():
            for t2, w2 in d.items():
                new[t1 + t2] = new.get(t1 + t2, 0) + w1 * w2
        result = new
    return result


def _frontier_pass(board, revealed, flagged, M, log):
    """Run one frontier-enumeration round. Returns (revealed, flagged, changed, status_flag).

    status_flag: None on success, 'STUCK' if a component was too large.
    """
    frontier, constraints = _build_frontier(board, revealed, flagged)
    if not frontier or not constraints:
        return revealed, flagged, False, None

    components = _split_components(frontier, constraints)

    # Enumerate each component.
    per_comp_results = []  # list of (cells, per_total_cell_counts, per_total_leaves)
    for cells, cons in components:
        if len(cells) > log.max_component_size:
            log.max_component_size = len(cells)
        per_total_cell_counts, per_total_leaves = _enumerate_component(cells, cons)
        if per_total_cell_counts is None:
            return revealed, flagged, False, STUCK
        if not per_total_leaves:
            # No valid assignments at all -- contradiction.
            return revealed, flagged, False, CONTRADICTION
        per_comp_results.append((cells, per_total_cell_counts, per_total_leaves))

    # Compute interior count and remaining mines.
    occupied = revealed | flagged
    area = board.area
    hidden_all = ((1 << area) - 1) & ~occupied
    frontier_bits = 0
    for c in frontier:
        frontier_bits |= 1 << c
    interior_bits = hidden_all & ~frontier_bits
    I = interior_bits.bit_count()
    R = M - flagged.bit_count()

    # Compute the global normalizer and per-(component, cell) weighted mine
    # counts using the global mine count constraint.
    # For each combination of per-component mine totals (t_1, ..., t_n)
    # the weight is (prod leaves) * C(I, R - sum t).
    # We aggregate per-cell mine counts in each component, weighted by
    # the other components' weights and the interior binomial.

    # Build per-component totals lists for convolution; pre-compute
    # convolutions excluding each component j (used to weight component j's
    # cells).
    comp_totals = [list(per_total_leaves.keys()) for _, _, per_total_leaves in per_comp_results]
    comp_leaves = [per_total_leaves for _, _, per_total_leaves in per_comp_results]

    # Full convolution.
    full = {0: 1}
    for d in comp_leaves:
        nxt = {}
        for t, w in full.items():
            for t2, w2 in d.items():
                nxt[t + t2] = nxt.get(t + t2, 0) + w * w2
        full = nxt

    # Normalizer: sum over all combinations of full[t] * C(I, R - t).
    Z = 0
    interior_weight_by_combined = {}  # t -> w_total
    for t, w in full.items():
        rem = R - t
        if 0 <= rem <= I:
            cb = comb(I, rem)
            Z += w * cb
            interior_weight_by_combined[t] = cb
    if Z == 0:
        return revealed, flagged, False, CONTRADICTION

    # Interior cells: certainly safe if rem==0 in every nonzero combination;
    # certainly mines if rem==I in every nonzero combination.
    interior_all_safe = True
    interior_all_mine = True
    any_nonzero = False
    for t, w in full.items():
        rem = R - t
        if not (0 <= rem <= I):
            continue
        if w == 0:
            continue
        any_nonzero = True
        if rem != 0:
            interior_all_safe = False
        if rem != I:
            interior_all_mine = False
    if not any_nonzero:
        return revealed, flagged, False, CONTRADICTION

    changed = False

    if I > 0:
        if interior_all_safe:
            log.global_count_decisive = True
            # Reveal all interior cells.
            for c in iter_bits(interior_bits):
                if not (revealed & (1 << c)):
                    revealed = _reveal_cell(board, c, revealed, flagged)
                    log.enum_deductions += 1
                    changed = True
        elif interior_all_mine:
            log.global_count_decisive = True
            for c in iter_bits(interior_bits):
                if not (flagged & (1 << c)):
                    flagged |= 1 << c
                    log.enum_deductions += 1
                    changed = True

    # For each component cell, compute mine probability times Z (integer).
    # If equals Z -> certainly mine. If equals 0 -> certainly safe.
    n_comp = len(per_comp_results)
    # Precompute "all-others" convolutions for each component (could be slow
    # for many components; n is small for ≤11x11).
    for j, (cells, per_total_cell_counts, per_total_leaves) in enumerate(per_comp_results):
        # Convolve all other components.
        others = {0: 1}
        for k, d in enumerate(comp_leaves):
            if k == j:
                continue
            nxt = {}
            for t, w in others.items():
                for t2, w2 in d.items():
                    nxt[t + t2] = nxt.get(t + t2, 0) + w * w2
            others = nxt
        # For each cell in component j, mine_weight = sum over t_j and t_other
        #   per_total_cell_counts[t_j][cell_pos]
        #   * others[t_other]
        #   * C(I, R - t_j - t_other)
        # If equal to Z -> mine. If 0 -> safe.
        for cell_pos, cell_idx in enumerate(cells):
            mine_w = 0
            for t_j, counts_arr in per_total_cell_counts.items():
                cnt = counts_arr[cell_pos]
                if cnt == 0:
                    continue
                for t_other, w_other in others.items():
                    rem = R - t_j - t_other
                    if 0 <= rem <= I:
                        mine_w += cnt * w_other * comb(I, rem)
            bit = 1 << cell_idx
            if mine_w == 0:
                # Certainly safe.
                if not (revealed & bit):
                    revealed = _reveal_cell(board, cell_idx, revealed, flagged)
                    log.enum_deductions += 1
                    changed = True
            elif mine_w == Z:
                # Certainly mine. Note: leaf-weighted "always-mine" check.
                # mine_w == Z iff every weighted-nonzero combination has this
                # cell as a mine. We approximate: this is true iff the
                # per-total-cell-counts[t][cell_pos] == per_total_leaves[t]
                # for every t with weighted-nonzero contribution. mine_w==Z
                # implies same thing only if all weights positive, which they
                # are. So this is correct.
                if not (flagged & bit):
                    flagged |= bit
                    log.enum_deductions += 1
                    changed = True

    if changed:
        log.enum_rounds += 1

    return revealed, flagged, changed, None


def solve(board, revealed, flagged, M):
    """Run the solver to a fixpoint.

    Returns (revealed, flagged, status, log).
    """
    log = Log()
    revealed, flagged, contradiction = _trivial_pass(board, revealed, flagged, log)
    if contradiction:
        return revealed, flagged, CONTRADICTION, log

    occupied_full = (1 << board.area) - 1
    safe_mask = occupied_full & ~board.mines
    while True:
        # Win condition matches the game: all safe cells revealed.
        # The solver doesn't need to flag every mine — an unprovable mine
        # is fine as long as the player never has to click on it.
        if (revealed & safe_mask) == safe_mask:
            return revealed, flagged, SOLVED, log

        revealed, flagged, changed, status = _frontier_pass(
            board, revealed, flagged, M, log)
        if status == STUCK:
            return revealed, flagged, STUCK, log
        if status == CONTRADICTION:
            return revealed, flagged, CONTRADICTION, log
        if not changed:
            return revealed, flagged, STUCK, log

        # Re-run trivial after enumeration deductions.
        revealed, flagged, contradiction = _trivial_pass(
            board, revealed, flagged, log)
        if contradiction:
            return revealed, flagged, CONTRADICTION, log
