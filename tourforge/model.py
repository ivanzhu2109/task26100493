"""Data model for TourForge tours.

A tour is a fixed set of steps.  A viewer is described by a *profile*: a
complete assignment of booleans to the tour's attributes, fixed for the
whole visit.  Navigation only: each normal step has a single "continue"
hotspot with up to 3 ordered branches; the first branch whose condition
holds under the profile is taken (later matching branches are shadowed).
"""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_ATTRIBUTES = 48
MAX_STEPS = 50
MAX_BRANCHES = 3

# A condition is a conjunction of attribute=value literals.
# An empty condition is always true.
Condition = dict[str, bool]


@dataclass(frozen=True)
class Branch:
    """One ordered outgoing branch of a normal step."""

    target: str
    condition: Condition = field(default_factory=dict)


@dataclass(frozen=True)
class Step:
    """A tour step.  End steps have no branches."""

    name: str
    is_end: bool = False
    branches: tuple[Branch, ...] = ()


@dataclass(frozen=True)
class Tour:
    """A whole tour: named attributes, named steps, one entry step."""

    attributes: tuple[str, ...]
    steps: dict[str, Step]
    entry: str


# A profile is a complete, fixed assignment of every attribute.
Profile = dict[str, bool]
