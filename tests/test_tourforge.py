"""Automated tests for the TourForge validation library."""

from __future__ import annotations

import itertools
import random
import time

from tourforge import Branch, Outcome, Step, Tour, analyze, replay


# ---------------------------------------------------------------- helpers

def exhaustive_verdict(tour: Tour) -> bool:
    """Independent reference: replay every complete profile."""
    for values in itertools.product([False, True], repeat=len(tour.attributes)):
        profile = dict(zip(tour.attributes, values))
        if replay(tour, profile).outcome is not Outcome.SUCCESS:
            return False
    return True


def check_against_exhaustive(tour: Tour) -> None:
    result = analyze(tour)
    assert result.passed == exhaustive_verdict(tour)
    if not result.passed:
        ce = result.counterexample
        assert ce is not None
        assert set(ce.profile) == set(tour.attributes)
        assert ce.failure in (Outcome.STUCK, Outcome.LOOP)
        # The counterexample must be reproducible by replay.
        again = replay(tour, ce.profile)
        assert again.trajectory == ce.trajectory
        assert again.outcome == ce.failure
        if ce.failure is Outcome.LOOP:
            # Loop trajectories must include the closing revisit.
            assert ce.trajectory[-1] in ce.trajectory[:-1]
        else:
            assert not tour.steps[ce.trajectory[-1]].is_end


# ------------------------------------------------------- handcrafted tours

def test_shadowed_back_edge_passes() -> None:
    # The empty-condition first branch always fires, so the p0 back edge
    # to S0 is shadowed and can never execute: no loop is possible.
    tour = Tour(
        attributes=("p0",),
        steps={
            "S0": Step("S0", branches=(Branch("S1"),)),
            "S1": Step("S1", branches=(Branch("END"), Branch("S0", {"p0": True}))),
            "END": Step("END", is_end=True),
        },
        entry="S0",
    )
    check_against_exhaustive(tour)
    assert analyze(tour).passed


def test_shadowed_branch_changes_outcome() -> None:
    # Same graph, but the back edge is first and fires for p0=True:
    # those profiles loop S0 -> S1 -> S0.
    tour = Tour(
        attributes=("p0",),
        steps={
            "S0": Step("S0", branches=(Branch("S1"),)),
            "S1": Step("S1", branches=(Branch("S0", {"p0": True}), Branch("END"))),
            "END": Step("END", is_end=True),
        },
        entry="S0",
    )
    check_against_exhaustive(tour)
    result = analyze(tour)
    assert not result.passed
    assert result.counterexample.failure is Outcome.LOOP
    assert result.counterexample.profile == {"p0": True}


def test_missing_branch_only_for_some_profiles() -> None:
    # Only profiles with p0=True, p1=False reach S1 and find no branch.
    tour = Tour(
        attributes=("p0", "p1"),
        steps={
            "S0": Step("S0", branches=(Branch("S1", {"p0": True}), Branch("END"))),
            "S1": Step("S1", branches=(Branch("END", {"p1": True}),)),
            "END": Step("END", is_end=True),
        },
        entry="S0",
    )
    check_against_exhaustive(tour)
    result = analyze(tour)
    assert not result.passed
    ce = result.counterexample
    assert ce.failure is Outcome.STUCK
    assert ce.profile["p0"] is True and ce.profile["p1"] is False
    assert ce.trajectory == ["S0", "S1"]


def test_unreachable_problem_step_does_not_block() -> None:
    # S2 would loop / get stuck, but no profile can ever reach it.
    tour = Tour(
        attributes=("p0",),
        steps={
            "S0": Step("S0", branches=(Branch("END"),)),
            "S1": Step("S1", branches=(Branch("S2", {"p0": True}),)),
            "S2": Step("S2", branches=(Branch("S2"),)),
            "END": Step("END", is_end=True),
        },
        entry="S0",
    )
    check_against_exhaustive(tour)
    assert analyze(tour).passed


def test_structural_cycle_without_executable_loop() -> None:
    # There is a cycle S0 -> S1 -> S0 in the graph, but the guards are
    # mutually exclusive along any single fixed profile, so it passes.
    tour = Tour(
        attributes=("p0",),
        steps={
            "S0": Step("S0", branches=(Branch("S1", {"p0": True}), Branch("END"))),
            "S1": Step("S1", branches=(Branch("S0", {"p0": False}), Branch("END"))),
            "END": Step("END", is_end=True),
        },
        entry="S0",
    )
    check_against_exhaustive(tour)
    assert analyze(tour).passed


# ---------------------------------------------------------- random tours

def random_tour(rng: random.Random, n_attrs: int, n_steps: int) -> Tour:
    attrs = tuple(f"p{i}" for i in range(n_attrs))
    names = [f"S{i}" for i in range(n_steps)]
    n_end = rng.randint(1, max(1, n_steps // 3))
    end_names = set(rng.sample(names[1:], n_end))
    steps: dict[str, Step] = {}
    for name in names:
        if name in end_names:
            steps[name] = Step(name, is_end=True)
            continue
        branches = []
        for _ in range(rng.randint(1, 3)):
            condition = {
                attr: rng.random() < 0.5
                for attr in rng.sample(attrs, rng.randint(0, min(2, n_attrs)))
            }
            branches.append(Branch(rng.choice(names), condition))
        steps[name] = Step(name, branches=tuple(branches))
    return Tour(attributes=attrs, steps=steps, entry="S0")


def test_random_small_tours_match_exhaustive() -> None:
    rng = random.Random(20261004)
    for _ in range(300):
        tour = random_tour(rng, rng.randint(1, 6), rng.randint(2, 8))
        check_against_exhaustive(tour)


# ------------------------------------------------------------- scale tour

def build_scale_tour(back_edge_on_p0_true: bool) -> Tour:
    attrs = tuple(f"p{i}" for i in range(47))
    steps: dict[str, Step] = {}
    steps["S0"] = Step("S0", branches=(Branch("S1", {"p0": True}), Branch("S48")))
    for i in range(1, 47):
        steps[f"S{i}"] = Step(
            f"S{i}",
            branches=(Branch(f"S{i+1}", {f"p{i}": True}), Branch(f"S{i+2}")),
        )
    steps["S47"] = Step(
        "S47",
        branches=(Branch("S0", {"p0": back_edge_on_p0_true}), Branch("S48")),
    )
    steps["S48"] = Step("S48", is_end=True)
    return Tour(attributes=attrs, steps=steps, entry="S0")


def test_scale_tour_with_unreachable_back_edge_passes() -> None:
    tour = build_scale_tour(back_edge_on_p0_true=False)
    start = time.monotonic()
    result = analyze(tour)
    elapsed = time.monotonic() - start
    assert result.passed
    assert elapsed < 10.0


def test_scale_tour_with_executable_back_edge_fails() -> None:
    tour = build_scale_tour(back_edge_on_p0_true=True)
    start = time.monotonic()
    result = analyze(tour)
    elapsed = time.monotonic() - start
    assert elapsed < 10.0
    assert not result.passed
    ce = result.counterexample
    assert ce.failure is Outcome.LOOP
    # The loop must take the S47 back edge, which requires p0=True.
    assert ce.profile["p0"] is True
    assert "S47" in ce.trajectory
    assert ce.trajectory[-1] in ce.trajectory[:-1]
    again = replay(tour, ce.profile)
    assert again.trajectory == ce.trajectory
    assert again.outcome is Outcome.LOOP
