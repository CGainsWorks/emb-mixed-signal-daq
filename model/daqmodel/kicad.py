"""KiCad schematic of the front end, generated from the same netlist.

The schematic is drawn in the label style: every pin has a short wire stub
ending in a net label; KiCad joins pins whose labels share a name. It
reads less like a hand drawn page than a routed schematic does; it can be
generated exactly and checked mechanically, which matters more here: the
test suite parses the file back and rebuilds the connectivity from the pin
geometry, the wires and the labels. It then compares that with the netlist
the SPICE deck is simulated from.

The schematic is the board, not the simulation, so it differs from the deck
in three stated ways: the sensor resistances are off board, the gain
resistor is one of three behind an analogue multiplexer (U4); the input
pair passes through an input selector (U5) that the calibration routine uses
to short the input or connect the reference.

Written for KiCad 8 (file format 20231120). It has not been opened in KiCad
on the machine it was generated on; see STATUS.md.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

from .frontend import FRONT_END, R_G_E96, FrontEnd

GRID = 2.54
STUB = 2 * GRID
NS = uuid.UUID("6f1c2d6e-3b8a-4c55-9a51-1d2b7c0e9a40")


def uid(*parts) -> str:
    """Deterministic UUIDs, so regenerating gives an identical file."""
    return str(uuid.uuid5(NS, "/".join(str(p) for p in parts)))


def fmt(x: float) -> str:
    s = f"{x:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


# ---------------------------------------------------------------- symbols

@dataclass(frozen=True)
class Pin:
    number: str
    name: str
    x: float          # symbol coordinates, y up
    y: float
    angle: int        # direction from the connection point into the body
    etype: str = "passive"


@dataclass(frozen=True)
class SymbolDef:
    name: str
    prefix: str
    pins: tuple
    body: str         # graphics, already formatted


def _font():
    return "(effects (font (size 1.27 1.27)))"


def two_pin(name: str, prefix: str, body: str) -> SymbolDef:
    return SymbolDef(name, prefix, (Pin("1", "~", 0, 3.81, 270),
                                    Pin("2", "~", 0, -3.81, 90)), body)


R_SYM = two_pin("R", "R", "(rectangle (start -1.016 -2.54) (end 1.016 2.54) "
                "(stroke (width 0.254) (type default)) (fill (type none)))")
C_SYM = two_pin("C", "C", "(polyline (pts (xy -2.032 -0.762) (xy 2.032 -0.762)) "
                "(stroke (width 0.508) (type default)) (fill (type none))) "
                "(polyline (pts (xy -2.032 0.762) (xy 2.032 0.762)) "
                "(stroke (width 0.508) (type default)) (fill (type none)))")
OPAMP_SYM = SymbolDef(
    "OPAMP", "U",
    (Pin("3", "+", -7.62, 2.54, 0, "input"), Pin("2", "-", -7.62, -2.54, 0, "input"),
     Pin("1", "~", 7.62, 0, 180, "output"),
     Pin("8", "V+", -2.54, 7.62, 270, "power_in"),
     Pin("4", "V-", -2.54, -7.62, 90, "power_in")),
    "(polyline (pts (xy -5.08 5.08) (xy 5.08 0) (xy -5.08 -5.08) (xy -5.08 5.08)) "
    "(stroke (width 0.254) (type default)) (fill (type background)))")


def box(name: str, prefix: str, left: list, right: list) -> SymbolDef:
    """A rectangle with pins down each side, 2.54 mm apart."""
    rows = max(len(left), len(right))
    h = (rows + 1) * GRID
    # Wide enough for the longest pin name on each side, in 5.08 mm steps.
    chars = max((len(n) for _, n, _ in left), default=0) +         max((len(n) for _, n, _ in right), default=0)
    w = max(15.24, 5.08 * math.ceil((chars * 1.1 + 4) / 5.08))
    pins = []
    for i, (num, pname, et) in enumerate(left):
        pins.append(Pin(num, pname, -w / 2 - GRID, h / 2 - (i + 1) * GRID, 0, et))
    for i, (num, pname, et) in enumerate(right):
        pins.append(Pin(num, pname, w / 2 + GRID, h / 2 - (i + 1) * GRID, 180, et))
    body = (f"(rectangle (start {fmt(-w / 2)} {fmt(h / 2)}) (end {fmt(w / 2)} {fmt(-h / 2)}) "
            "(stroke (width 0.254) (type default)) (fill (type background)))")
    return SymbolDef(name, prefix, tuple(pins), body)


P, I, O, PW = "passive", "input", "output", "power_in"

ADC_SYM = box("ADC", "U", [("1", "AIN0", I), ("2", "AIN1", I), ("3", "REFIN1+", I),
                           ("4", "REFIN1-", I), ("5", "AVDD", PW), ("6", "AVSS", PW)],
              [("7", "SCLK", I), ("8", "DIN", I), ("9", "DOUT/RDY", O), ("10", "CS", I),
               ("11", "IOVDD", PW), ("12", "DGND", PW)])
REF_SYM = box("VREF", "U", [("1", "VIN", PW), ("2", "GND", PW)], [("3", "VOUT", O)])
MUX_SYM = box("MUX3", "U", [("1", "S1", P), ("2", "S2", P), ("3", "S3", P)],
              [("5", "D", P), ("6", "A0", I), ("7", "A1", I), ("8", "EN", I),
               ("9", "VDD", PW), ("10", "GND", PW)])
SEL_SYM = box("INSEL", "U", [("1", "SIG+", P), ("2", "SIG-", P), ("3", "CAL+", P),
                             ("4", "CAL-", P)],
              [("5", "OUT+", P), ("6", "OUT-", P), ("7", "SEL0", I), ("8", "SEL1", I),
               ("9", "VDD", PW), ("10", "GND", PW)])
CONN2_SYM = box("CONN2", "J", [], [("1", "1", P), ("2", "2", P)])
CONN12_SYM = box("CONN12", "J", [], [(str(i + 1), str(i + 1), P) for i in range(12)])
FLAG_SYM = box("PWR_FLAG", "#FLG", [], [("1", "pwr", "power_out")])

SYMBOLS = {s.name: s for s in (R_SYM, C_SYM, OPAMP_SYM, ADC_SYM, REF_SYM, MUX_SYM,
                               SEL_SYM, CONN2_SYM, CONN12_SYM, FLAG_SYM)}


def lib_symbol(s: SymbolDef, prefix: str = "daq:") -> str:
    pins = []
    for p in s.pins:
        pins.append(f"(pin {p.etype} line (at {fmt(p.x)} {fmt(p.y)} {p.angle}) "
                    f"(length {fmt(GRID)}) (name \"{p.name}\" {_font()}) "
                    f"(number \"{p.number}\" {_font()}))")
    return (f"(symbol \"{prefix}{s.name}\" (pin_names (offset 0.508)) "
            "(exclude_from_sim no) (in_bom yes) (on_board yes)\n"
            f"  (property \"Reference\" \"{s.prefix}\" (at 0 0 0) {_font()})\n"
            f"  (property \"Value\" \"{s.name}\" (at 0 0 0) {_font()})\n"
            "  (property \"Footprint\" \"\" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n"
            "  (property \"Datasheet\" \"\" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n"
            f"  (symbol \"{s.name}_0_1\" {s.body})\n"
            f"  (symbol \"{s.name}_1_1\"\n    " + "\n    ".join(pins) + ")\n)")


# ---------------------------------------------------------------- the board

@dataclass(frozen=True)
class Placed:
    ref: str
    sym: str
    value: str
    footprint: str
    x: float
    y: float
    nets: dict        # pin number -> net
    description: str


R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"


def _ohms(v: float) -> str:
    if v >= 1000:
        return fmt(v / 1000) + "k"
    return fmt(v)


def _farads(v: float) -> str:
    for unit, scale in (("u", 1e-6), ("n", 1e-9), ("p", 1e-12)):
        if v >= scale:
            return fmt(v / scale) + unit
    return fmt(v)


def board_parts(fe: FrontEnd = FRONT_END) -> list[Placed]:
    """Every part on the front end page, with position and pin nets."""
    # A grid of cells on the 2.54 mm grid, wide enough that no label of one
    # part can land on a pin or wire of its neighbour. Signal flows left to
    # right along rows 0 to 2; support circuitry is below.
    def cell(col, row):
        return 25.4 + col * 50.8, 25.4 + row * 45.72

    rg = [(g, r) for g, r in R_G_E96.items() if r is not None]
    parts = [
        Placed("J1", "CONN2", "Signal in", "Connector:Conn_01x02", *cell(0, 0),
               {"1": "sig_p", "2": "sig_n"}, "Sensor input"),
        Placed("J3", "CONN2", "Cal ref in", "Connector:Conn_01x02", *cell(0, 2),
               {"1": "cal_p", "2": "cal_n"}, "Calibration reference input"),
        Placed("U5", "INSEL", "Input selector", "", *cell(0, 1),
               {"1": "sig_p", "2": "sig_n", "3": "cal_p", "4": "cal_n", "5": "a_p",
                "6": "a_n", "7": "in_sel0", "8": "in_sel1", "9": "+AVDD", "10": "AGND"},
               "Signal, shorted pair or calibration reference"),
        Placed("R3", "R", _ohms(fe.r_prot), R0603, *cell(1, 0),
               {"1": "a_p", "2": "in_p"}, "Input protection, 0.1 %"),
        Placed("R4", "R", _ohms(fe.r_prot), R0603, *cell(1, 2),
               {"1": "a_n", "2": "in_n"}, "Input protection, 0.1 %"),
        Placed("C1", "C", _farads(fe.c_cm), C0603, *cell(2, 0),
               {"1": "in_p", "2": "AGND"}, "EMI filter, C0G"),
        Placed("C2", "C", _farads(fe.c_cm), C0603, *cell(2, 2),
               {"1": "in_n", "2": "AGND"}, "EMI filter, C0G"),
        Placed("C3", "C", _farads(fe.c_diff), C0603, *cell(2, 1),
               {"1": "in_p", "2": "in_n"}, "EMI filter, differential, C0G"),
        Placed("U1A", "OPAMP", "Zero drift", "", *cell(3, 0),
               {"3": "in_p", "2": "fb_p", "1": "out_p", "8": "+AVDD", "4": "AGND"},
               "Gain stage"),
        Placed("U1B", "OPAMP", "Zero drift", "", *cell(3, 2),
               {"3": "in_n", "2": "fb_n", "1": "out_n", "8": "+AVDD", "4": "AGND"},
               "Gain stage"),
        Placed("R5", "R", _ohms(fe.r_f), R0603, *cell(4, 0),
               {"1": "out_p", "2": "fb_p"}, "Feedback, 0.1 %"),
        Placed("R6", "R", _ohms(fe.r_f), R0603, *cell(4, 2),
               {"1": "out_n", "2": "fb_n"}, "Feedback, 0.1 %"),
    ]
    for k, (g, r) in enumerate(rg):
        parts.append(Placed(f"R7{'ABC'[k]}", "R", _ohms(r), R0603, *cell(3 + k, 1),
                            {"1": "fb_p", "2": f"rg_s{k + 1}"}, f"Gain set, G={g}, 0.1 %"))
    parts += [
        Placed("U4", "MUX3", "Gain mux", "", *cell(3, 3),
               {"1": "rg_s1", "2": "rg_s2", "3": "rg_s3", "5": "fb_n",
                "6": "gain_a0", "7": "gain_a1", "8": "gain_en", "9": "+AVDD", "10": "AGND"},
               "R_G select; EN low opens every switch, which is gain 1"),
        Placed("R8", "R", _ohms(fe.r_aa), R0603, *cell(5, 0),
               {"1": "out_p", "2": "ainp"}, "Anti-alias, 0.1 %"),
        Placed("R9", "R", _ohms(fe.r_aa), R0603, *cell(5, 2),
               {"1": "out_n", "2": "ainm"}, "Anti-alias, 0.1 %"),
        Placed("C4", "C", _farads(fe.c_aa_cm), C0603, *cell(6, 0),
               {"1": "ainp", "2": "AGND"}, "Anti-alias, C0G"),
        Placed("C5", "C", _farads(fe.c_aa_cm), C0603, *cell(6, 2),
               {"1": "ainm", "2": "AGND"}, "Anti-alias, C0G"),
        Placed("C6", "C", _farads(fe.c_aa_diff), C0603, *cell(6, 1),
               {"1": "ainp", "2": "ainm"}, "Anti-alias, differential, C0G"),
        Placed("U2", "ADC", "AD7124-8", "Package_CSP:LFCSP-32-1EP_5x5mm_P0.5mm", *cell(5, 3),
               {"1": "ainp", "2": "ainm", "3": "vref", "4": "AGND", "5": "+AVDD",
                "6": "AGND", "7": "spi_sclk", "8": "spi_mosi", "9": "spi_miso",
                "10": "spi_cs", "11": "+3V3", "12": "DGND"},
               "24-bit sigma-delta ADC, register map the firmware targets"),
        Placed("U3", "VREF", "2.5 V", "", *cell(1, 4),
               {"1": "+AVDD", "2": "AGND", "3": "vref_raw"},
               "Precision reference, part to be selected"),
        Placed("R10", "R", "100", R0603, *cell(2, 4),
               {"1": "vref_raw", "2": "vref"}, "Reference noise filter"),
        Placed("C7", "C", "47u", "Capacitor_SMD:C_1210_3225Metric", *cell(3, 4),
               {"1": "vref", "2": "AGND"}, "Reference noise filter, 34 Hz"),
        Placed("J2", "CONN12", "To MCU", "Connector:Conn_01x12", *cell(6, 4),
               {"1": "+3V3", "2": "DGND", "3": "spi_sclk", "4": "spi_mosi",
                "5": "spi_miso", "6": "spi_cs", "7": "gain_a0", "8": "gain_a1",
                "9": "gain_en", "10": "in_sel0", "11": "in_sel1", "12": "+AVDD"},
               "SPI and control to the STM32 board"),
    ]
    # Power flags tell the electrical rules check that each rail is driven
    # (by the power board, which is not on this page).
    for k, rail in enumerate(("+AVDD", "AGND", "+3V3", "DGND")):
        parts.append(Placed(f"#FLG0{k + 1}", "PWR_FLAG", "PWR_FLAG", "", *cell(k, 5),
                            {"1": rail}, "Rail driven by the power board"))
    return parts


def pin_position(p: Placed, pin: Pin) -> tuple[float, float]:
    """Connection point in sheet coordinates (y down, symbol not rotated)."""
    return round(p.x + pin.x, 4), round(p.y - pin.y, 4)


def stub_end(p: Placed, pin: Pin) -> tuple[float, float]:
    x, y = pin_position(p, pin)
    a = math.radians(pin.angle)
    return round(x - STUB * math.cos(a), 4), round(y + STUB * math.sin(a), 4)


def text_positions(p: Placed, s: SymbolDef) -> tuple[float, float, float, float]:
    """Reference above and value below the body, clear of the pin names."""
    if s.name in ("R", "C"):
        return p.x + 5.08, p.y - 1.27, p.x + 5.08, p.y + 1.27
    top = max(pin.y for pin in s.pins)
    bottom = min(pin.y for pin in s.pins)
    return p.x, p.y - top - 3.81, p.x, p.y - bottom + 3.81


def schematic(fe: FrontEnd = FRONT_END) -> str:
    parts = board_parts(fe)
    root = uid("root")
    used = sorted({p.sym for p in parts})
    out = [
        "(kicad_sch",
        "  (version 20231120)",
        "  (generator \"daqmodel\")",
        "  (generator_version \"1.0\")",
        f"  (uuid \"{root}\")",
        "  (paper \"A3\")",
        "  (title_block (title \"Mixed-signal DAQ: analogue front end\") "
        "(company \"CGainsWorks\") (rev \"A\") "
        "(comment 1 \"Generated by model/daqmodel/kicad.py from the netlist the SPICE deck uses\") "
        "(comment 2 \"Not fabricated. Amplifier, reference and switch parts to be selected.\"))",
        "  (lib_symbols",
    ]
    for name in used:
        out.append("    " + lib_symbol(SYMBOLS[name]).replace("\n", "\n    "))
    out.append("  )")

    for p in parts:
        s = SYMBOLS[p.sym]
        rx, ry, vx, vy = text_positions(p, s)
        out.append(
            f"  (symbol (lib_id \"daq:{p.sym}\") (at {fmt(p.x)} {fmt(p.y)} 0) (unit 1) "
            f"(exclude_from_sim no) (in_bom {'no' if p.ref.startswith('#') else 'yes'}) "
            "(on_board yes) (dnp no)\n"
            f"    (uuid \"{uid('sym', p.ref)}\")\n"
            f"    (property \"Reference\" \"{p.ref}\" (at {fmt(rx)} {fmt(ry)} 0) {_font()})\n"
            f"    (property \"Value\" \"{p.value}\" (at {fmt(vx)} {fmt(vy)} 0) {_font()})\n"
            f"    (property \"Footprint\" \"{p.footprint}\" (at {fmt(p.x)} {fmt(p.y)} 0) "
            "(effects (font (size 1.27 1.27)) hide))\n"
            f"    (property \"Description\" \"{p.description}\" (at {fmt(p.x)} {fmt(p.y)} 0) "
            "(effects (font (size 1.27 1.27)) hide))\n"
            + "".join(f"    (pin \"{pin.number}\" (uuid \"{uid('pin', p.ref, pin.number)}\"))\n"
                      for pin in s.pins)
            + f"    (instances (project \"daq_frontend\" (path \"/{root}\" "
            f"(reference \"{p.ref}\") (unit 1))))\n  )")

    for p in parts:
        s = SYMBOLS[p.sym]
        for pin in s.pins:
            net = p.nets[pin.number]
            x0, y0 = pin_position(p, pin)
            x1, y1 = stub_end(p, pin)
            out.append(f"  (wire (pts (xy {fmt(x0)} {fmt(y0)}) (xy {fmt(x1)} {fmt(y1)})) "
                       f"(stroke (width 0) (type default)) (uuid \"{uid('w', p.ref, pin.number)}\"))")
            # Text runs away from the pin: left of a left hand pin and so on.
            ang = {0: 180, 180: 0, 90: 270, 270: 90}[pin.angle]
            just = "right" if ang == 180 else "left"
            if ang in (90, 270):
                just = "left" if ang == 90 else "right"
            out.append(f"  (label \"{net}\" (at {fmt(x1)} {fmt(y1)} {ang}) "
                       f"(effects (font (size 1.27 1.27)) (justify {just} bottom)) "
                       f"(uuid \"{uid('l', p.ref, pin.number)}\"))")

    out += [
        "  (sheet_instances (path \"/\" (page \"1\")))",
        ")",
    ]
    return "\n".join(out) + "\n"


def bom_rows(fe: FrontEnd = FRONT_END) -> list[list[str]]:
    rows = []
    for p in board_parts(fe):
        if p.ref.startswith("#"):
            continue
        rows.append([p.ref, p.value, p.footprint or "to be selected", p.description])
    return rows


def symbol_library() -> str:
    """The project symbol library, so KiCad finds every symbol by name."""
    nl = "\n"
    body = nl.join("  " + lib_symbol(SYMBOLS[n], prefix="").replace(nl, nl + "  ")
                   for n in sorted(SYMBOLS))
    return ("(kicad_symbol_lib (version 20231120) (generator \"daqmodel\") "
            "(generator_version \"1.0\")" + nl + body + nl + ")")


SYM_LIB_TABLE = """(sym_lib_table
  (version 7)
  (lib (name "daq")(type "KiCad")(uri "${KIPRJMOD}/daq.kicad_sym")(options "")(descr "Symbols for this project, generated"))
)"""

PROJECT = """{
  "meta": {
    "filename": "daq_frontend.kicad_pro",
    "version": 1
  }
}"""
