# -*- coding: utf-8 -*-
"""Pure-Python logic for the skráningartafla: rows, floors, sameign sumra, checks.

No Revit or Excel imports here, so this runs (and is tested) in plain CPython
as well as in pyRevit's IronPython.

Column layout of the Einingar sheet (HMS útgáfa 5.03), A..AC:

    A  D0   Lokun            K  D9   Brúttó sh < 1,8   U  Stofur
    B  D1   Rými hæð-röð     L  D10a Salarhæð min      V  Svefnherbergi
    C  D2   Notkun texti     M  D10b Salarhæð max      W  Eldhús
    D  D3   Höfuðflokkun     N  D11  Brúttórúmmál      X  Önnur herbergi
    E  D4   Eignarhald       O  D12  Nettóflötur       Y  Geymslur
    F  D5   Botnflötur       P  D13  Birt flatarmál    Z  Þvottahús
    G  D5M  Milliflötur      Q  D14  Reiknitala        AA Baðherbergi
    H  D6   Stigar           R  D15  Skiptarúmmál      AB Snyrtingar
    I  D7   Op               S  D16  Upphitað rými     AC Aðrir fletir
    J  D8   Brúttóflötur     T       Alrými
"""
from __future__ import unicode_literals

import re

FIRST_ROW = 8          # first data row on Einingar / Sameign_sumra / Hæðir+1
N_COLS = 29            # A..AC

COL = dict((k, i) for i, k in enumerate(
    "A B C D E F G H I J K L M N O P Q R S T U V W X Y Z AA AB AC".split()))

COUNT_COLUMNS = [      # T..AC, in sheet order
    "Alrými", "Stofur", "Svefnherbergi", "Eldhús", "Önnur herbergi",
    "Geymslur", "Þvottahús", "Baðherbergi", "Snyrtingar", "Aðrir fletir",
]

LOKUN = ("A", "B", "C")
HOFUD = ("N", "U", "T", "B", "F", "V", "S")
SKIPT_HOFUD = ("N", "U", "T", "B")       # get birt flatarmál / skiptarúmmál

RE_RYMI = re.compile(r"^-?\d{4,6}$")
RE_ELINE = re.compile(r"^[A-Z]\d{2,}$")
RE_SEREIGN = re.compile(r"^-?\d{4,6}$")
RE_Y = re.compile(r"^Y(\d*)$")


# --------------------------------------------------------------------------
# data

class Rymi(object):
    """One rýmislína (one Revit Area, or one Room in rooms mode)."""

    def __init__(self, number, notkun="", lokun="A", hofud="", eignarhald="",
                 botn=0.0, milli=False, stigar=None, op=None, undir18=None,
                 hmin=None, hmax=None, netto=None, netto_parts=None,
                 reiknitala=None, upphitad=None, floor_code=None,
                 floor_name=None, floor_elev=0.0, sameign_sumra="",
                 counts=None, element_id=None):
        self.number = (number or "").strip()
        self.notkun = (notkun or "").strip()
        self.lokun = (lokun or "A").strip().upper()
        self.hofud = (hofud or "").strip().upper()
        self.eignarhald = (eignarhald or "").strip().upper()
        self.botn = botn or 0.0
        self.milli = bool(milli)
        self.stigar = stigar
        self.op = op
        self.undir18 = undir18
        self.hmin = hmin
        self.hmax = hmax
        self.netto = netto                  # explicit value (overrides parts)
        self.netto_parts = list(netto_parts or [])   # room areas inside
        self.reiknitala = reiknitala
        self.upphitad = upphitad
        self.floor_code = floor_code or self.number[:2]
        self.floor_name = floor_name
        self.floor_elev = floor_elev
        self.sameign_sumra = sameign_sumra or ""
        self.counts = counts or {}
        self.element_id = element_id

    # -- derived -----------------------------------------------------------
    @property
    def is_sereign(self):
        return bool(RE_SEREIGN.match(self.eignarhald))

    @property
    def is_y(self):
        return bool(RE_Y.match(self.eignarhald))

    @property
    def is_svalir(self):
        return self.hofud == "S"

    @property
    def is_eignarlina(self):
        return self.is_sereign and self.eignarhald == self.number

    def netto_value(self):
        if self.netto is not None:
            return r1(self.netto)
        if self.netto_parts:
            return r1(sum(r1(p) for p in self.netto_parts))
        return None

    def mean_height(self):
        if self.hmin is None and self.hmax is None:
            return None
        lo = self.hmin if self.hmin is not None else self.hmax
        hi = self.hmax if self.hmax is not None else self.hmin
        return (r2(lo) + r2(hi)) / 2.0

    def flatur(self):
        """D5 or D5M, whichever this line uses."""
        return r1(self.botn)

    def brutto(self):
        return r1(self.flatur() - r1(self.op or 0))

    def has_volume(self):
        """Brúttórúmmál goes in for A (and B, except svalir) with a height.
        Millifletir share volume with the space they sit in."""
        if self.milli or self.is_svalir or self.hofud == "S":
            return False
        if self.lokun not in ("A", "B"):
            return False
        return self.mean_height() is not None

    def rummal(self):
        if not self.has_volume():
            return None
        return r1(self.botn * self.mean_height())

    def gets_birt(self):
        return (self.lokun == "A" and self.is_sereign and
                self.hofud in SKIPT_HOFUD)

    def birt(self):
        if not self.gets_birt():
            return None
        return r1(self.flatur() - r1(self.op or 0) - r1(self.undir18 or 0))

    def gets_skipt(self):
        """Skiptarúmmál: séreign and sameign sumra (not X)."""
        return self.is_sereign or self.is_y


