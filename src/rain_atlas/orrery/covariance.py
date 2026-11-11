"""Covariance propagation through the state-transition matrix, checked against Monte Carlo.

Linear covariance mapping: for dynamics x' = f(x) with state-transition matrix
Phi(t, t0) = d x(t) / d x(t0) (integrated by the variational equations in
:meth:`ForceModel.rhs_stm`), an initial covariance P0 maps as

    P(t) = Phi(t, t0) P0 Phi(t, t0)^T .

This is exact for linear dynamics and a first-order approximation otherwise; it
is checked here against a Monte-Carlo cloud of samples each propagated by the
*analytic* Kepler solution (an independent propagator), so agreement tests both
the STM and the nonlinearity of the mapping. Two regimes are reported: a small
initial uncertainty (where the linear map should be excellent) and a large one
(where nonlinearity shows up, especially in along-track position).

Reported statistics: the sample covariance vs the linear covariance (Frobenius
and per-block relative differences), the position 1-sigma ellipsoid volume
ratio, and a chi-square consistency fraction of the Monte-Carlo samples against
the linear covariance.
"""

from __future__ import annotations

import numpy as np

from .integrators import integrate
from .kepler import kepler_trajectory


def propagate_covariance(stm: np.ndarray, p0: np.ndarray) -> np.ndarray:
    return stm @ p0 @ stm.T


def stm_at(model, x0: np.ndarray, t: float) -> tuple[np.ndarray, np.ndarray]:
    """Propagate the state and 6x6 STM to time ``t`` in the force model."""

    y0 = np.concatenate([x0, np.eye(6).ravel()])
    res = integrate(model.rhs_stm, 0.0, y0, [t], method="rkf78", rtol=1e-12, atol=1e-12)
    final = res.states[-1]
    return final[:6], final[6:42].reshape(6, 6)


def monte_carlo_cloud(
    x0: np.ndarray, p0: np.ndarray, t: float, mu: float, samples: int, seed: int
) -> np.ndarray:
    """Propagate ``samples`` draws from N(x0, p0) by the analytic two-body solution."""

    rng = np.random.default_rng(seed)
    draws = rng.multivariate_normal(x0, p0, size=samples)
    out = np.empty((samples, 6))
    for i, x in enumerate(draws):
        out[i] = kepler_trajectory(x[:3], x[3:6], [t], mu)[0]
    return out


def covariance_study(
    x0: np.ndarray,
    p0: np.ndarray,
    t: float,
    mu: float,
    model=None,
    samples: int = 4000,
    seed: int = 20260115,
) -> dict:
    """Compare STM-propagated covariance against a Kepler Monte-Carlo cloud.

    If ``model`` is None, the STM is formed from the analytic two-body partials
    propagated numerically through a point-mass model is skipped, and instead
    the STM is estimated by finite differences of the Kepler flow (independent
    of any force model), isolating the covariance mapping itself.
    """

    if model is not None:
        x_lin, stm = stm_at(model, x0, t)
    else:
        x_lin = kepler_trajectory(x0[:3], x0[3:6], [t], mu)[0]
        stm = np.empty((6, 6))
        step = np.array([1e-3, 1e-3, 1e-3, 1e-6, 1e-6, 1e-6])
        for j in range(6):
            dx = np.zeros(6)
            dx[j] = step[j]
            plus = kepler_trajectory((x0 + dx)[:3], (x0 + dx)[3:6], [t], mu)[0]
            minus = kepler_trajectory((x0 - dx)[:3], (x0 - dx)[3:6], [t], mu)[0]
            stm[:, j] = (plus - minus) / (2.0 * step[j])

    p_lin = propagate_covariance(stm, p0)
    cloud = monte_carlo_cloud(x0, p0, t, mu, samples, seed)
    mean_mc = cloud.mean(axis=0)
    p_mc = np.cov(cloud.T, bias=False)

    def block_rel(a, b):
        return float(np.linalg.norm(a - b) / np.linalg.norm(b))

    pos_lin, pos_mc = p_lin[:3, :3], p_mc[:3, :3]
    vol_ratio = float(np.sqrt(np.linalg.det(pos_lin) / np.linalg.det(pos_mc)))
    # chi-square consistency of MC samples against the linear covariance.
    diff = cloud - x_lin
    d2 = np.einsum("ij,jk,ik->i", diff, np.linalg.inv(p_lin), diff)
    from scipy.stats import chi2  # noqa: PLC0415

    inside = float(np.mean(d2 <= chi2.ppf(0.95, 6)))
    return {
        "samples": samples,
        "linear_covariance": p_lin.tolist(),
        "monte_carlo_covariance": p_mc.tolist(),
        "mean_offset_m": float(np.linalg.norm((mean_mc - x_lin)[:3]) * 1000.0),
        "position_block_rel_diff": block_rel(pos_lin, pos_mc),
        "velocity_block_rel_diff": block_rel(p_lin[3:, 3:], p_mc[3:, 3:]),
        "full_frobenius_rel_diff": block_rel(p_lin, p_mc),
        "position_ellipsoid_volume_ratio": vol_ratio,
        "chi2_95_inside_fraction": inside,
    }


def ellipsoid_axes(cov_block: np.ndarray) -> dict:
    """Principal 1-sigma semi-axes (km) and directions of a 3x3 position covariance."""

    vals, vecs = np.linalg.eigh(cov_block)
    order = np.argsort(vals)[::-1]
    vals, vecs = vals[order], vecs[:, order]
    return {
        "semi_axes_km": np.sqrt(np.maximum(vals, 0.0)).tolist(),
        "axes_directions": vecs.T.tolist(),
    }
