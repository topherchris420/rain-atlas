"""The evidence core against independent computations (quadrature, stacked regression)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy import integrate, stats

from rain_atlas.research.inference import (
    Analysis,
    ExperimentStats,
    Hypothesis,
    Posterior,
    PriorSpec,
    change_hypotheses,
    log_evidence_batch,
)
from rain_atlas.research.oscillator import (
    INDEX,
    LIBRARY,
    Design,
    Instrument,
    World,
    coefficient_vector,
)


def test_closed_form_evidence_matches_double_quadrature():
    rng = np.random.default_rng(3)
    x = rng.normal(size=6)
    y = 0.8 * x + rng.normal(scale=0.5, size=6)
    m0, v0, a0, b0 = 0.2, 4.0, 2.0, 0.6

    def integrand(theta, s2):
        like = np.prod(stats.norm.pdf(y, loc=theta * x, scale=math.sqrt(s2)))
        prior_theta = stats.norm.pdf(theta, loc=m0, scale=math.sqrt(s2 * v0))
        prior_s2 = stats.invgamma.pdf(s2, a0, scale=b0)
        return like * prior_theta * prior_s2

    brute, _ = integrate.dblquad(integrand, 1e-6, 30.0, -12.0, 12.0, epsabs=1e-14, epsrel=1e-9)
    logz, *_ = log_evidence_batch(
        np.array([[[x @ x]]]),
        np.array([[x @ y]]),
        np.array([y @ y]),
        np.array([6.0]),
        np.array([[m0]]),
        np.array([[[1.0 / v0]]]),
        a0,
        b0,
    )
    assert logz[0] == pytest.approx(math.log(brute), abs=2e-6)


def _random_stats(rng, count, rows=40):
    out, stacked = [], []
    for _ in range(count):
        phi = rng.normal(size=(rows, len(LIBRARY)))
        y = phi[:, 0] * -1.1 + phi[:, 1] * -0.2 + rng.normal(size=rows)
        out.append(ExperimentStats.from_rows(phi, y))
        stacked.append((phi, y))
    return out, stacked


@pytest.mark.parametrize(
    "hypothesis",
    [
        Hypothesis(("x", "v", "u")),
        Hypothesis(("x", "v", "u"), 2, ("x",)),
        Hypothesis(("x", "v", "u", "x^3"), 3, ("v", "1")),
    ],
)
def test_assembly_from_sufficient_statistics_matches_stacked_regression(hypothesis):
    rng = np.random.default_rng(11)
    stats_list, stacked = _random_stats(rng, 5)
    prior = PriorSpec.default(noise_sd=1.3)
    fit = Analysis(stats_list, prior, budget=16, change_prior=0.3).evaluate([hypothesis])[0]
    # Build the augmented design matrix row by row, independently of the prefix sums.
    rows, ys = [], []
    for e, (phi, y) in enumerate(stacked):
        post = hypothesis.change_at is not None and e >= hypothesis.change_at
        cols = [phi[:, INDEX[t]] for t in hypothesis.structure]
        cols += [phi[:, INDEX[t]] * (1.0 if post else 0.0) for t in hypothesis.changed]
        rows.append(np.stack(cols, axis=1))
        ys.append(y)
    X, y = np.vstack(rows), np.concatenate(ys)
    logz, *_ = log_evidence_batch(
        (X.T @ X)[None],
        (X.T @ y)[None],
        np.array([y @ y]),
        np.array([float(len(y))]),
        fit.m0[None],
        fit.V0inv[None],
        prior.a0,
        prior.noise_sd**2 * (prior.a0 - 1),
    )
    assert fit.log_evidence == pytest.approx(float(logz[0]), rel=1e-12, abs=1e-9)


def test_incremental_marginal_equals_refit_with_the_new_experiment():
    rng = np.random.default_rng(5)
    stats_list, _ = _random_stats(rng, 4)
    new_stats, _ = _random_stats(rng, 1)
    prior = PriorSpec.default(noise_sd=1.1)
    hyps = [Hypothesis(("x", "v", "u")), Hypothesis(("x", "v", "u"), 2, ("u",))]
    before = Analysis(stats_list, prior, budget=16, change_prior=0.3).evaluate(hyps)
    after = Analysis(stats_list + new_stats, prior, budget=16, change_prior=0.3).evaluate(hyps)
    s = new_stats[0]
    inc = Analysis(stats_list, prior, budget=16, change_prior=0.3).new_data_log_marginal(
        before, s.G[None], s.h[None], np.array([s.q]), np.array([s.n])
    )
    for j in range(2):
        assert inc[0, j] == pytest.approx(after[j].log_evidence - before[j].log_evidence, abs=1e-8)


def _observe(world, designs):
    inst = Instrument(world)
    return [inst.run(d, i) for i, d in enumerate(designs)]


def test_posterior_identifies_duffing_and_its_coefficients():
    coeffs = {"x": -1.2, "v": -0.15, "u": 1.0, "x^3": -0.45}
    world = World(coefficients=coeffs, noise_scale=0.3, seed=99)
    designs = [Design(1.2, 1.1, 0.5), Design(1.5, 1.2, -0.8), Design(1.0, 0.9, 1.0), Design(1.4, 1.3, 0.0)]
    obs = _observe(world, designs)
    stats_list = [ExperimentStats.from_rows(*o.regression()) for o in obs]
    structures = [("x", "v", "u"), ("x", "v", "u", "x^3"), ("x", "v", "u", "1"), ("x", "v", "u", "x^3", "1")]
    analysis = Analysis(stats_list, PriorSpec.default(), budget=16, change_prior=0.3)
    post = Posterior.from_fits(analysis.evaluate([Hypothesis(s) for s in structures]))
    assert post.top.hypothesis.structure == ("x", "v", "u", "x^3")
    assert post.top.probability > 0.9
    est = post.top.current_coefficients()
    sd = post.top.current_sd()
    truth = coefficient_vector(coeffs)
    for t in ("x", "v", "u", "x^3"):
        assert abs(est[INDEX[t]] - truth[INDEX[t]]) < 4 * sd[INDEX[t]] + 1e-3


def test_change_point_and_attribution_are_recovered():
    pre = {"x": -1.0, "v": -0.2, "u": 1.0}
    post = {"x": -1.45, "v": -0.2, "u": 1.0}
    world = World(coefficients=pre, noise_scale=0.3, change_at=3, changed_coefficients=post, seed=5)
    designs = [Design(1.0, 1.0 + 0.1 * i, 0.3) for i in range(6)]
    obs = _observe(world, designs)
    stats_list = [ExperimentStats.from_rows(*o.regression()) for o in obs]
    structure = ("x", "v", "u")
    hyps = [Hypothesis(structure)] + change_hypotheses(structure, len(obs), ("x^3", "1"))
    analysis = Analysis(stats_list, PriorSpec.default(), budget=16, change_prior=0.3)
    posterior = Posterior.from_fits(analysis.evaluate(hyps))
    assert posterior.p_change() > 0.99
    assert next(iter(posterior.change_location())) == 3
    assert next(iter(posterior.attribution())) == ("x",)
    assert posterior.top.current_coefficients()[INDEX["x"]] == pytest.approx(-1.45, abs=0.08)


def test_one_step_predictive_intervals_are_calibrated_on_fresh_data():
    world = World(coefficients={"x": -0.9, "v": -0.1, "u": 0.8}, noise_scale=0.5, seed=21)
    obs = _observe(world, [Design(1.0, 0.8, 0.4), Design(0.7, 1.4, -0.6)])
    analysis = Analysis(
        [ExperimentStats.from_rows(*o.regression()) for o in obs],
        PriorSpec.default(),
        budget=16,
        change_prior=0.0,
    )
    fit = Posterior.from_fits(analysis.evaluate([Hypothesis(("x", "v", "u"))])).top
    fresh = Instrument(world).run(Design(1.2, 1.1, 0.0), 7)
    phi, y = fresh.regression()
    mean, scale, dof = fit.predictive(phi)
    lo, hi = stats.t.interval(0.9, dof, loc=mean, scale=scale)
    coverage = np.mean((y >= lo) & (y <= hi))
    assert 0.85 <= coverage <= 0.95
