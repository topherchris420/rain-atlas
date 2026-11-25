import numpy as np
import pytest

from rain_atlas.research.nine_fourths import parameter_gain, reference_gain


def test_factorized_gain_matches_reference():
    rng = np.random.default_rng(31)
    x = rng.normal(size=(7, 23, 9))
    g = x.swapaxes(-1, -2) @ x
    m = rng.normal(size=(4, 9))
    q = rng.normal(size=(4, 4))
    p = q @ q.T + np.eye(4)
    np.testing.assert_allclose(parameter_gain(p, m, g), reference_gain(p, m, g), atol=1e-10)


def test_legacy_indices_are_not_matrix_product():
    p = np.eye(2)
    m = np.eye(2)
    g = np.array([[[2.0, 0.0], [0.0, 3.0]]])
    legacy = np.einsum("ij,kl,blm,nm->bin", p, m, g, m)
    corrected = (p @ m) @ g @ m.T
    assert not np.allclose(legacy, corrected)
    assert parameter_gain(p, m, g)[0] == pytest.approx(0.5 * np.log(12))


def test_zero_and_invalid_precision():
    assert parameter_gain(np.eye(2), np.eye(2), np.zeros((1, 2, 2)))[0] == pytest.approx(0)
    with pytest.raises(np.linalg.LinAlgError):
        parameter_gain(-np.eye(2), np.eye(2), np.zeros((1, 2, 2)))
    with pytest.raises(ValueError):
        parameter_gain(np.eye(2), np.eye(3), np.zeros((1, 3, 3)))
