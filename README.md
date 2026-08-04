# emb-mixed-signal-daq

> **Status: planned. This repository is a brief, not an implementation.**
> Nothing here is built yet. The sections below define what goes in it.

A precision acquisition board where the analogue design is the point: grounding strategy, filtering, controlled-impedance routing and a documented noise budget, validated by measured ENOB and SNR against a precision reference.

---

## What this covers

CV entries this repository is the evidence for:

- Mixed-Signal Data-Acquisition Board

---

## Requirements

### Hardware

- Low-noise analogue front end
- 24-bit ADC
- STM32 or ARM Cortex-M
- Precision voltage reference
- Shielding
- Test gear: precision source, reference DMM, spectrum analyser

### Software

- C firmware over SPI and I2C
- Driver and sampling engine
- Calibration routine
- Host-side capture tool
- Noise analysis scripts

### Report and documentation deliverables

- Schematic and grounding strategy
- Noise budget
- Measured ENOB and SNR
- Controlled-impedance routing notes
- Calibration procedure and results against reference instruments

---

## Inputs

- Analogue signal under test
- Sample rate and gain configuration
- Calibration reference values
- Reference voltage specification

## Outputs

- Calibrated digital samples over SPI or a host link
- Calibration coefficients
- Noise floor and ENOB measurements
- Captured datasets
- Calibration report

---

## Intended structure

```
hardware/
  kicad/ or altium/
  outputs/              gerbers, bom, schematic.pdf, 3d/
  docs/                 grounding_strategy.md, noise_budget.md,
                        impedance_routing.md
firmware/
  src/                  adc_spi, sampling_engine, calibration, host_link
  include/
  test/
host-tools/             capture tool, noise analysis scripts
test-results/
  noise-floor/
  enob-snr/
  linearity/
  calibration/
docs/                   spec.md, calibration_procedure.md,
                        validation_report.md
```

Plus the standard baseline: `README.md`, `LICENSE`, `.gitignore`, `.gitattributes`
(Git LFS rules for weights, bags and media), `.github/workflows/ci.yml`, `docs/`,
`scripts/setup.sh`, `scripts/run_demo.sh` and `tests/`.

---

## Build checklist

- [ ] Written specification: bandwidth, resolution, noise target
- [ ] Noise budget calculation before design
- [ ] Analogue front end design
- [ ] Schematic capture
- [ ] Layout with grounding strategy and controlled-impedance routing
- [ ] Fabrication and assembly
- [ ] ADC SPI driver and sampling engine
- [ ] First captures and sanity checks
- [ ] Noise floor measurement
- [ ] ENOB and SNR measurement
- [ ] Linearity measurement
- [ ] Calibration routine and coefficients
- [ ] Validation against a reference DMM
- [ ] Host capture tool
- [ ] Validation report

---

## Definition of done

This repository is finished when:

- [ ] The whole thing runs from one command on a clean machine.
- [ ] The README opens with a diagram or a GIF, not a wall of text.
- [ ] Every number quoted in the README is reproducible from a script in the repo.
- [ ] Limitations are stated honestly in their own section.
- [ ] A licence is declared.
- [ ] Large binaries live in Releases or LFS, not in the Git history.
- [ ] The repository URL is added to the matching CV bullet point.

---

## Starter prompt

Paste this into your coding agent of choice to begin.

<details>
<summary>Expand</summary>

```
You are helping me build a portfolio project from scratch. Read this brief and then
propose a concrete implementation plan before writing any code.

PROJECT: emb-mixed-signal-daq
A precision acquisition board where the analogue design is the point: grounding strategy, filtering, controlled-impedance routing and a documented noise budget, validated by measured ENOB and SNR against a precision reference.

TARGET STACK
- C firmware over SPI and I2C
- Driver and sampling engine
- Calibration routine
- Host-side capture tool
- Noise analysis scripts

HARDWARE CONTEXT
- Low-noise analogue front end
- 24-bit ADC
- STM32 or ARM Cortex-M
- Precision voltage reference
- Shielding
- Test gear: precision source, reference DMM, spectrum analyser

THE SYSTEM MUST TAKE THESE INPUTS
- Analogue signal under test
- Sample rate and gain configuration
- Calibration reference values
- Reference voltage specification

AND PRODUCE THESE OUTPUTS
- Calibrated digital samples over SPI or a host link
- Calibration coefficients
- Noise floor and ENOB measurements
- Captured datasets
- Calibration report

INTENDED REPOSITORY LAYOUT
hardware/
  kicad/ or altium/
  outputs/              gerbers, bom, schematic.pdf, 3d/
  docs/                 grounding_strategy.md, noise_budget.md,
                        impedance_routing.md
firmware/
  src/                  adc_spi, sampling_engine, calibration, host_link
  include/
  test/
host-tools/             capture tool, noise analysis scripts
test-results/
  noise-floor/
  enob-snr/
  linearity/
  calibration/
docs/                   spec.md, calibration_procedure.md,
                        validation_report.md

CONSTRAINTS
- Everything must run from a single command: `docker compose up` or `make demo`.
- No placeholder or stub code presented as working. If something is not implemented, say so.
- Every quantitative claim in the README must be reproducible from a script in this repo.
- Use only public or synthetic data. Record the licence of every dataset used.


START BY
1. Confirming or challenging the proposed repository layout.
2. Listing the specific libraries and versions you intend to pin.
3. Identifying the single riskiest technical unknown and how to de-risk it first.
Then work through the milestones in the README build checklist, one at a time.

```

</details>

---

## Notes

- Do not backdate commits to match CV dates. Publishing older work today is normal and expected.
- Record dataset licences before training on anything. Several common research datasets are
  non-commercial only.
- Flip this repository to public once there is something in it worth showing.
