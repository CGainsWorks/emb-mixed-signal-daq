"""Figures for the test results. Every one is labelled as simulated."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from . import noise_budget as nb  # noqa: E402
from .io import ROOT  # noqa: E402
from .spec import SPEC  # noqa: E402

SIM = "simulated"
plt.rcParams.update({"figure.dpi": 110, "font.size": 9, "axes.grid": True,
                     "grid.alpha": 0.3, "savefig.bbox": "tight"})


def _save(fig, rel):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(p, metadata={"Software": None})
    plt.close(fig)


def budget_psd(gains=(1, 128)):
    f = np.logspace(0, np.log10(SPEC.converter.f_mod * 2), 600)
    fig, axes = plt.subplots(1, len(gains), figsize=(5.2 * len(gains), 3.8), sharey=True)
    for ax, g in zip(axes, gains):
        gain = nb.FRONT_END.gain(g)
        total = np.zeros_like(f)
        for line in nb.lines(g):
            psd = line.psd_fn(f)
            total += psd
            ax.loglog(f, np.sqrt(psd) / gain * 1e9, lw=1, label=line.name.split(",")[0])
        ax.loglog(f, np.sqrt(total) / gain * 1e9, "k", lw=2, label="Total")
        w = nb.sinc_magnitude(f)
        ax2 = ax.twinx()
        ax2.semilogx(f, 20 * np.log10(np.maximum(w, 1e-12)), color="0.6", ls=":", lw=1)
        ax2.set_ylim(-160, 10)
        ax2.set_ylabel("sinc4 response (dB, dotted)", color="0.4")
        ax2.grid(False)
        ax.set_title(f"Gain {g}: input referred noise density (budget)")
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylim(0.01, 100)
    axes[0].set_ylabel("nV/rtHz, referred to the input")
    axes[0].legend(fontsize=7, loc="lower left")
    _save(fig, "test-results/noise-floor/budget_psd.png")


def budget_shares(budgets):
    fig, ax = plt.subplots(figsize=(8, 3.2))
    names = [r[0].split(",")[0] for r in budgets[0].rows]
    left = np.zeros(len(budgets))
    labels = [f"G={b.gain_nominal}" for b in budgets]
    for i, name in enumerate(names):
        share = np.array([b.rows[i][5] * 100 for b in budgets])
        ax.barh(labels, share, left=left, label=name)
        left += share
    ax.set_xlabel("Share of total noise power (%)")
    ax.set_title("Where the noise comes from, by gain (budget)")
    ax.legend(fontsize=7, bbox_to_anchor=(1.01, 1), loc="upper left")
    _save(fig, "test-results/noise-floor/budget_shares.png")


def noise_histograms(results):
    fig, axes = plt.subplots(1, len(results), figsize=(4 * len(results), 3))
    for ax, r in zip(axes, results):
        v = (r.codes - r.codes.mean()) * SPEC.converter.lsb / r.gain * 1e6
        ax.hist(v, bins=40, color="C0")
        ax.set_title(f"G={r.gain}: {r.floor.rms * 1e6:.3f} uV rms ({SIM})")
        ax.set_xlabel("Input referred (uV)")
    _save(fig, "test-results/noise-floor/histograms.png")


def spectra(sines):
    fig, axes = plt.subplots(len(sines), 1, figsize=(8, 3 * len(sines)))
    for ax, s in zip(np.atleast_1d(axes), sines):
        fs = SPEC.full_scale(s.gain)
        x = s.volts - s.volts.mean()
        spec = np.abs(np.fft.rfft(x)) * 2 / len(x)
        f = np.arange(len(spec)) * SPEC.converter.odr / len(x)
        ax.plot(f, 20 * np.log10(np.maximum(spec / fs, 1e-12)), lw=0.7)
        ax.set_xlim(0, SPEC.converter.odr / 2)
        ax.set_ylim(-200, 5)
        ax.set_ylabel("dBFS")
        ax.set_title(f"G={s.gain}, {s.f_hz:.2f} Hz at {s.m.level_dbfs:.2f} dBFS: "
                     f"SNR {s.m.snr_db:.1f} dB, THD {s.m.thd_db:.1f} dB, "
                     f"ENOB {s.m.enob_sinad:.2f} ({SIM})")
    np.atleast_1d(axes)[-1].set_xlabel("Frequency (Hz)")
    _save(fig, "test-results/enob-snr/spectra.png")


def inl(lin):
    fig, ax = plt.subplots(figsize=(7, 3.2))
    fs = SPEC.full_scale(lin.gain)
    ax.plot(lin.applied / fs, lin.lin.inl_best_fit_ppm, "o-", ms=3,
            label=f"measured from the sweep ({SIM})")
    ax.set_xlabel("Input (fraction of full scale)")
    ax.set_ylabel("INL (ppm of FSR)")
    ax.set_title(f"G={lin.gain}: best fit INL, peak {lin.lin.max_best_fit_ppm:.2f} ppm "
                 f"(model was given {lin.injected_max_ppm:.2f} ppm)")
    ax.legend()
    _save(fig, "test-results/linearity/inl.png")


def calibration(cals):
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.4))
    for c in cals:
        fsr = SPEC.fsr(c.gain)
        fs = SPEC.full_scale(c.gain)
        x = [p.nominal_v / fs for p in c.points]
        axes[0].plot(x, [(p.raw_v - p.dmm_v) / fsr * 1e6 for p in c.points], "o-", ms=3,
                     label=f"G={c.gain}")
        axes[1].plot(x, [(p.cal_v - p.dmm_v) / fsr * 1e6 for p in c.points], "o-", ms=3,
                     label=f"G={c.gain}")
    axes[0].set_title(f"Before calibration, against the DMM ({SIM})")
    axes[1].set_title(f"After calibration, against the DMM ({SIM})")
    for ax in axes:
        ax.set_xlabel("Input (fraction of full scale)")
        ax.set_ylabel("Error (ppm of FSR)")
        ax.legend(fontsize=7)
    axes[1].axhspan(-SPEC.calibrated_error_target_ppm_fsr,
                    SPEC.calibrated_error_target_ppm_fsr, color="C2", alpha=0.12)
    _save(fig, "test-results/calibration/errors.png")
