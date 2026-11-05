"""Regenerate reviewed manifests and analytical fixtures; never runs a method.

Expected values come from algebraic cases (not captured implementation output).
This also demonstrates the small directory template used for new skills.

The committed fixtures are canonical. Example inputs use vectorized NumPy
sin/cos, whose last-ulp results differ between CPUs and builds (Linux x86-64
vs the Windows host that first ran this: up to 1.6e-16 relative). Tolerance
outcomes are unaffected, but the bytes, and so the skill content hashes,
change. Regenerate only to change a skill deliberately; files are written
with LF so a Windows run does not also change line endings.
"""

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
N = {"type": "number"}
INTEGER = {"type": "integer"}
S = {"type": "string"}
ARRAY = {"type": "array", "items": N, "minItems": 1, "maxItems": 32768}
MATRIX = {"type": "array", "items": ARRAY, "minItems": 1, "maxItems": 32768}
ART = {
    "type": "object",
    "required": ["$artifact", "sha256"],
    "additionalProperties": False,
    "properties": {"$artifact": S, "sha256": S},
}


def num(default=None, **kw):
    return {**N, **kw, **({"default": default} if default is not None else {})}


def integer(default=None, **kw):
    return {**INTEGER, **kw, **({"default": default} if default is not None else {})}


def schema(props, required=None):
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": props,
        "required": required if required is not None else list(props),
    }


