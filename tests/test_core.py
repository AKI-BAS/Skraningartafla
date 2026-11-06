# -*- coding: utf-8 -*-
"""Plain-CPython tests for skraning.core:  python -m pytest tests  (or run directly)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from skraning import core  # noqa: E402
from skraning.core import Rymi, Staedi, COL  # noqa: E402


def sample():
    return [
        Rymi("0001", "Geymsla", "A", "N", "0101", 11.4, hmin=3.23, hmax=3.23,
             netto_parts=[9.9], floor_elev=-3.2),
        Rymi("0002", "Bílakjallari", "A", "B", "Y", 567.4, hmin=2.845, hmax=2.845,
             netto=532.4, floor_elev=-3.2),
        Rymi("0101", "Íbúð", "A", "N", "0101", 56.2, hmin=2.89, hmax=2.89,
             netto_parts=[10.9, 3.6, 25, 3.6, 3.9], sameign_sumra="Y1",
             counts={"Stofur": 1, "Baðherbergi": 1}),
        Rymi("0102", "Íbúð", "A", "N", "0102", 115.1, hmin=2.89, hmax=2.89,
             netto_parts=[97.1], sameign_sumra="Y1"),
        Rymi("0103", "Stigahús/Lyfta", "A", "U", "Y1", 26.5, stigar=6, op=6.5,
             hmin=2.89, hmax=2.89, netto_parts=[10.8, 4.5]),
        Rymi("0104", "Svalir", "B", "S", "0101", 11.4),
        Rymi("0105", "Skyggni", "B", "U", "Y1", 3.5, hmin=2.89, hmax=2.89),
        Rymi("0106", "Verönd", "C", "S", "0102", 31.9),
    ]


def parking():
    return [Staedi("B02", "Y"), Staedi("B01", "Y")]


def test_rows_layout():
    rows, row_of = core.einingar_rows(sample(), parking())
    # floor 00 first, blank line, then floor 01
    assert row_of["0001"] == 8 and row_of["0002"] == 9
    assert all(v is None for v in rows[2])
    assert row_of["0101"] == 11
    r = rows[row_of["0101"] - 8]
    assert r[COL["B"]] == "'0101" and r[COL["E"]] == "'0101"
    assert r[COL["F"]] == 56.2 and r[COL["L"]] == 2.89 and r[COL["M"]] == 2.89
    assert r[COL["N"]] == "=ROUND(F11*M11,1)"
    assert r[COL["O"]] == "=10.9+3.6+25+3.6+3.9"
    assert r[COL["P"]] == "=F11"
    assert r[COL["Q"]] == "=ROUND((L11+M11)/2,2)" and r[COL["R"]] == "=ROUND(O11*Q11,1)"
    assert r[COL["U"]] == 1 and r[COL["AA"]] == 1


def test_stair_and_open_rows():
    rows, row_of = core.einingar_rows(sample(), [])
    st = rows[row_of["0103"] - 8]
    assert st[COL["H"]] == 6 and st[COL["I"]] == 6.5
    assert st[COL["J"]] == "=F%d-I%d" % (row_of["0103"], row_of["0103"])
    assert st[COL["P"]] is None                # Y1: no birt flatarmál
    assert st[COL["R"]] is not None            # but skiptarúmmál
    sv = rows[row_of["0104"] - 8]
    assert sv[COL["A"]] == "B" and sv[COL["L"]] is None and sv[COL["N"]] is None
    assert sv[COL["Q"]] == 1 and sv[COL["O"]] is None
    sk = rows[row_of["0105"] - 8]              # B skyggni: height + volume, no Q
    assert sk[COL["N"]] is not None and sk[COL["Q"]] is None
    assert [r[COL["B"]] for r in rows[row_of["0104"] - 8:row_of["0106"] - 7]] == \
        ["'0104", "'0105", "'0106"]


def test_parking_lines_last():
    rows, row_of = core.einingar_rows(sample(), parking())
    assert row_of["B01"] < row_of["B02"]
    e = rows[row_of["B01"] - 8]
    assert e[:5] == ["E", "B01", "Bílastæði", "B", "B01"]
    assert all(v is None for v in rows[row_of["B01"] - 9])


def test_haedir_and_totals():
    h = core.haedir_rows(sample())
    assert [x[0] for x in h] == ["00", "01"]
    assert h[0][2] == 578.8
    assert h[1][2] == 56.2 + 115.1 + 26.5
    t = core.totals(sample())
    assert t["birt"] == round(11.4 + 56.2 + 115.1, 1)


def test_sameign():
    rows = core.sameign_rows(sample(), parking())
    assert rows[0] == ("B01", "Bílastæði", "Y", "Bílakjallari", "J")
    assert ("0101", "Íbúð", "Y1", "Sameign", "S") in rows


def test_validate_clean_sample():
    errs = [i for i in core.validate(sample(), parking()) if i.level == core.Issue.ERROR]
    assert errs == [], [e.message for e in errs]


def test_validate_catches():
    bad = sample() + [
        Rymi("0101", "Íbúð", "A", "N", "0199", 10, hmin=2.8, hmax=2.8),   # dup + no eignarlína
        Rymi("0107", "Svalir", "D", "N", "Y0", 5),
        Rymi("0108", "Bílskúr", "A", "B", "0101", 20, hmin=2.5, hmax=2.5),
    ]
    msgs = " | ".join(i.message for i in core.validate(bad, [Staedi("X1", "")]))
    for needle in ("notað 2 sinnum", "0199", "lokun 'D'", "Y0", "ætti að vera höfuðflokkur S",
                   "bílgeymsla", "vantar sameign sumra"):
        assert needle in msgs, needle


def test_classify_room():
    kw = [("Svefnherbergi", ["svefn"]), ("Baðherbergi", ["bað"]), ("Stofur", ["stofa"]),
          ("Önnur herbergi", ["herbergi"])]
    assert core.classify_room("Svefnherbergi 2", kw) == "Svefnherbergi"
    assert core.classify_room("Forstofa", kw) == "Aðrir fletir"
    assert core.classify_room("Borð-stofa", kw) == "Stofur"
    assert core.classify_room("Baðherbergi", kw) == "Baðherbergi"
    assert core.classify_room("Herbergi", kw) == "Önnur herbergi"


def test_overview_tables():
    from skraning import overview_tables as ot
    sh = ot.rymi_sheet(sample())
    row = [r for r in sh["rows"] if r[2] == "'0101"][0]
    assert row[6] == 56.2 and row[15] == 47.0 and row[22] == 5
    own = dict((r[0], r) for r in ot.owner_sheet(sample())["rows"])
    assert own["'0101"][3] == round(11.4 + 56.2, 1) and own["'0101"][4] == 11.4


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
    print("%d tests passed" % n)
