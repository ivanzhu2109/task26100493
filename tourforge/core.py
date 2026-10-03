"""Navigation validation: analyze() and replay()."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .model import Profile, Tour
from .bdd import BDD


class Outcome(str, Enum):
    SUCCESS = "success"          # reached an end step
    STUCK = "stuck"              # no branch condition matched
    LOOP = "loop"                # revisited a step (deterministic cycle)


@dataclass(frozen=True)
class ReplayResult:
    trajectory: list[str]
    outcome: Outcome


@dataclass(frozen=True)
class Counterexample:
    profile: Profile
    trajectory: list[str]
    failure: Outcome  # Outcome.STUCK or Outcome.LOOP


@dataclass(frozen=True)
class AnalysisResult:
    passed: bool
    counterexample: Optional[Counterexample] = None


def replay(tour: Tour, profile: Profile) -> ReplayResult:
    """Concretely run one profile until end / stuck / first step revisit."""
    trajectory: list[str] = []
    visited: set[str] = set()
    current = tour.entry
    while True:
        trajectory.append(current)
        step = tour.steps[current]
        if step.is_end:
            return ReplayResult(trajectory, Outcome.SUCCESS)
        if current in visited:
            # Deterministic step revisit: the profile loops forever.
            return ReplayResult(trajectory, Outcome.LOOP)
        visited.add(current)
        for branch in step.branches:
            if all(profile[attr] == value for attr, value in branch.condition.items()):
                current = branch.target
                break
        else:
            return ReplayResult(trajectory, Outcome.STUCK)


def _condition_node(bdd: BDD, condition: dict[str, bool]) -> int:
    return bdd.conjunction(
        [bdd.literal(attr, value) for attr, value in condition.items()]
    )


def analyze(tour: Tour) -> AnalysisResult:
    """Pass iff every complete profile reaches an end step in finite steps."""
    bdd = BDD(list(tour.attributes))

    # Per step, precompute the exact profile sets that take each branch.
    # Branch i is taken iff its condition holds and every earlier branch
    # condition fails (ordered priority / shadowing).  g_none is the set
    # of profiles matching no branch at all (stuck).
    guards: dict[str, list[int]] = {}
    stuck: dict[str, int] = {}
    for name, step in tour.steps.items():
        if step.is_end:
            continue
        earlier_fail = bdd.constant(True)
        step_guards: list[int] = []
        for branch in step.branches:
            cond = _condition_node(bdd, branch.condition)
            step_guards.append(bdd.conjunction([earlier_fail, cond]))
            earlier_fail = bdd.conjunction([earlier_fail, bdd.negate(cond)])
        guards[name] = step_guards
        stuck[name] = earlier_fail

    # fail[s] = set of profiles whose deterministic trajectory from s
    # never reaches an end step (gets stuck or loops).  It is the greatest
    # fixpoint of  fail[s] = stuck[s] OR OR_i (guard_i[s] AND fail[target_i])
    # computed by descending iteration from "all profiles".
    fail: dict[str, int] = {
        name: bdd.constant(step.is_end is False)
        for name, step in tour.steps.items()
    }
    changed = True
    while changed:
        changed = False
        for name, step in tour.steps.items():
            if step.is_end:
                continue
            terms = [stuck[name]]
            for guard, branch in zip(guards[name], step.branches):
                terms.append(bdd.conjunction([guard, fail[branch.target]]))
            updated = bdd.disjunction(terms)
            if updated != fail[name]:
                fail[name] = updated
                changed = True

    if fail[tour.entry] == bdd.constant(False):
        return AnalysisResult(passed=True)

    profile = bdd.one_satisfying_assignment(fail[tour.entry])
    assert profile is not None
    # Materialize the counterexample through replay so the returned
    # trajectory and failure kind are exactly what replay reproduces.
    result = replay(tour, profile)
    assert result.outcome in (Outcome.STUCK, Outcome.LOOP)
    return AnalysisResult(
        passed=False,
        counterexample=Counterexample(
            profile=profile,
            trajectory=result.trajectory,
            failure=result.outcome,
        ),
    )