class Staedi(object):
    """One E-line: a parking space in a bílageymsla (Revit Parking element)."""

    def __init__(self, number, y_code="", notkun="Bílastæði", element_id=None):
        self.number = (number or "").strip().upper()
        self.y_code = (y_code or "").strip().upper()
        self.notkun = notkun
        self.element_id = element_id


class Issue(object):
    ERROR = "Villa"
    WARN = "Aðvörun"
    INFO = "Ath"

    def __init__(self, level, message, element_id=None, number=""):
        self.level = level
        self.message = message
        self.element_id = element_id
        self.number = number


# --------------------------------------------------------------------------
# helpers

def r1(x):
    return round(float(x) + 0.0, 1) if x is not None else None


def r2(x):
    return round(float(x) + 0.0, 2) if x is not None else None


def _num(x):
    """Format a number for an Excel formula string (always '.' decimals)."""
    s = "%.4f" % x
    s = s.rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def text(s):
    """Text that must stay text in Excel ('0101', '00')."""
    return "'" + s if s else None


def y_sort_key(code):
    m = RE_Y.match(code or "")
    if not m:
        return (9, code)
    return (0, int(m.group(1) or 0))


def parse_sameign(value):
    """'Y1; Y:J, Y2:P' -> [('Y1','S'), ('Y','J'), ('Y2','P')]"""
    out = []
    for part in re.split(r"[;,\s]+", (value or "").upper()):
        if not part:
            continue
        if ":" in part:
            code, rule = part.split(":", 1)
        else:
            code, rule = part, ""
        out.append((code.strip(), rule.strip()))
    return out


def classify_room(name, keywords):
    """Which count column a room name belongs to.

    keywords: list of (column, [prefixes]) checked in order; a prefix matches
    the start of any word in the name (so 'stofa' hits 'Stofa' and
    'Borð-stofa' but not 'Forstofa'). Falls back to 'Aðrir fletir'.
    """
    words = [w for w in re.split(r"[\s/\-_.,()]+", (name or "").lower()) if w]
    for col, prefixes in keywords:
        for p in prefixes:
            p = p.lower()
            for w in words:
                if w.startswith(p):
                    return col
    return "Aðrir fletir"


# --------------------------------------------------------------------------
# sorting / floors

def sort_rymi(rymi):
    lok = {"A": 0, "B": 1, "C": 2}
    return sorted(rymi, key=lambda r: (r.floor_elev, r.floor_code,
                                       lok.get(r.lokun, 9), r.number))


