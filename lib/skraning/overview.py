# -*- coding: utf-8 -*-
"""Raw overview export: everything the model knows about rooms, areas,
floors, stairs, openings and parking, as plain values in a normal .xlsx.

This is for filling in / double-checking the skráningartafla by hand. It does
not depend on the Area Scheme being set up correctly: every Room and every
Area (all schemes) is listed on its own.
"""
from __future__ import unicode_literals

import datetime
import os

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (  # noqa: E402
    BuiltInCategory, BuiltInParameter, FilteredElementCollector, Level, Opening,
)

from pyrevit import revit, forms, script  # noqa: E402

from skraning import core, settings, revit_collect as rc, overview_tables as ot  # noqa: E402
from skraning.revit_collect import FT, FT2, _iid, _loops, _inside, _point, get_text  # noqa: E402

FT3 = FT ** 3
F1, F2 = ot.F1, ot.F2


def _p_double(el, bip, factor):
    try:
        p = el.get_Parameter(bip)
        if p is not None and p.HasValue:
            return p.AsDouble() * factor
    except Exception:
        pass
    return None


def _p_text(el, bip):
    try:
        p = el.get_Parameter(bip)
        if p is not None and p.HasValue:
            return (p.AsString() or p.AsValueString() or "").strip()
    except Exception:
        pass
    return ""


def _level_name(doc, level_id):
    try:
        lv = doc.GetElement(level_id)
        return lv.Name if lv is not None else ""
    except Exception:
        return ""


def _poly_area(pts):
    """Shoelace on (x, y) feet -> m²."""
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0 * FT2


def _curves_area(curves):
    pts = []
    for c in curves:
        try:
            for p in c.Tessellate():
                pts.append((p.X, p.Y))
        except Exception:
            pass
    return _poly_area(pts) if len(pts) >= 3 else None


def _status(el):
    if el.Location is None:
        return "Ekki staðsett"
    if el.Area <= 0:
        return "Ekki lokað / tvítekið"
    return ""


def _skr(el, s):
    return [get_text(el, s["p_lokun"]) or None, get_text(el, s["p_hofudflokkun"]) or None,
            core.text(get_text(el, s["p_eignarhald"]))]


# --------------------------------------------------------------------------

class _AreaIndex(object):
    """Areas of one scheme, per level, to find which Area a point is in."""

    def __init__(self, areas):
        self.by_level = {}
        for a in areas:
            if a.Area > 0:
                self.by_level.setdefault(_iid(a.LevelId), []).append((a, _loops(a)))

    def find(self, level_id, x, y):
        for a, loops in self.by_level.get(_iid(level_id), []):
            if _inside(loops, x, y):
                return a
        return None


