# Test results (simulated)

**Everything in this folder is a simulation.** No board exists. The files
are produced by `scripts/run_all.py`, `scripts/run_fil.py` and
`scripts/run_ngspice.py`. CI regenerates them on every push and fails if
they differ from what is committed.

| Folder | What | Produced by |
|---|---|---|
| [noise-floor](noise-floor) | Noise budget by contributor and gain, the shorted input noise floor of the simulated board, the ngspice cross-check | `run_all.py`, `run_ngspice.py` |
| [enob-snr](enob-snr) | Coherent sine tests at gain 1 and 128: SNR, THD, SFDR, SINAD, ENOB, IEEE 1241 methods | `run_all.py` |
| [linearity](linearity) | 41 point DC sweep, best fit and end point INL | `run_all.py` |
| [calibration](calibration) | Coefficients per gain, validation against the simulated DMM, the firmware in the loop comparison | `run_all.py`, `run_fil.py` |
| [headline.json](headline.json) | The numbers the README quotes | `run_all.py` |

The method behind each figure is in
[docs/validation_report.md](../docs/validation_report.md).
