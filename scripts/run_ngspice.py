#!/usr/bin/env python3
"""Cross-check the noise budget against ngspice.

Runs each committed deck in hardware/spice through ngspice in batch mode and
compares, at every gain:

1. Noise density at the converter pins, point by point over 1 Hz to 10 MHz,
   against the budget's closed form sum of the same contributors.
2. The noise integrated through the sinc4 decimator, which is the number the
   specification is written in.
3. The signal transfer function |V(ainp) - V(ainm)| from the AC analysis,
   against the budget's gain and filter poles.

The budget and the deck share nothing but the component values: the budget
is hand written transfer functions, the deck is solved by ngspice's own
modified nodal analysis with its own resistor noise models. Agreement to
better than 0.1 percent is required; the observed figure is printed and
written to test-results/noise-floor/ngspice_crosscheck.csv.

    python scripts/run_ngspice.py [--skip-missing]
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))

from daqmodel import noise_budget as nb  # noqa: E402
from daqmodel.frontend import FRONT_END  # noqa: E402
from daqmodel.io import write_csv  # noqa: E402
from daqmodel.spec import GAINS  # noqa: E402
from daqmodel.spice import LTSPICE_ONLY, read_wrdata  # noqa: E402

TOLERANCE = 1e-4


def interp_loglog(f_src, y_src, f):
    return np.exp(np.interp(np.log(f), np.log(f_src), np.log(y_src)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-missing", action="store_true",
                    help="exit 0 with a message if ngspice is not installed")
    a = ap.parse_args()
    exe = shutil.which("ngspice")
    if exe is None:
        print("ngspice not found" + ("; skipping" if a.skip_missing else ""))
        return 0 if a.skip_missing else 1

    rows, worst = [], 0.0
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / "spice-out").mkdir()
        for g in GAINS:
            deck = ROOT / "hardware" / "spice" / f"frontend_g{g}.cir"
            text = deck.read_text()
            bad = [t for t in LTSPICE_ONLY if t in text]
            if bad:
                raise SystemExit(f"{deck.name}: LTspice-only syntax {bad}")
            shutil.copy(deck, work / deck.name)
            r = subprocess.run([exe, "-b", deck.name], cwd=work, capture_output=True, text=True)
            if r.returncode != 0:
                print(r.stdout, r.stderr, file=sys.stderr)
                raise SystemExit(f"ngspice failed on {deck.name}")

            f, onoise = read_wrdata(work / "spice-out" / f"noise_g{g}.dat")
            f_ac, mag = read_wrdata(work / "spice-out" / f"ac_g{g}.dat")

            # 1. density, point by point
            ref = np.sqrt(nb.analogue_psd(g, f))
            dens_err = float(np.max(np.abs(onoise / ref - 1)))

            # 2. integrated through the decimator, on the budget's own grid
            # restricted to the range ngspice swept
            grid = nb.integration_grid()
            grid = grid[(grid >= f[0]) & (grid <= f[-1])]
            var_sp = nb.integrate(interp_loglog(f, onoise, grid) ** 2, grid)
            var_py = nb.integrate(nb.analogue_psd(g, grid), grid)
            gain = FRONT_END.gain(g)
            v_sp, v_py = math.sqrt(var_sp) / gain, math.sqrt(var_py) / gain
            int_err = abs(v_sp / v_py - 1)

            # 3. signal transfer
            h = np.abs(gain * nb.rc_diff(f_ac, FRONT_END.r_leg, FRONT_END.c_cm, FRONT_END.c_diff)
                       * nb.rc_diff(f_ac, FRONT_END.r_aa, FRONT_END.c_aa_cm, FRONT_END.c_aa_diff))
            ac_err = float(np.max(np.abs(mag / h - 1)))

            worst = max(worst, dens_err, int_err, ac_err)
            rows.append([g, f"{onoise[0] * 1e9:.4f}", f"{ref[0] * 1e9:.4f}",
                         f"{v_sp * 1e9:.3f}", f"{v_py * 1e9:.3f}",
                         f"{dens_err:.2e}", f"{int_err:.2e}", f"{ac_err:.2e}"])
            print(f"gain {g:3d}: density at 1 Hz {onoise[0] * 1e9:.3f} nV/rtHz "
                  f"(budget {ref[0] * 1e9:.3f}); integrated {v_sp * 1e9:.2f} nV rms "
                  f"input referred (budget {v_py * 1e9:.2f}); worst deviation: "
                  f"density {dens_err:.1e}, integrated {int_err:.1e}, transfer {ac_err:.1e}")

    write_csv("test-results/noise-floor/ngspice_crosscheck.csv",
              ["gain", "ngspice_out_nV_rtHz_1Hz", "budget_out_nV_rtHz_1Hz",
               "ngspice_in_nV_rms", "budget_in_nV_rms", "max_density_rel_dev",
               "integrated_rel_dev", "max_transfer_rel_dev"], rows)
    if worst > TOLERANCE:
        print(f"FAILED: worst relative deviation {worst:.2e} > {TOLERANCE:g}", file=sys.stderr)
        return 1
    print(f"ngspice agrees with the noise budget: worst relative deviation {worst:.1e} "
          f"(limit {TOLERANCE:g})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
