# -*- coding: utf-8 -*-
"""Plain tables (no formulas) for the overview export. No Revit imports,
so this can be tested in plain Python.

A sheet is a dict: {"name", "headers", "rows", "formats": {col_index: fmt}}.
"""
from __future__ import unicode_literals

from skraning import core

F1 = "0.0"
F2 = "0.00"


def sheet(name, headers, rows, formats=None, note=None):
    return {"name": name, "headers": list(headers), "rows": [list(r) for r in rows],
            "formats": formats or {}, "note": note}


def _v(x, nd=1):
    if x is None or x == "":
        return None
    try:
        return round(float(x), nd)
    except (TypeError, ValueError):
        return x


def rymi_sheet(rymi):
    """The rýmislínur exactly as the Skráningartafla export calculates them,
    but as plain numbers so they can be compared with a hand-filled table."""
    headers = ["Hæð", "D0 Lokun", "D1 Rými", "D2 Notkun", "D3 Höfuðfl.", "D4 Eignarhald",
               "D5 Botnflötur", "D5M Milliflötur", "D6 Stigar", "D7 Op", "D8 Brúttó",
               "D9 <1,8m", "D10a Salarh. lægst", "D10b Salarh. hæst", "D11 Brúttórúmmál",
               "D12 Nettóflötur", "Nettó - herbergi", "D13 Birt flatarmál", "D14 Reiknitala",
               "D15 Skiptarúmmál (áætl.)", "D16 Upphitað", "Sameign sumra", "Fj. herbergja"]
    rows = []
    for r in core.sort_rymi(rymi):
        mh = r.mean_height()
        netto = r.netto_value()
        skipt = None
        if r.gets_skipt() and netto is not None:
            skipt = core.r1(netto * (1 if r.is_svalir else (mh or 0))) or None
        rows.append([
            core.text(r.floor_code), r.lokun, core.text(r.number), r.notkun, r.hofud,
            core.text(r.eignarhald),
            None if r.milli else _v(r.botn), _v(r.botn) if r.milli else None,
            _v(r.stigar), _v(r.op), _v(r.brutto()), _v(r.undir18),
            _v(r.hmin, 2), _v(r.hmax, 2), _v(r.rummal()), netto,
            " + ".join("%.1f" % p for p in r.netto_parts) or None,
            _v(r.birt()), _v(r.reiknitala, 3), skipt, r.upphitad, r.sameign_sumra or None,
            len(r.netto_parts) or None,
        ])
    fm = dict((i, F1) for i in (6, 7, 8, 9, 10, 11, 14, 15, 17, 19))
    fm.update({12: F2, 13: F2})
    return sheet("Rýmislínur", headers, rows, fm,
                 note="Sömu tölur og Flytja út skrifar í Einingar, en sem gildi (ekki formúlur).")


def owner_sheet(rymi):
    """Sum per eignarhald (séreign / sameign) - handy for checking Samantekt."""
    groups = {}
    for r in rymi:
        key = r.eignarhald or "(autt)"
        g = groups.setdefault(key, {"lines": [], "A": 0.0, "B": 0.0, "C": 0.0,
                                    "netto": 0.0, "rummal": 0.0, "birt": 0.0})
        g["lines"].append(r.number)
        if r.lokun in ("A", "B", "C"):
            g[r.lokun] += r.flatur()
        g["netto"] += r.netto_value() or 0.0
        g["rummal"] += r.rummal() or 0.0
        g["birt"] += r.birt() or 0.0
    rows = []
    for key in sorted(groups, key=lambda k: (not core.RE_SEREIGN.match(k), core.y_sort_key(k))):
        g = groups[key]
        rows.append([core.text(key), len(g["lines"]), ", ".join(sorted(g["lines"])),
                     _v(g["A"]) or None, _v(g["B"]) or None, _v(g["C"]) or None,
                     _v(g["netto"]) or None, _v(g["rummal"]) or None, _v(g["birt"]) or None])
    return sheet("Eignir", ["Eignarhald", "Fj. lína", "Rýmislínur", "Flötur A", "Flötur B",
                            "Flötur C", "Nettó", "Brúttórúmmál", "Birt flatarmál"],
                 rows, dict((i, F1) for i in range(3, 9)))