def _collect(doc, s):
    rooms = list(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Rooms)
                 .WhereElementIsNotElementType())
    areas = list(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Areas)
                 .WhereElementIsNotElementType())
    schemes = rc.area_schemes(doc)
    scheme = s.get("area_scheme") if s.get("area_scheme") in schemes else \
        (schemes[0] if schemes else None)
    idx = _AreaIndex([a for a in areas if scheme and a.AreaScheme.Name == scheme])
    sheets = []

    # ---- Herbergi -------------------------------------------------------
    rows, rooms_in_area = [], {}
    for r in rooms:
        pt = _point(r)
        host = idx.find(r.LevelId, pt.X, pt.Y) if (pt is not None and r.Area > 0) else None
        if host is not None:
            rooms_in_area.setdefault(_iid(host.Id), []).append(r)
        lv = doc.GetElement(r.LevelId)
        rows.append([
            _level_name(doc, r.LevelId), ot._v(lv.Elevation * FT, 2) if lv else None,
            core.text(rc._number(r)), rc._name(r),
            ot._v(r.Area * FT2) or None, ot._v(r.Perimeter * FT, 2) or None,
            ot._v(r.UnboundedHeight * FT, 2) or None, ot._v(r.Volume * FT3) or None,
            _p_text(r, BuiltInParameter.ROOM_DEPARTMENT) or None,
            core.text(rc._number(host)) if host else None, rc._name(host) if host else None,
        ] + _skr(r, s) + [_status(r) or None, _iid(r.Id)])
    rows.sort(key=lambda x: (x[1] if x[1] is not None else 0, x[2] or ""))
    sheets.append(ot.sheet(
        "Herbergi",
        ["Hæð (Level)", "Kóti m", "Númer", "Heiti", "Flatarmál m²", "Ummál m",
         "Lofthæð m", "Rúmmál m³", "Deild", "Í svæði (%s)" % (scheme or "-"), "Heiti svæðis",
         "SKR Lokun", "SKR Höfuðfl.", "SKR Eignarhald", "Staða", "Element Id"],
        rows, {1: F2, 4: F1, 5: F2, 6: F2, 7: F1},
        note="Rúmmál er aðeins reiknað ef 'Area and Volume computations' er stillt á rúmmál."))

    # ---- Svæði (all schemes) -------------------------------------------
    rows = []
    for a in areas:
        try:
            sch = a.AreaScheme.Name
        except Exception:
            sch = ""
        lv = doc.GetElement(a.LevelId)
        inside = rooms_in_area.get(_iid(a.Id), []) if sch == scheme else []
        netto = sum(core.r1(x.Area * FT2) for x in inside)
        rows.append([
            sch, _level_name(doc, a.LevelId), ot._v(lv.Elevation * FT, 2) if lv else None,
            core.text(rc._number(a)), rc._name(a),
            ot._v(a.Area * FT2) or None, ot._v(a.Perimeter * FT, 2) or None,
            ot._v(netto) or None, len(inside) or None,
            "; ".join("%s %s %.1f" % (rc._number(x), rc._name(x), x.Area * FT2)
                      for x in sorted(inside, key=rc._number)) or None,
        ] + _skr(a, s) + [get_text(a, s["p_sameign_sumra"]) or None,
                          _status(a) or None, _iid(a.Id)])
    rows.sort(key=lambda x: (x[0], x[2] if x[2] is not None else 0, x[3] or ""))
    sheets.append(ot.sheet(
        "Svæði",
        ["Area Scheme", "Hæð (Level)", "Kóti m", "Númer", "Heiti", "Flatarmál m²", "Ummál m",
         "Nettó (summa herb.)", "Fj. herb.", "Herbergi innan svæðis",
         "SKR Lokun", "SKR Höfuðfl.", "SKR Eignarhald", "SKR Sameign sumra", "Staða",
         "Element Id"],
        rows, {2: F2, 5: F1, 6: F2, 7: F1},
        note="Herbergi eru tengd svæðum í '%s' eftir staðsetningarpunkti herbergis." % scheme
        if scheme else "Engin svæði (Areas) í líkaninu."))

    # ---- Hæðir ----------------------------------------------------------
    levels = sorted(FilteredElementCollector(doc).OfClass(Level), key=lambda l: l.Elevation)
    room_sum, area_sum = {}, {}
    for r in rooms:
        if r.Area > 0:
            k = _iid(r.LevelId)
            room_sum[k] = room_sum.get(k, 0.0) + r.Area * FT2
    for a in areas:
        if a.Area > 0 and scheme and a.AreaScheme.Name == scheme:
            k = _iid(a.LevelId)
            area_sum[k] = area_sum.get(k, 0.0) + a.Area * FT2
    rows = []
    for i, lv in enumerate(levels):
        nxt = levels[i + 1] if i + 1 < len(levels) else None
        k = _iid(lv.Id)
        rows.append([lv.Name, ot._v(lv.Elevation * FT, 3),
                     ot._v((nxt.Elevation - lv.Elevation) * FT, 3) if nxt else None,
                     "Já" if rc._is_story(lv) else "",
                     core.text(get_text(lv, s["p_haednumer"])), get_text(lv, s["p_haedarheiti"]) or None,
                     ot._v(rc.get_length(lv, s["p_salarhaed_haedar"]), 2),
                     ot._v(room_sum.get(k)), ot._v(area_sum.get(k)), _iid(lv.Id)])
    sheets.append(ot.sheet(
        "Hæðir",
        ["Level", "Kóti m", "Hæð að næsta level m", "Building Story", "SKR Hæðarnúmer",
         "SKR Hæðarheiti", "SKR Salarhæð hæðar", "Herbergi alls m²",
         "Svæði alls m² (%s)" % (scheme or "-"), "Element Id"],
        rows, {1: "0.000", 2: "0.000", 6: F2, 7: F1, 8: F1}))

    # ---- Stigar og op ---------------------------------------------------
    rows = []
    for st in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Stairs) \
            .WhereElementIsNotElementType():
        foot, how = None, ""
        try:
            parts = [doc.GetElement(i) for i in st.GetStairsRuns()] + \
                    [doc.GetElement(i) for i in st.GetStairsLandings()]
            tot = 0.0
            for p in parts:
                a = _curves_area(list(p.GetFootprintBoundary()))
                tot += a or 0.0
            if tot > 0:
                foot, how = tot, "Hlaup + pallar"
        except Exception:
            pass
        if foot is None:
            bb = st.get_BoundingBox(None)
            if bb is None:
                continue                      # sub-elements (runs etc.) without geometry
            foot = (bb.Max.X - bb.Min.X) * (bb.Max.Y - bb.Min.Y) * FT2
            how = "Umlykjandi kassi (gróft)"
        host = None
        bb = st.get_BoundingBox(None)
        base_id = None
        try:
            base_id = st.get_Parameter(BuiltInParameter.STAIRS_BASE_LEVEL_PARAM).AsElementId()
        except Exception:
            pass
        if bb is not None and base_id is not None:
            c = (bb.Min + bb.Max) / 2.0
            host = idx.find(base_id, c.X, c.Y)
        rows.append([
            "Stigi", st.Category.Name if st.Category else "",
            _level_name(doc, base_id) if base_id else "",
            _level_name(doc, st.get_Parameter(BuiltInParameter.STAIRS_TOP_LEVEL_PARAM).AsElementId())
            if st.get_Parameter(BuiltInParameter.STAIRS_TOP_LEVEL_PARAM) else "",
            ot._v(foot), how, getattr(st, "ActualRisersNumber", None),
            ot._v(getattr(st, "Height", 0) * FT, 2) or None,
            core.text(rc._number(host)) if host else None, _iid(st.Id)])
    for op in FilteredElementCollector(doc).OfClass(Opening):
        area = None
        try:
            if op.IsRectBoundary:
                a, b = op.BoundaryRect[0], op.BoundaryRect[1]
                area = abs((b.X - a.X) * (b.Y - a.Y)) * FT2 or None
            else:
                area = _curves_area(list(op.BoundaryCurves))
        except Exception:
            pass
        host = getattr(op, "Host", None)
        lvl = _p_text(op, BuiltInParameter.WALL_BASE_CONSTRAINT) or \
            (_level_name(doc, host.LevelId) if host is not None and hasattr(host, "LevelId") else "")
        rows.append(["Op", op.Category.Name if op.Category else "", lvl,
                     _p_text(op, BuiltInParameter.WALL_HEIGHT_TYPE) or None,
                     ot._v(area), "Útlína ops", None, None, None, _iid(op.Id)])
    sheets.append(ot.sheet(
        "Stigar og op",
        ["Tegund", "Flokkur", "Neðsta hæð", "Efsta hæð", "Grunnflötur m²", "Reiknað út frá",
         "Fj. uppstiga", "Hæð m", "Í svæði", "Element Id"],
        rows, {4: F1, 7: F2},
        note="Grunnflötur stiga er fótspor hlaupa og palla (eða gróft umlykjandi box). "
             "Notið til að fylla D6 Stigar / D7 Op handvirkt."))

    # ---- Bílastæði ------------------------------------------------------
    rows = []
    for p in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Parking) \
            .WhereElementIsNotElementType():
        pt = _point(p)
        host = idx.find(p.LevelId, pt.X, pt.Y) if pt is not None else None
        try:
            tname = doc.GetElement(p.GetTypeId()).get_Parameter(
                BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
        except Exception:
            tname = ""
        rows.append([core.text(_p_text(p, BuiltInParameter.ALL_MODEL_MARK)),
                     _level_name(doc, p.LevelId), tname,
                     core.text(rc._number(host)) if host else None,
                     rc._name(host) if host else None,
                     core.text(get_text(p, s["p_sameign_sumra"])), _iid(p.Id)])
    rows.sort(key=lambda x: (x[0] or "~"))
    sheets.append(ot.sheet("Bílastæði", ["Mark", "Hæð", "Gerð", "Í svæði", "Heiti svæðis",
                                         "SKR Sameign sumra", "Element Id"], rows))
    return sheets, scheme


def run():
    doc = revit.doc
    out = script.get_output()
    s = settings.load()
    with forms.ProgressBar(title="Les líkan...", indeterminate=True):
        sheets, scheme = _collect(doc, s)
        # the calculated rýmislínur, as the main export would write them
        try:
            mode = "areas" if scheme else "rooms"
            if scheme:
                s["area_scheme"] = scheme
            rymi, _, _, _ = rc.collect(doc, s, mode)
            if rymi:
                sheets.insert(0, ot.rymi_sheet(rymi))
                sheets.insert(1, ot.owner_sheet(rymi))
        except Exception as ex:
            out.print_md("Rýmislínur reiknuðust ekki: %s" % ex)

    proj = rc.project_data(doc, s)
    default = "%s Yfirlit rýma_%s.xlsx" % (
        (proj["heiti"] or "Likan").replace("/", "-").replace("\\", "-"),
        datetime.date.today().strftime("%d.%m.%Y"))
    target = forms.save_file(file_ext="xlsx", default_name=default)
    if not target:
        return
    if not target.lower().endswith(".xlsx"):
        target += ".xlsx"

    from skraning import excel_com
    with forms.ProgressBar(title="Skrifa í Excel...", indeterminate=True):
        try:
            excel_com.write_plain_workbook(target, sheets)
        except Exception as ex:
            forms.alert("Gat ekki skrifað Excel skjalið:\n%s\n\nEr skjalið opið í Excel?" % ex,
                        exitscript=True)
    out.print_md("**Vistað:** `%s`" % target)
    for sh in sheets:
        out.print_md("- %s: %d línur" % (sh["name"], len(sh["rows"])))
    if forms.alert("Yfirlit vistað:\n%s\n\nOpna í Excel?" % target, yes=True, no=True):
        os.startfile(target)
