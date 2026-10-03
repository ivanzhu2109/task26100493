"""Tests for the TourForge validation library."""

import itertools
import random
import time
import unittest

from tourforge import Branch, Step, Tour, analyze, replay


def all_profiles(attributes):
    for bits in itertools.product((False, True), repeat=len(attributes)):
        yield dict(zip(attributes, bits))


def reference_ok(tour):
    """Independent exhaustive reference: replay every complete profile."""
    return all(
        replay(tour, profile).outcome == "end"
        for profile in all_profiles(tour.attributes)
    )


def check_against_reference(tour):
    """analyze must agree with exhaustive replay, and any counterexample
    must be exactly reproducible by replay under the returned profile."""
    verdict = analyze(tour)
    expected = reference_ok(tour)
    assert verdict.ok == expected, (verdict, expected)
    if not verdict.ok:
        failure = verdict.failure
        assert failure.kind in ("stuck", "loop")
        assert set(failure.profile) == set(tour.attributes)
        result = replay(tour, failure.profile)
        assert result.outcome == failure.kind, (result, failure)
        assert result.trajectory == failure.trajectory, (result, failure)
        if failure.kind == "loop":
            assert failure.trajectory[-1] in failure.trajectory[:-1]
    return verdict


class ShadowingTest(unittest.TestCase):
    """A higher-priority branch shadowing a later back edge must count."""

    def make(self, shadow):
        branches = []
        if shadow:
            branches.append(Branch("END"))
        branches.append(Branch("S0", (("p0", True),)))
        branches.append(Branch("END"))
        return Tour(
            entry="S0",
            attributes=("p0",),
            steps={
                "S0": Step("S0", branches=(Branch("S1"),)),
                "S1": Step("S1", branches=tuple(branches)),
                "END": Step("END", is_end=True),
            },
        )

    def test_shadowed_back_edge_passes(self):
        # The empty-condition first branch always fires, so the back edge
        # to S0 is unreachable and no profile can loop.
        check_against_reference(self.make(shadow=True))

    def test_unshadowed_back_edge_loops(self):
        verdict = check_against_reference(self.make(shadow=False))
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.failure.kind, "loop")
        self.assertEqual(verdict.failure.profile, {"p0": True})


class PartialStuckTest(unittest.TestCase):
    """Missing branch coverage for only some reachable profiles."""

    def test_stuck_only_for_some_profiles(self):
        tour = Tour(
            entry="S0",
            attributes=("p0", "p1"),
            steps={
                "S0": Step(
                    "S0",
                    branches=(Branch("S1", (("p0", True),)), Branch("END")),
                ),
                "S1": Step("S1", branches=(Branch("END", (("p1", True),)),)),
                "END": Step("END", is_end=True),
            },
        )
        verdict = check_against_reference(tour)
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.failure.kind, "stuck")
        self.assertEqual(
            verdict.failure.profile, {"p0": True, "p1": False}
        )
        self.assertEqual(verdict.failure.trajectory, ("S0", "S1"))


class UnreachableTest(unittest.TestCase):
    """Problems on steps unreachable from the entry must not block publish."""

    def test_unreachable_stuck_step_ignored(self):
        tour = Tour(
            entry="S0",
            attributes=("p0",),
            steps={
                "S0": Step("S0", branches=(Branch("END"),)),
                "S1": Step("S1"),  # unreachable and has no branches at all
                "END": Step("END", is_end=True),
            },
        )
        self.assertTrue(analyze(tour).ok)


class RandomSmallGraphTest(unittest.TestCase):
    """Fixed-seed random cyclic small graphs vs exhaustive reference."""

    def test_random_tours(self):
        rng = random.Random(20261004)
        for _ in range(300):
            n_attrs = rng.randint(1, 6)
            attrs = tuple(f"p{i}" for i in range(n_attrs))
            n_steps = rng.randint(2, 8)
            names = [f"S{i}" for i in range(n_steps)]
            ends = set(rng.sample(names, rng.randint(1, 2)))
            steps = {}
            for name in names:
                if name in ends:
                    steps[name] = Step(name, is_end=True)
                    continue
                branches = []
                for _ in range(rng.randint(1, 3)):
                    condition = tuple(
                        (rng.choice(attrs), rng.choice((False, True)))
                        for _ in range(rng.randint(0, 2))
                    )
                    branches.append(Branch(rng.choice(names), condition))
                steps[name] = Step(name, branches=tuple(branches))
            tour = Tour(entry="S0", attributes=attrs, steps=steps)
            check_against_reference(tour)


def make_scale_tour(back_edge_on_p0_false):
    """49 steps S0..S48, 47 attributes p0..p46; S48 is the end step."""
    attrs = tuple(f"p{i}" for i in range(47))
    steps = {}
    steps["S0"] = Step(
        "S0", branches=(Branch("S1", (("p0", True),)), Branch("S48"))
    )
    for i in range(1, 47):
        steps[f"S{i}"] = Step(
            f"S{i}",
            branches=(
                Branch(f"S{i + 1}", ((f"p{i}", True),)),
                Branch(f"S{i + 2}"),
            ),
        )
    if back_edge_on_p0_false:
        s47_branches = (Branch("S0", (("p0", False),)), Branch("S48"))
    else:
        s47_branches = (Branch("S0", (("p0", True),)), Branch("S48"))
    steps["S47"] = Step("S47", branches=s47_branches)
    steps["S48"] = Step("S48", is_end=True)
    return Tour(entry="S0", attributes=attrs, steps=steps)


class ScaleTest(unittest.TestCase):
    def test_structural_cycle_still_passes(self):
        tour = make_scale_tour(back_edge_on_p0_false=True)
        start = time.monotonic()
        verdict = analyze(tour)
        elapsed = time.monotonic() - start
        self.assertTrue(verdict.ok)
        self.assertLess(elapsed, 10.0)

    def test_executable_cycle_rejected(self):
        tour = make_scale_tour(back_edge_on_p0_false=False)
        start = time.monotonic()
        verdict = analyze(tour)
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 10.0)
        self.assertFalse(verdict.ok)
        failure = verdict.failure
        self.assertEqual(failure.kind, "loop")
        result = replay(tour, failure.profile)
        self.assertEqual(result.outcome, "loop")
        self.assertEqual(result.trajectory, failure.trajectory)
        self.assertEqual(failure.trajectory[0], "S0")
        self.assertEqual(failure.trajectory[-1], "S0")
        self.assertIn("S47", failure.trajectory)


if __name__ == "__main__":
    unittest.main()