def floors(rymi):
    """[(code, name, elev)] in elevation order."""
    seen = {}
    for r in rymi:
        f = seen.get(r.floor_code)
        if f is None or r.floor_elev < f[2]:
            seen[r.floor_code] = (r.floor_code, r.floor_name or default_floor_name(r.floor_code),
                                  r.floor_elev)
    return sorted(seen.values(), key=lambda f: (f[2], f[0]))


def default_floor_name(code):
    try:
        n = int(code)
    except (TypeError, ValueError):
        return code or ""
    if n == 0:
        return "Kjallari"
    if n < 0:
        return "%d. kjallari" % (1 - n)
    return "%d. hæð" % n


# --------------------------------------------------------------------------
# sheet rows

def einingar_rows(rymi, staedi, fill_calculated=True, blank_between_floors=True):
    """Rows for Einingar starting at FIRST_ROW. Each row is a list of N_COLS
    values (None = empty); formulas are strings starting with '='.
    Returns (rows, row_of) where row_of maps rýmisnúmer -> Excel row."""
    rows, row_of = [], {}
    last_floor = None
    for r in sort_rymi(rymi):
        if blank_between_floors and last_floor is not None and r.floor_code != last_floor:
            rows.append([None] * N_COLS)
        last_floor = r.floor_code
        n = FIRST_ROW + len(rows)
        rows.append(_rymi_row(r, n, fill_calculated))
        row_of[r.number] = n
    if staedi:
        rows.append([None] * N_COLS)
        rows.append([None] * N_COLS)
        for s in sorted(staedi, key=lambda s: s.number):
            row = [None] * N_COLS
            row[COL["A"]] = "E"
            row[COL["B"]] = s.number
            row[COL["C"]] = s.notkun
            row[COL["D"]] = "B"
            row[COL["E"]] = s.number
            row_of[s.number] = FIRST_ROW + len(rows)
            rows.append(row)
    return rows, row_of


def _rymi_row(r, n, fill_calculated):
    row = [None] * N_COLS
    c = COL
    F = "F%d" % n
    G = "G%d" % n
    row[c["A"]] = r.lokun
    row[c["B"]] = text(r.number)
    row[c["C"]] = r.notkun
    row[c["D"]] = r.hofud
    row[c["E"]] = text(r.eignarhald) if r.is_sereign else r.eignarhald
    area_col = "G" if r.milli else "F"
    row[c[area_col]] = r.flatur()
    if r.stigar:
        row[c["H"]] = r1(r.stigar)
    if r.op:
        row[c["I"]] = r1(r.op)
    if r.undir18:
        row[c["K"]] = r1(r.undir18)

    svalir = r.is_svalir
    if not svalir and r.lokun in ("A", "B") and r.mean_height() is not None:
        row[c["L"]] = r2(r.hmin if r.hmin is not None else r.hmax)
        row[c["M"]] = r2(r.hmax if r.hmax is not None else r.hmin)
    if r.has_volume():
        if row[c["L"]] == row[c["M"]]:
            row[c["N"]] = "=ROUND(%s*M%d,1)" % (F, n)
        else:
            row[c["N"]] = "=ROUND(%s*(L%d+M%d)/2,1)" % (F, n, n)

    if r.lokun == "A":
        netto = r.netto_value()
        if netto is not None:
            parts = [r1(p) for p in r.netto_parts] if r.netto is None else []
            if len(parts) > 1:
                row[c["O"]] = "=" + "+".join(_num(p) for p in parts)
            else:
                row[c["O"]] = netto

    if r.upphitad:
        row[c["S"]] = int(r.upphitad)
    for i, name in enumerate(COUNT_COLUMNS):
        v = r.counts.get(name)
        if v:
            row[c["T"] + i] = v

    if fill_calculated:
        src = G if r.milli else F
        row[c["J"]] = ("=%s-I%d" % (src, n)) if r.op else ("=%s" % src)
        if r.gets_birt():
            row[c["P"]] = "=%s-I%d-K%d" % (src, n, n) if (r.op or r.undir18) else "=%s" % src
        if r.gets_skipt():
            if svalir:
                row[c["Q"]] = 1
                row[c["R"]] = "=ROUND(%s*Q%d,1)" % (F, n)
            elif r.reiknitala is not None:
                row[c["Q"]] = r2(r.reiknitala)
                if r.lokun == "A" and row[c["O"]] is not None:
                    row[c["R"]] = "=ROUND(O%d*Q%d,1)" % (n, n)
                elif r.lokun == "B" and r.has_volume():
                    row[c["R"]] = "=ROUND(N%d*Q%d,1)" % (n, n)
                elif r.lokun == "C":
                    row[c["R"]] = "=ROUND(%s*Q%d,1)" % (F, n)
            elif (r.lokun == "A" and r.hofud in SKIPT_HOFUD and r.has_volume()
                  and row[c["O"]] is not None):
                # reiknitala = D11/D5 = mean salarhæð (unrounded volume)
                row[c["Q"]] = "=ROUND((L%d+M%d)/2,2)" % (n, n)
                row[c["R"]] = "=ROUND(O%d*Q%d,1)" % (n, n)
    elif r.reiknitala is not None:
        row[c["Q"]] = r2(r.reiknitala)
    elif svalir and r.gets_skipt():
        row[c["Q"]] = 1
    return row


