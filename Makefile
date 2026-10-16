# Everything this repository produces comes from `make demo`.
PY ?= python

.DEFAULT_GOAL := help
.PHONY: help setup demo test firmware fil spice check ci clean schematic

help:
	@echo "make setup     install the Python dependencies"
	@echo "make demo      regenerate every result, document, deck and schematic, then"
	@echo "               run the firmware in the loop (needs gcc)"
	@echo "make test      Python tests and the firmware unit tests"
	@echo "make spice     cross-check the noise budget in ngspice, if installed"
	@echo "make check     confirm the committed results match a fresh run"
	@echo "make ci        everything the GitHub Actions job does, locally"
	@echo "make schematic rerun ERC and export the schematic PDF and SVG (needs Docker)"
	@echo "make clean     remove build products"

setup:
	$(PY) -m pip install -r requirements.txt

demo:
	$(PY) scripts/run_all.py
	$(MAKE) fil

firmware:
	$(MAKE) -C firmware test sim

fil: firmware
	$(PY) scripts/run_fil.py

test: firmware
	$(PY) -m pytest tests -q

spice:
	$(PY) scripts/run_ngspice.py --skip-missing

# The comparison is against HEAD, so after changing the model the order is:
# make demo, commit, then make check.
check:
	$(PY) scripts/check_outputs_current.py

# The same steps, in the same order, as .github/workflows/ci.yml.
ci:
	$(PY) scripts/run_all.py
	$(MAKE) -C firmware test sim
	$(PY) scripts/run_fil.py
	$(PY) scripts/run_ngspice.py
	$(PY) -m pytest tests -q
	$(PY) scripts/check_outputs_current.py

# KiCad is far too large to install on every CI run, so the ERC report and
# the PDF and SVG exports are committed and refreshed here, with the hash of
# the schematic they were made from. tests/test_hardware_files.py fails if
# the schematic changes without this being rerun.
KICAD_IMAGE ?= kicad/kicad:8.0
schematic:
	docker run --rm -u root -v "$(CURDIR)/hardware:/hw" -w /hw/kicad $(KICAD_IMAGE) sh -c "\
		kicad-cli sch erc --exit-code-violations -o /hw/outputs/erc.rpt daq_frontend.kicad_sch && \
		kicad-cli sch export pdf -o /hw/outputs/schematic.pdf daq_frontend.kicad_sch && \
		kicad-cli sch export svg -o /hw/outputs daq_frontend.kicad_sch && \
		sha256sum daq_frontend.kicad_sch > /hw/outputs/schematic.sha256"

clean:
	rm -rf build firmware/build .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
