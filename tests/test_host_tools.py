"""Calibration arithmetic, framing and the capture tool."""

import re
import struct

import pytest

import capture
from conftest import ROOT
from daqhost import calibration as cal
from daqhost import framing


def test_round_div_rounds_half_away_from_zero():
    assert [cal.round_div(a, 2) for a in (5, -5, 4, -4, 1, -1)] == [3, -3, 2, -2, 1, -1]
    with pytest.raises(ValueError):
        cal.round_div(1, 0)


def test_perfect_channel_calibrates_to_identity():
    span = round(0.9 * 2 ** 23)
    c = cal.compute([0] * 8, [span] * 8, 2_250_000_000, 2_500_000_000)
    assert c.offset_q8 == 0
    assert abs(c.gain_q29 - 2 ** 29) < 200
    assert cal.apply(2 ** 22, c) == pytest.approx(2 ** 30, rel=1e-6)


def test_offset_and_gain_errors_are_removed():
    # A channel reading 1000 codes high with 0.2 percent too much gain.
    def code(v):
        return round(v / 2.5 * 2 ** 23 * 1.002) + 1000
    c = cal.compute([code(0)] * 4, [code(2.25)] * 4, 2_250_000_000, 2_500_000_000)
    for v in (-2.0, -0.5, 0.0, 1.0, 2.4):
        assert cal.to_volts(cal.apply(code(v), c), 2.5) == pytest.approx(v, abs=1e-6)


@pytest.mark.parametrize("span", [0, -1000, 1000, 2 ** 24])
def test_implausible_spans_are_refused(span):
    with pytest.raises(cal.CalibrationError):
        cal.compute([0] * 4, [span] * 4, 2_250_000_000, 2_500_000_000)


def test_output_saturates_at_int32():
    c = cal.Coefficients(-(1 << 30), 1 << 29)
    assert cal.apply(2 ** 23 - 1, c) == cal.INT32_MAX


def test_committed_c_vectors_agree_with_python():
    """The fixture the C tests use, recomputed here from its own codes."""
    text = (ROOT / "firmware/test/fixtures/cal_vectors.h").read_text()
    blocks = re.findall(r"\{ /\* gain \d+ \*/(.*?)\n    \},", text, re.S)
    assert len(blocks) == 4
    for b in blocks:
        head, *arrays = b.split("{")
        nums = [int(x.rstrip("L")) for x in re.findall(r"-?\d+L*", head)]
        _, vcal, fs, off, gain = nums
        zero, ref, codes, outs = ([int(x) for x in a.split("}")[0].split(",")] for a in arrays)
        c = cal.compute(zero, ref, vcal, fs)
        assert (c.offset_q8, c.gain_q29) == (off, gain)
        assert [cal.apply(x, c) for x in codes] == outs


def test_crc_check_value():
    assert framing.crc16_ccitt(b"123456789") == 0x29B1


def test_round_trip_and_resynchronisation():
    a = framing.encode(framing.FRAME_SAMPLES, 7, [1, -2, 3])
    b = framing.encode(framing.FRAME_RAW, 8, [2 ** 31 - 1, -(2 ** 31)])
    corrupt = bytearray(framing.encode(framing.FRAME_SAMPLES, 9, [5]))
    corrupt[7] ^= 0xFF
    c = framing.encode(framing.FRAME_STATUS, 10, [0] * 5)
    frames, st = framing.decode(b"\x00\x13" + a + b + bytes(corrupt) + c + b"\xA5")
    assert [f.words for f in frames[:2]] == [[1, -2, 3], [2 ** 31 - 1, -(2 ** 31)]]
    assert st.crc_errors == 1
    assert st.sequence_gaps == 1          # 8 then 10
    assert st.frames == 3


def test_capture_decodes_64_bit_coefficients():
    off, gain = -832228, 537015460
    words = [off & 0xFFFFFFFF, (off >> 32) & 0xFFFFFFFF, gain & 0xFFFFFFFF, gain >> 32, 3]
    words = [struct.unpack("<i", struct.pack("<I", w))[0] for w in words]
    cap = capture.parse(framing.encode(framing.FRAME_COEFFS, 0, words))
    assert cap.coeffs == [(3, off, gain)]


def test_capture_cli_writes_volts(tmp_path):
    stream = framing.encode(framing.FRAME_SAMPLES, 0, [2 ** 30, -(2 ** 30)])
    stream += framing.encode(framing.FRAME_STATUS, 1, [2, 0, 0, 0, 0])
    src = tmp_path / "s.bin"
    src.write_bytes(stream)
    out = tmp_path / "c.csv"
    assert capture.main([str(src), "--gain", "1", "--out", str(out)]) == 0
    rows = out.read_text().splitlines()
    assert rows[1].split(",")[2] == "1.2500000000"
    assert rows[2].split(",")[2] == "-1.2500000000"