tone = [math.cos(2 * math.pi * 8 * i / 64) for i in range(256)]
fir_input = [math.sin(i * 1.37) + math.cos(i * 0.73) for i in range(128)]
fir_output = [
    0.7 * x - (0.2 * fir_input[i - 1] if i else 0) + (0.1 * fir_input[i - 2] if i > 1 else 0)
    for i, x in enumerate(fir_input)
]
fs = num(exclusiveMinimum=0, unit="Hz")
specs = [
    (
        "stft-analysis",
        "stft",
        "signal-processing",
        "spectral.time-frequency",
        {"x": ARRAY, "fs": fs, "nperseg": integer(128, minimum=4), "hop": integer(64, minimum=1)},
        ["x", "fs"],
        {
            "power": ART,
            "frequency_hz": ARRAY,
            "time_s": ARRAY,
            "peak_hz": {"type": ["number", "null"]},
            "resolution_hz": N,
            "unit": S,
        },
        {"x": tone, "fs": 64, "nperseg": 64, "hop": 32},
        {"peak_hz": 8, "resolution_hz": 1},
        "Hann short-time Fourier power density with complete frames and explicit resolution.",
        [
            "Uniform sampling; no padding or detrending. Window length trades temporal and spectral resolution.",
            "Density units are input units squared/Hz; visual ridges are not significance tests.",
        ],
    ),
    (
        "morlet-wavelet",
        "morlet_cwt",
        "signal-processing",
        "spectral.wavelet",
        {"x": ARRAY, "fs": fs, "frequencies_hz": ARRAY, "omega0": num(6, minimum=5, maximum=12)},
        ["x", "fs", "frequencies_hz"],
        {
            "coefficients": ART,
            "edge_valid": ART,
            "dominant_hz": {"type": ["number", "null"]},
            "frequency_hz": ARRAY,
            "unit": S,
        },
        {"x": tone * 4, "fs": 64, "frequencies_hz": [4, 8, 12]},
        {"dominant_hz": 8},
        "Corrected complex Morlet multiscale analysis with explicit edge mask.",
        [
            "Coefficients use discrete L2 normalization, not a PSD. Frequencies are nominal centers.",
            "Zero extension biases edges; mask excludes sqrt(2) scales. Reject frequencies above fs/4.",
        ],
    ),
    (
        "phase-locking",
        "phase_locking",
        "resonance",
        "resonance.phase-locking",
        {"phases_rad": MATRIX},
        None,
        {"plv": MATRIX, "mean_order": N, "unit": S},
        {"phases_rad": [[i * 0.1, i * 0.1] for i in range(64)]},
        {"plv": [[1, 1], [1, 1]], "mean_order": 1},
        "Pairwise temporal phase-locking values and instantaneous Kuramoto order.",
        [
            "Requires meaningful input phases in radians. No phase extraction from arbitrary broadband signals.",
            "PLV is biased with finite samples and autocorrelation; common drive and identical uncoupled frequencies give high PLV.",
        ],
    ),
    (
        "kuramoto-network",
        "kuramoto",
        "dynamical-systems",
        "resonance.kuramoto",
        {
            "omega_rad_s": ARRAY,
            "theta0_rad": ARRAY,
            "coupling": num(minimum=0),
            "dt": num(exclusiveMinimum=0),
            "steps": integer(minimum=1, maximum=100000),
            "diffusion": num(0, minimum=0),
            "phase_lag": num(0),
        },
        ["omega_rad_s", "theta0_rad", "coupling", "dt", "steps"],
        {"phases": ART, "end_order": N, "final_phases_rad": ARRAY, "unit": S},
        {"omega_rad_s": [1, 1], "theta0_rad": [0, 0], "coupling": 2, "dt": 0.01, "steps": 100},
        {"end_order": 1, "final_phases_rad": [1, 1]},
        "Globally coupled phase oscillators with RK4 or additive-noise Euler-Maruyama integration.",
        [
            "All-to-all K/N coupling excluding self; frequencies and K in rad/s, diffusion in rad squared/s.",
            "No amplitude dynamics, delays or inferred causal coupling. Finite populations and time windows cannot establish a thermodynamic transition.",
            "Stochastic convergence requires coupled Wiener increments; fixed seed alone is not a convergence test.",
        ],
    ),
    (
        "adaptive-filter",
        "lms",
        "signal-processing",
        "signal.adaptive-filter",
        {
            "reference": ARRAY,
            "desired": ARRAY,
            "taps": integer(minimum=1, maximum=1024),
            "step_size": num(exclusiveMinimum=0, exclusiveMaximum=2),
            "normalized": {"type": "boolean", "default": False},
        },
        ["reference", "desired", "taps", "step_size"],
        {
            "coefficients": {"type": "array", "items": N},
            "mse": N,
            "prediction": ART,
            "errors": ART,
            "unit": S,
        },
        {"reference": [1] * 200, "desired": [2] * 200, "taps": 1, "step_size": 0.1},
        {"coefficients": [2]},
        "Causal LMS and normalized LMS adaptive filtering with recorded residuals.",
        [
            "Plain LMS stability depends on input covariance and step size; correlated references can remove desired signal.",
            "Weights are estimates, not calibrated uncertainties. Divergence is an explicit error.",
        ],
    ),
    (
        "fir-identification",
        "identify_fir",
        "dynamical-systems",
        "dynamics.system-identification",
        {"reference": ARRAY, "response": ARRAY, "taps": integer(minimum=1, maximum=1024)},
        None,
        {
            "coefficients": {"type": "array", "items": N},
            "covariance": MATRIX,
            "residual_variance": N,
            "condition_number": N,
            "residuals": ART,
            "dof": INTEGER,
            "unit": S,
        },
        {"reference": fir_input, "response": fir_output, "taps": 3},
        {"coefficients": [0.7, -0.2, 0.1], "residual_variance": 0},
        "Least-squares FIR system identification, residual diagnostics and conditional covariance.",
        [
            "Linear time-invariant causal FIR, persistently exciting noise-free input; IID response residuals for covariance.",
            "Rank deficiency and condition number >1e10 are rejected; errors in variables and colored residuals invalidate covariance.",
        ],
    ),
    (
        "plate-eigenmode",
        "plate_mode",
        "computational-physics",
        "resonance.plate-mode",
        {
            "m": integer(minimum=1),
            "n": integer(minimum=1),
            "a_m": num(1, exclusiveMinimum=0),
            "b_m": num(1, exclusiveMinimum=0),
            "thickness_m": num(0.001, exclusiveMinimum=0),
            "young_pa": num(2e11, exclusiveMinimum=0),
            "density_kg_m3": num(7800, exclusiveMinimum=0),
            "poisson": num(0.3, exclusiveMinimum=-1, exclusiveMaximum=0.5),
            "grid": integer(65, minimum=8, maximum=512),
        },
        ["m", "n"],
        {"x_m": ARRAY, "y_m": ARRAY, "displacement": ART, "frequency_hz": N, "rigidity_nm": N, "unit": S},
        {"m": 1, "n": 1},
        {"frequency_hz": math.pi * 0.001 * math.sqrt(2e11 / (12 * 7800 * (1 - 0.3**2)))},
        "Simply supported rectangular thin-plate eigenmodes with material-derived frequencies.",
        [
            "Kirchhoff-Love thin, homogeneous isotropic plate; small displacement, simply supported edges.",
            "Not free-edge Chladni plates, fluid cymatics, granular transport, damping or nonlinear response. Nodal plots alone do not validate those phenomena.",
        ],
    ),
    (
        "cross-spectral",
        "cross_spectrum",
        "signal-processing",
        "spectral.multichannel",
        {"channels": MATRIX, "fs": fs, "nperseg": integer(128, minimum=8)},
        ["channels", "fs"],
        {
            "cross_psd": ART,
            "coherence": ART,
            "undefined_bins": ART,
            "frequency_hz": ARRAY,
            "peak_hz": N,
            "peak_coherence": N,
            "segments": INTEGER,
            "unit": S,
        },
        {"channels": [[x, x] for x in tone], "fs": 64, "nperseg": 64},
        {"peak_hz": 8, "peak_coherence": 1, "segments": 7},
        "Welch multichannel cross PSD and magnitude-squared coherence with undefined-bin mask.",
        [
            "Stationary uniformly sampled channels and >=3 segments; coherence has finite-sample bias.",
            "CSD convention conj(X)*Y. Common drive and leakage are not causal interaction; zero-power bins are explicitly undefined.",
        ],
    ),
]


