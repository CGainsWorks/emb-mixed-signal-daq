"""The SPICE decks and the KiCad schematic, parsed back and checked."""

import math
import re
from collections import defaultdict

import pytest

from conftest import ROOT
from daqmodel import kicad, spice
from daqmodel.frontend import FRONT_END, netlist
from daqmodel.spec import GAINS, K_BOLTZMANN, TEMPERATURE_K


@pytest.mark.parametrize("gain", GAINS)
def test_deck_contains_every_netlist_part(gain):
    deck = spice.deck(gain)
    for p in netlist(gain):
        assert re.search(rf"^{p.ref} {p.nets[0]} {p.nets[1]} ", deck, re.M) or \
            p.kind == "OPAMP", p.ref
    for t in spice.LTSPICE_ONLY:
        assert t not in deck


def test_noise_generators_have_the_allowance_values():
    deck = spice.deck(8)
    r_en = float(re.search(r"^RNVU1A \S+ \S+ (\S+)", deck, re.M).group(1))
    assert math.sqrt(4 * K_BOLTZMANN * TEMPERATURE_K * r_en) == pytest.approx(FRONT_END.en_amp, rel=1e-5)
    gm = float(re.search(r"^GNIU1A \S+ \S+ \S+ \S+ (\S+)", deck, re.M).group(1))
    i_n = gm * math.sqrt(4 * K_BOLTZMANN * TEMPERATURE_K * 1e3)
    assert i_n == pytest.approx(FRONT_END.in_amp, rel=1e-5)


# ---------------------------------------------------------------- KiCad

def sexpr(text):
    """A minimal S-expression reader: nested lists of atoms and strings."""
    tokens = re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', text)
    stack = [[]]
    for t in tokens:
        if t == "(":
            stack.append([])
        elif t == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(t[1:-1] if t.startswith('"') else t)
    assert len(stack) == 1
    return stack[0][0]


