"""Data model for TourForge tour publish validation.

A tour is a fixed set of steps. A viewer profile is a complete boolean
assignment over the tour's attributes, given in full at the start and
immutable for the whole tour. Only navigation is analyzed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# A literal: attribute name paired with the boolean value it must equal.
Literal = tuple[str, bool]

# A condition is a conjunction of literals; the empty condition is always true.
Condition = tuple[Literal, ...]

# A complete profile: every attribute mapped to a boolean.
Profile = dict[str, bool]


@dataclass(frozen=True)
class Branch:
    """One ordered branch of a normal step."""

    target: str
    condition: Condition = ()


@dataclass(frozen=True)
class Step:
    """A tour step. End steps are terminal; normal steps hold ordered branches."""

    name: str
    is_end: bool = False
    branches: tuple[Branch, ...] = ()


@dataclass(frozen=True)
class Tour:
    """A tour: entry step, attribute names, and named steps."""

    entry: str
    attributes: tuple[str, ...]
    steps: dict[str, Step] = field(default_factory=dict)


@dataclass(frozen=True)
class ReplayResult:
    """Outcome of concretely executing one fixed profile."""

    trajectory: tuple[str, ...]
    outcome: str  # "end" | "stuck" | "loop"


@dataclass(frozen=True)
class Failure:
    """A counterexample: one complete profile that cannot reach an end step."""

    kind: str  # "stuck" | "loop"
    profile: Profile
    trajectory: tuple[str, ...]


@dataclass(frozen=True)
class Verdict:
    """Result of analyze(): ok, or a single reproducible failure."""

    ok: bool
    failure: Failure | None = None
