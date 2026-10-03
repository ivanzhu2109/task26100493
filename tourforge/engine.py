"""Navigation analysis engine: replay() and analyze().

analyze() works symbolically: sets of profiles are represented as reduced
ordered binary decision diagrams (BDDs) over the tour's attributes, and the
set of (step, profile) states that can reach an end step is computed as a
least fixpoint. Profiles outside that set are stuck or loop forever; one
such profile is extracted and concretely replayed to build the failure
report, so every counterexample is reproducible by replay() by construction.
"""

from __future__ import annotations

from .model import Condition, Failure, Profile, ReplayResult, Tour, Verdict


def replay(tour: Tour, profile: Profile) -> ReplayResult:
    """Execute one fixed profile until end, stuck, or first step revisit."""
    trajectory = [tour.entry]
    seen = {tour.entry}
    current = tour.entry
    while True:
        step = tour.steps[current]
        if step.is_end:
            return ReplayResult(tuple(trajectory), "end")
        target = None
        for branch in step.branches:
            if all(profile[attr] == value for attr, value in branch.condition):
                target = branch.target
                break
        if target is None:
            return ReplayResult(tuple(trajectory), "stuck")
        trajectory.append(target)
        if target in seen:
            return ReplayResult(tuple(trajectory), "loop")
        seen.add(target)
        current = target


class _Bdd:
    """Minimal reduced ordered BDD over a fixed attribute ordering.

    Node 0 is the False terminal, node 1 the True terminal. Non-terminal
    nodes are (var_index, low, high) triples kept in a unique table, so
    structural equality is node-id equality.
    """

    FALSE = 0
    TRUE = 1

    def __init__(self, variables: tuple[str, ...]):
        self._vars = variables
        self._index = {name: i for i, name in enumerate(variables)}
        self._nodes: list[tuple[int, int, int] | None] = [None, None]
        self._unique: dict[tuple[int, int, int], int] = {}
        self._apply_cache: dict[tuple[str, int, int], int] = {}
        self._neg_cache: dict[int, int] = {}

    def _mk(self, var: int, low: int, high: int) -> int:
        if low == high:
            return low
        key = (var, low, high)
        node = self._unique.get(key)
        if node is None:
            node = len(self._nodes)
            self._nodes.append(key)
            self._unique[key] = node
        return node

    def literal(self, attr: str, value: bool) -> int:
        var = self._index[attr]
        if value:
            return self._mk(var, self.FALSE, self.TRUE)
        return self._mk(var, self.TRUE, self.FALSE)

    def condition(self, condition: Condition) -> int:
        node = self.TRUE
        for attr, value in condition:
            node = self._apply("and", node, self.literal(attr, value))
        return node

    def neg(self, node: int) -> int:
        cached = self._neg_cache.get(node)
        if cached is not None:
            return cached
        if node == self.FALSE:
            result = self.TRUE
        elif node == self.TRUE:
            result = self.FALSE
        else:
            var, low, high = self._nodes[node]
            result = self._mk(var, self.neg(low), self.neg(high))
        self._neg_cache[node] = result
        return result

    def _apply(self, op: str, a: int, b: int) -> int:
        if a > b:
            a, b = b, a
        key = (op, a, b)
        cached = self._apply_cache.get(key)
        if cached is not None:
            return cached
        if op == "and":
            if a == self.FALSE or b == self.FALSE:
                result = self.FALSE
            elif a == self.TRUE:
                result = b
            elif b == self.TRUE:
                result = a
            else:
                result = self._apply_rec(op, a, b)
        else:
            if a == self.TRUE or b == self.TRUE:
                result = self.TRUE
            elif a == self.FALSE:
                result = b
            elif b == self.FALSE:
                result = a
            else:
                result = self._apply_rec(op, a, b)
        self._apply_cache[key] = result
        return result

    def _apply_rec(self, op: str, a: int, b: int) -> int:
        var_a, low_a, high_a = self._nodes[a]
        var_b, low_b, high_b = self._nodes[b]
        var = min(var_a, var_b)
        if var_a == var:
            al, ah = low_a, high_a
        else:
            al = ah = a
        if var_b == var:
            bl, bh = low_b, high_b
        else:
            bl = bh = b
        low = self._apply(op, al, bl)
        high = self._apply(op, ah, bh)
        return self._mk(var, low, high)

    def and_(self, a: int, b: int) -> int:
        return self._apply("and", a, b)

    def or_(self, a: int, b: int) -> int:
        return self._apply("or", a, b)

    def sat_one(self, node: int) -> dict[str, bool]:
        """One satisfying assignment (partial) of a non-empty BDD."""
        assignment: dict[str, bool] = {}
        while node > self.TRUE:
            var, low, high = self._nodes[node]
            if low != self.FALSE:
                assignment[self._vars[var]] = False
                node = low
            else:
                assignment[self._vars[var]] = True
                node = high
        return assignment


def analyze(tour: Tour) -> Verdict:
    """Decide whether every complete profile reaches an end step finitely.

    Returns Verdict(ok=True) iff all profiles succeed. Otherwise the
    failure is one concrete profile whose replay() run reproduces the
    reported trajectory and kind exactly.
    """
    bdd = _Bdd(tour.attributes)
    # taken[i] = profiles for which branch i is the first matching branch:
    # its condition holds and no earlier condition does (priority/shadowing).
    taken: dict[str, list[tuple[int, str]]] = {}
    winning: dict[str, int] = {}
    for name, step in tour.steps.items():
        if step.is_end:
            winning[name] = bdd.TRUE
            continue
        winning[name] = bdd.FALSE
        shadowed = bdd.FALSE
        entries = []
        for branch in step.branches:
            cond = bdd.condition(branch.condition)
            entries.append((bdd.and_(cond, bdd.neg(shadowed)), branch.target))
            shadowed = bdd.or_(shadowed, cond)
        taken[name] = entries
    # Least fixpoint: profiles that reach an end step in finitely many
    # clicks. Ascending chain, so the loop terminates.
    changed = True
    while changed:
        changed = False
        for name, entries in taken.items():
            new = bdd.FALSE
            for pre, target in entries:
                new = bdd.or_(new, bdd.and_(pre, winning[target]))
            if new != winning[name]:
                winning[name] = new
                changed = True
    if winning[tour.entry] == bdd.TRUE:
        return Verdict(ok=True)
    witness = bdd.sat_one(bdd.neg(winning[tour.entry]))
    profile = {attr: witness.get(attr, False) for attr in tour.attributes}
    result = replay(tour, profile)
    return Verdict(
        ok=False,
        failure=Failure(
            kind=result.outcome, profile=profile, trajectory=result.trajectory
        ),
    )
