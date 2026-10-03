"""Minimal reduced ordered BDD package (stdlib only).

Used to represent sets of profiles (boolean functions over the tour
attributes) exactly and canonically, so fixpoint iteration over profile
sets is decidable by pointer equality.
"""

from __future__ import annotations


class BDD:
    """A reduced ordered binary decision diagram over named variables."""

    def __init__(self, var_order: list[str]) -> None:
        # Node ids 0 and 1 are the False / True terminals.
        # Non-terminal nodes are tuples (var_index, low_id, high_id).
        self._order = list(var_order)
        self._index_of = {name: i for i, name in enumerate(self._order)}
        self._nodes: list[tuple[int, int, int]] = []
        self._unique: dict[tuple[int, int, int], int] = {}
        self._apply_cache: dict[tuple[str, int, int], int] = {}
        self._not_cache: dict[int, int] = {}

    def _mk(self, var_index: int, low: int, high: int) -> int:
        if low == high:
            return low
        key = (var_index, low, high)
        node = self._unique.get(key)
        if node is None:
            node = len(self._nodes) + 2
            self._nodes.append(key)
            self._unique[key] = node
        return node

    def _parts(self, node: int) -> tuple[int, int, int]:
        return self._nodes[node - 2]

    def constant(self, value: bool) -> int:
        return 1 if value else 0

    def literal(self, var: str, value: bool) -> int:
        index = self._index_of[var]
        return self._mk(index, 1, 0) if not value else self._mk(index, 0, 1)

    def _apply(self, op: str, left: int, right: int) -> int:
        if left <= 1 and right <= 1:
            if op == "and":
                return 1 if (left == 1 and right == 1) else 0
            return 1 if (left == 1 or right == 1) else 0
        if op == "and":
            if left == 0 or right == 0:
                return 0
            if left == 1:
                return right
            if right == 1:
                return left
        else:
            if left == 1 or right == 1:
                return 1
            if left == 0:
                return right
            if right == 0:
                return left
        if left == right:
            return left
        key = (op, left, right) if left < right else (op, right, left)
        cached = self._apply_cache.get(key)
        if cached is not None:
            return cached
        lvar, llow, lhigh = self._parts(left)
        rvar, rlow, rhigh = self._parts(right)
        if lvar < rvar:
            var, a_low, a_high, b_low, b_high = lvar, llow, lhigh, right, right
        elif rvar < lvar:
            var, a_low, a_high, b_low, b_high = rvar, left, left, rlow, rhigh
        else:
            var, a_low, a_high, b_low, b_high = lvar, llow, lhigh, rlow, rhigh
        low = self._apply(op, a_low, b_low)
        high = self._apply(op, a_high, b_high)
        result = self._mk(var, low, high)
        self._apply_cache[key] = result
        return result

    def negate(self, node: int) -> int:
        if node <= 1:
            return 1 - node
        cached = self._not_cache.get(node)
        if cached is not None:
            return cached
        var, low, high = self._parts(node)
        result = self._mk(var, self.negate(low), self.negate(high))
        self._not_cache[node] = result
        return result

    def conjunction(self, nodes: list[int]) -> int:
        result = 1
        for node in nodes:
            result = self._apply("and", result, node)
        return result

    def disjunction(self, nodes: list[int]) -> int:
        result = 0
        for node in nodes:
            result = self._apply("or", result, node)
        return result

    def one_satisfying_assignment(self, node: int) -> dict[str, bool] | None:
        """Return a complete assignment satisfying ``node``, or None."""
        if node == 0:
            return None
        assignment = [False] * len(self._order)
        current = node
        while current > 1:
            var, low, high = self._parts(current)
            if low != 0:
                assignment[var] = False
                current = low
            else:
                assignment[var] = True
                current = high
        return {name: assignment[i] for i, name in enumerate(self._order)}