def find(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


@pytest.fixture(scope="module")
def sheet():
    text = (ROOT / "hardware/kicad/daq_frontend.kicad_sch").read_text(encoding="utf-8")
    assert text.count("(") == text.count(")")
    return sexpr(text)


def connectivity(sheet):
    """Rebuild {(ref, pin): net} from geometry alone."""
    libs = {}
    for s in find(find(sheet, "lib_symbols")[0], "symbol"):
        pins = {}
        for unit in find(s, "symbol"):
            for p in find(unit, "pin"):
                at = find(p, "at")[0]
                num = find(p, "number")[0][1]
                pins[num] = (float(at[1]), float(at[2]))
        libs[s[1]] = pins
    label_at = {}
    for lab in find(sheet, "label"):
        at = find(lab, "at")[0]
        label_at[(round(float(at[1]), 3), round(float(at[2]), 3))] = lab[1]
    wires = {}
    for w in find(sheet, "wire"):
        a, b = find(w, "pts")[0][1:]
        pa = (round(float(a[1]), 3), round(float(a[2]), 3))
        pb = (round(float(b[1]), 3), round(float(b[2]), 3))
        wires[pa] = pb
    nets = {}
    for s in find(sheet, "symbol"):
        lib = find(s, "lib_id")[0][1]
        at = find(s, "at")[0]
        x, y = float(at[1]), float(at[2])
        ref = next(p[2] for p in find(s, "property") if p[1] == "Reference")
        for num, (px, py) in libs[lib].items():
            pin_pt = (round(x + px, 3), round(y - py, 3))
            end = wires[pin_pt]
            nets[(ref, num)] = label_at[end]
    return nets


def test_schematic_connectivity_matches_its_parts(sheet):
    nets = connectivity(sheet)
    expect = {(p.ref, n): net for p in kicad.board_parts() for n, net in p.nets.items()}
    assert nets == expect


def test_every_net_joins_at_least_two_pins(sheet):
    count = defaultdict(int)
    for net in connectivity(sheet).values():
        count[net] += 1
    assert {n: c for n, c in count.items() if c < 2} == {}


def test_schematic_matches_the_simulated_circuit(sheet):
    """Every part the deck simulates is on the board with the same value and
    the same nets, apart from the three stated differences: the sensor is
    off board, R_G is three resistors behind a multiplexer and the input
    selector sits between the connector and the protection resistors. SPICE
    node 0 is the board's AGND."""
    nets = connectivity(sheet)
    values = {p.ref: p.value for p in kicad.board_parts()}
    for g in GAINS:
        for p in netlist(g):
            if p.ref in ("VSIG", "R1", "R2"):
                continue
            if p.kind == "OPAMP":
                assert (nets[(p.ref, "3")], nets[(p.ref, "2")], nets[(p.ref, "1")]) == p.nets
                continue
            if p.ref == "R7":
                match = [r for r, v in values.items() if r.startswith("R7")
                         and v == kicad._ohms(p.value)]
                assert len(match) == 1
                r = match[0]
                assert nets[(r, "1")] == p.nets[0]
                mux_pin = {"A": "1", "B": "2", "C": "3"}[r[-1]]
                assert nets[("U4", mux_pin)] == nets[(r, "2")]
                assert nets[("U4", "5")] == p.nets[1]
                continue
            want = kicad._ohms(p.value) if p.kind == "R" else kicad._farads(p.value)
            assert values[p.ref] == want, p.ref
            spice_nets = tuple("AGND" if n == "0" else n for n in p.nets)
            assert (nets[(p.ref, "1")], nets[(p.ref, "2")]) == spice_nets, p.ref


def test_uuids_are_unique(sheet):
    text = (ROOT / "hardware/kicad/daq_frontend.kicad_sch").read_text()
    ids = re.findall(r'\(uuid "([0-9a-f-]+)"\)', text)
    assert len(ids) == len(set(ids))


def test_no_pin_or_label_touches_anything_but_its_own_stub(sheet):
    """KiCad joins anything that touches. A label or pin of one part landing
    on a wire of another would merge two nets without either appearing in
    the connectivity above, so check the geometry directly."""
    wires = []
    for w in find(sheet, "wire"):
        a, b = find(w, "pts")[0][1:]
        wires.append(((float(a[1]), float(a[2])), (float(b[1]), float(b[2]))))

    def on(seg, pt):
        (x0, y0), (x1, y1) = seg
        x, y = pt
        if abs((x1 - x0) * (y - y0) - (y1 - y0) * (x - x0)) > 1e-6:
            return False
        return min(x0, x1) - 1e-6 <= x <= max(x0, x1) + 1e-6 and \
            min(y0, y1) - 1e-6 <= y <= max(y0, y1) + 1e-6

    points = [w[0] for w in wires] + [w[1] for w in wires]
    for pt in points:
        touching = [w for w in wires if on(w, pt)]
        assert len(touching) == 1, f"{pt} touches {len(touching)} wires"


def test_parts_sit_on_the_connection_grid(sheet):
    for w in find(sheet, "wire"):
        for p in find(w, "pts")[0][1:]:
            for v in (float(p[1]), float(p[2])):
                assert abs(v / 1.27 - round(v / 1.27)) < 1e-6, v


def test_committed_schematic_exports_are_current():
    """The PDF, SVG and ERC report are made by `make schematic` in a KiCad
    container, not in CI. The hash says which schematic they came from."""
    import hashlib
    sch = (ROOT / "hardware/kicad/daq_frontend.kicad_sch").read_bytes()
    recorded = (ROOT / "hardware/outputs/schematic.sha256").read_text().split()[0]
    assert hashlib.sha256(sch).hexdigest() == recorded, "run `make schematic`"
    erc = (ROOT / "hardware/outputs/erc.rpt").read_text()
    assert "ERC messages: 0  Errors 0  Warnings 0" in erc