def haedir_rows(rymi):
    """[(code, name, botn A, rúmmál A)] for the Hæðir sheet."""
    out = []
    for code, name, _ in floors(rymi):
        botn = rumm = 0.0
        for r in rymi:
            if r.floor_code != code or r.lokun != "A" or r.milli:
                continue
            botn += r.flatur()
            rumm += r.rummal() or 0.0
        out.append((code, name, r1(botn), r1(rumm)))
    return out


def sameign_rows(rymi, staedi):
    """Rows for Sameign_sumra: (eignarhald, notkun, Y, Y notkun, regla)."""
    y_name = {}
    for r in rymi:
        if r.is_y:
            if r.hofud == "B" or r.eignarhald not in y_name:
                y_name[r.eignarhald] = r.notkun if r.hofud == "B" else "Sameign"
    rows = []
    for s in staedi:
        if s.y_code:
            rows.append((s.number, s.notkun, s.y_code, y_name.get(s.y_code, "Sameign"), "J"))
    for r in rymi:
        if not r.is_eignarlina:
            continue
        for code, rule in parse_sameign(r.sameign_sumra):
            if not rule:
                rule = "J" if r.hofud == "B" else "S"
            rows.append((r.eignarhald, r.notkun, code, y_name.get(code, "Sameign"), rule))
    rows.sort(key=lambda x: (y_sort_key(x[2]), x[0]))
    return rows


def totals(rymi):
    """Numbers for the summary in the output window (A lokun only)."""
    t = {"botn": 0.0, "brutto": 0.0, "rummal": 0.0, "netto": 0.0, "birt": 0.0}
    for r in rymi:
        if r.lokun != "A":
            continue
        if not r.milli:
            t["botn"] += r.flatur()
        t["brutto"] += r.brutto()
        t["rummal"] += r.rummal() or 0.0
        t["netto"] += r.netto_value() or 0.0
        t["birt"] += r.birt() or 0.0
    return dict((k, r1(v)) for k, v in t.items())


# --------------------------------------------------------------------------
# checks (same rules the HMS villutékk uses, plus model-side ones)