def main():
    for name, method, domain, cap, props, required, outputs, example, expected, summary, limits in specs:
        path = ROOT / "skills" / domain / name
        (path / "examples").mkdir(parents=True, exist_ok=True)
        manifest = {
            "schema": "atlas.skill/v1",
            "name": name,
            "version": "1.0.0",
            "kind": "executable",
            "domain": domain,
            "summary": summary,
            "capabilities": [cap],
            "entrypoint": "run.py",
            "determinism": "seeded" if method == "kuramoto" else "deterministic",
            "inputs": schema(props, required),
            "outputs": schema(outputs),
            "permissions": {"network": False, "subprocess": False, "read": ["inputs"], "write": ["outputs"]},
            "limits": {"timeout_s": 120, "memory_mb": 1024},
            "requires": {
                "python": ">=3.11",
                "packages": {"numpy": ">=2.0", "scipy": ">=1.13", "rain-atlas": ">=0.1"},
            },
            "examples": [{"name": "analytical", "seed": 17, "tolerance": {"abs": 1e-6, "rel": 1e-6}}],
            "references": ["docs/RESONANCE.md"],
            "limitations": limits,
        }
        for file, data in [
            ("skill.json", manifest),
            ("examples/analytical.input.json", example),
            ("examples/analytical.expected.json", expected),
        ]:
            (path / file).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
        (path / "run.py").write_text(
            f'from rain_atlas.science.skill_api import run_method\n\n\ndef run(inputs, ctx):\n    return run_method("{method}", inputs, ctx)\n',
            encoding="utf-8",
            newline="\n",
        )
        (path / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {summary} Use for reproducible numerical studies.\nlicense: MIT\n---\n\n# {name}\n\n{summary}\n\nInputs and outputs are typed in `skill.json`. Run the analytical example with\n`atlas skills test {name}`. Precision and convergence tests are in\n`tests/test_resonance.py`; methods, units and independent references are in\n`docs/RESONANCE.md`. Arrays are reproducible artifacts with SHA-256 digests.\n\n## Assumptions and failure conditions\n\n"
            + "\n".join("- " + x for x in limits)
            + "\n\nNo calibrated uncertainty or empirical validation is implied by a plot.\n",
            encoding="utf-8",
            newline="\n",
        )


if __name__ == "__main__":
    main()