def validate(rymi, staedi):
    issues = []
    E, W = Issue.ERROR, Issue.WARN

    def add(level, msg, r=None):
        issues.append(Issue(level, msg, getattr(r, "element_id", None),
                            getattr(r, "number", "")))

    numbers = {}
    for r in rymi:
        numbers.setdefault(r.number, []).append(r)
    for num, rs in numbers.items():
        if len(rs) > 1:
            for r in rs:
                add(E, "Rýmisnúmer %s er notað %d sinnum" % (num or "(tómt)", len(rs)), r)

    eignarlinur = set(r.number for r in rymi if r.is_eignarlina)
    y_used = set(r.eignarhald for r in rymi if r.is_y)
    y_referenced = set()

    for r in rymi:
        tag = r.number or "(ekkert númer)"
        if not RE_RYMI.match(r.number):
            add(E, "%s: rýmisnúmer á að vera 4-6 tölustafir (hæð + röð)" % tag, r)
        elif r.floor_code and not r.number.startswith(r.floor_code):
            add(W, "%s: rýmisnúmer byrjar ekki á hæðarnúmeri %s" % (tag, r.floor_code), r)
        if r.lokun not in LOKUN:
            add(E, "%s: lokun '%s' á að vera A, B eða C" % (tag, r.lokun), r)
        if r.hofud not in HOFUD:
            add(E, "%s: höfuðflokkun '%s' á að vera N, U, T, B, F, V eða S" % (tag, r.hofud), r)
        e = r.eignarhald
        if not e:
            add(E, "%s: eignarhald vantar" % tag, r)
        elif e == "Y0":
            add(E, "%s: Y0 er ekki leyfilegt" % tag, r)
        elif not (r.is_sereign or r.is_y or e == "X"):
            add(E, "%s: eignarhald '%s' á að vera rýmisnúmer, X eða Y/Y1/Y2..." % (tag, e), r)
        elif r.is_sereign and e not in eignarlinur:
            add(E, "%s: eignarhald %s vísar á rými sem er ekki til (eða er ekki eignarlína)"
                % (tag, e), r)
        if r.hofud == "B" and r.is_sereign and e != r.number:
            add(E, "%s: bílgeymsla á að hafa sama eignarhald og rýmisnúmer" % tag, r)
        low = r.notkun.lower()
        if any(k in low for k in ("svalir", "verönd", "þaksvalir")) and r.hofud != "S":
            add(W, "%s: '%s' ætti að vera höfuðflokkur S" % (tag, r.notkun), r)
        if r.botn <= 0:
            add(E, "%s: botnflötur er 0" % tag, r)
        if r.lokun == "A" and not r.is_svalir and not r.milli and r.mean_height() is None:
            add(W, "%s: salarhæð vantar (D10a/D10b) - brúttórúmmál reiknast ekki" % tag, r)
        if (r.lokun == "A" and r.hofud in SKIPT_HOFUD and r.gets_skipt()
                and r.netto_value() is None):
            add(W, "%s: nettóflötur vantar (engin herbergi fundust innan svæðisins)" % tag, r)
        nv = r.netto_value()
        if nv is not None and nv > r.flatur() + 0.05:
            add(W, "%s: nettóflötur %.1f er stærri en botnflötur %.1f" % (tag, nv, r.flatur()), r)
        if r.undir18 and r.undir18 > r.flatur() + 0.05:
            add(E, "%s: flötur undir 1,8 m er stærri en botnflötur" % tag, r)
        if r.sameign_sumra:
            if not r.is_eignarlina:
                add(W, "%s: sameign sumra er aðeins lesin af eignarlínu (rými = eignarhald)"
                    % tag, r)
            for code, rule in parse_sameign(r.sameign_sumra):
                y_referenced.add(code)
                if not RE_Y.match(code) or code == "Y0":
                    add(E, "%s: '%s' er ekki gilt Y-númer í sameign sumra" % (tag, code), r)
                elif code not in y_used:
                    add(W, "%s: sameign sumra %s - ekkert rými er með það eignarhald"
                        % (tag, code), r)
                if rule and rule not in ("S", "J", "P"):
                    add(E, "%s: reikniregla '%s' á að vera S, J eða P" % (tag, rule), r)

    seen = {}
    for s in staedi:
        if not RE_ELINE.match(s.number):
            issues.append(Issue(E, "Bílastæði '%s': númer á að vera bókstafur + 2 tölustafir (B01)"
                                % s.number, s.element_id, s.number))
        if s.number in seen:
            issues.append(Issue(E, "Bílastæði %s er tvítekið" % s.number, s.element_id, s.number))
        seen[s.number] = s
        if not s.y_code:
            issues.append(Issue(W, "Bílastæði %s: vantar sameign sumra (Y) bílageymslu"
                                % s.number, s.element_id, s.number))
        else:
            y_referenced.add(s.y_code)

    for code in sorted(y_used - y_referenced, key=y_sort_key):
        issues.append(Issue(W, "Sameign sumra %s: engin séreign er skráð sem eigandi "
                               "(setja %s í SKR_SameignSumra á eignarlínum)" % (code, code)))
    return issues
