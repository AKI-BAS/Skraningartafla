# -*- coding: utf-8 -*-
"""Read rýmislínur, bílastæði, floors and project data out of the Revit model.

Areas mode (default): every Area in the chosen Area Scheme is one rýmislína.
Its Area is the botnflötur (D5). Rooms whose location point lies inside the
Area (same level) give the nettóflötur (D12, sum of the rooms) and the room
counts (T..AC).

Rooms mode: every placed Room is one rýmislína; the Room area is used as
nettóflötur and, unless SKR_Botnflotur is filled in, also as botnflötur.
"""
from __future__ import unicode_literals

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (  # noqa: E402
    BuiltInCategory, BuiltInParameter, FilteredElementCollector, StorageType,
    SpatialElementBoundaryOptions, Wall, WallKind, WallFunction, FamilyInstance,
    Level, XYZ,
)

from skraning import core  # noqa: E402

FT = 0.3048


def _iid(eid):
    """ElementId -> int (ElementId.Value in Revit 2024+, IntegerValue before)."""
    if eid is None:
        return -1
    try:
        return int(eid.Value)
    except AttributeError:
        return eid.IntegerValue
FT2 = FT * FT


# --------------------------------------------------------------------------
# parameter helpers

def _param(el, name):
    if not name or el is None:
        return None
    try:
        return el.LookupParameter(name)
    except Exception:
        return None


def get_text(el, name):
    p = _param(el, name)
    if p is None or not p.HasValue:
        return ""
    if p.StorageType == StorageType.String:
        return (p.AsString() or "").strip()
    if p.StorageType == StorageType.Integer:
        return "%d" % p.AsInteger()
    if p.StorageType == StorageType.Double:
        return (p.AsValueString() or "").strip()
    return ""


def get_bool(el, name):
    p = _param(el, name)
    if p is None or not p.HasValue:
        return False
    if p.StorageType == StorageType.Integer:
        return p.AsInteger() == 1
    return get_text(el, name).lower() in ("1", "já", "ja", "yes", "true", "x")


def _get_double(el, name, factor):
    """Internal units -> metric. Text parameters are parsed ('3,23')."""
    p = _param(el, name)
    if p is None or not p.HasValue:
        return None
    if p.StorageType == StorageType.Double:
        v = p.AsDouble() * factor
        return v if v != 0 else None
    if p.StorageType == StorageType.Integer:
        v = p.AsInteger()
        return float(v) if v else None
    s = (p.AsString() or "").strip().replace(",", ".")
    try:
        return float(s) if s else None
    except ValueError:
        return None


def get_area(el, name):
    return _get_double(el, name, FT2)


def get_length(el, name):
    return _get_double(el, name, FT)


def get_number(el, name):
    return _get_double(el, name, 1.0)


# --------------------------------------------------------------------------
# geometry

def _loops(spatial):
    """Boundary loops as lists of (x, y) in feet."""
    out = []
    try:
        segs = spatial.GetBoundarySegments(SpatialElementBoundaryOptions())
    except Exception:
        return out
    if segs is None:
        return out
    for loop in segs:
        pts = []
        for s in loop:
            for p in s.GetCurve().Tessellate():
                pts.append((p.X, p.Y))
        if len(pts) >= 3:
            out.append(pts)
    return out


def _inside(loops, x, y):
    """Even-odd test over all loops (holes count automatically)."""
    inside = False
    for pts in loops:
        n = len(pts)
        j = n - 1
        for i in range(n):
            xi, yi = pts[i]
            xj, yj = pts[j]
            if (yi > y) != (yj > y):
                xc = (xj - xi) * (y - yi) / (yj - yi) + xi
                if x < xc:
                    inside = not inside
            j = i
    return inside


def _point(el):
    try:
        loc = el.Location
        return loc.Point
    except Exception:
        return None


# --------------------------------------------------------------------------
# levels

def _is_story(level):
    p = level.get_Parameter(BuiltInParameter.LEVEL_IS_BUILDING_STORY)
    return p is not None and p.HasValue and p.AsInteger() == 1


class FloorInfo(object):
    def __init__(self, doc, levels_used, s):
        self.s = s
        self.levels = {}
        all_lv = sorted(FilteredElementCollector(doc).OfClass(Level),
                        key=lambda l: l.Elevation)
        used = set(_iid(i) for i in levels_used)
        # levels that count as floors: used by rýmislínur, or given a hæðarnúmer
        story = [l for l in all_lv
                 if _iid(l.Id) in used or get_text(l, s["p_haednumer"])]
        for idx, lv in enumerate(story):
            nxt = story[idx + 1] if idx + 1 < len(story) else None
            if nxt is None:      # top floor: next Building Story level (e.g. roof)
                above = [l for l in all_lv if l.Elevation > lv.Elevation + 0.01
                         and _is_story(l)]
                nxt = above[0] if above else None
            h = get_length(lv, s["p_salarhaed_haedar"])
            if h is None and nxt is not None and s.get("salarhaed_haedarskil", True):
                h = (nxt.Elevation - lv.Elevation) * FT
            self.levels[_iid(lv.Id)] = {
                "code": get_text(lv, s["p_haednumer"]),
                "name": get_text(lv, s["p_haedarheiti"]),
                "elev": lv.Elevation * FT,
                "height": h,
                "level_name": lv.Name,
            }

    def get(self, level_id):
        return self.levels.get(_iid(level_id) if level_id else -1, {})


# --------------------------------------------------------------------------
# collection

def area_schemes(doc):
    names = set()
    for a in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Areas) \
            .WhereElementIsNotElementType():
        try:
            names.add(a.AreaScheme.Name)
        except Exception:
            pass
    return sorted(names)


def _spatial_elements(doc, s, mode):
    if mode == "rooms":
        els = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Rooms) \
            .WhereElementIsNotElementType()
        return [r for r in els if r.Area > 0 and not get_bool(r, s["p_sleppa"])]
    scheme = s.get("area_scheme")
    els = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Areas) \
        .WhereElementIsNotElementType()
    out = []
    for a in els:
        try:
            if a.AreaScheme.Name != scheme:
                continue
        except Exception:
            continue
        if a.Area > 0 and not get_bool(a, s["p_sleppa"]):
            out.append(a)
    return out


def _number(el):
    p = el.get_Parameter(BuiltInParameter.ROOM_NUMBER)
    return (p.AsString() if p is not None else "") or ""


def _name(el):
    p = el.get_Parameter(BuiltInParameter.ROOM_NAME)
    return (p.AsString() if p is not None else "") or ""


def collect(doc, s, mode="areas"):
    """Returns (rymi, staedi, issues, floor_info)."""
    issues = []
    els = _spatial_elements(doc, s, mode)
    floor_info = FloorInfo(doc, [e.LevelId for e in els], s)
    keywords = [(k, v) for k, v in s.get("herbergi_lyklar", [])]

    rooms_by_level = {}
    if mode == "areas":
        for r in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Rooms) \
                .WhereElementIsNotElementType():
            if r.Area <= 0 or get_bool(r, s["p_sleppa"]):
                continue
            pt = _point(r)
            if pt is None:
                continue
            rooms_by_level.setdefault(_iid(r.LevelId), []).append(r)

    loops_of = {}
    used_rooms = set()
    rymi = []
    for el in els:
        num = _number(el)
        lv = floor_info.get(el.LevelId)
        h_level = lv.get("height")
        hmin = get_length(el, s["p_salarhaed_min"])
        hmax = get_length(el, s["p_salarhaed_max"])
        if hmin is None and hmax is None and h_level is not None:
            hmin = hmax = h_level
        area_m2 = el.Area * FT2
        botn = get_area(el, s["p_botnflotur"]) or area_m2
        netto = get_area(el, s["p_nettoflotur"])
        parts, counts = [], {}
        if mode == "rooms":
            if netto is None:
                netto = area_m2
        else:
            loops = _loops(el)
            loops_of[_iid(el.Id)] = loops
            for room in rooms_by_level.get(_iid(el.LevelId), []):
                pt = _point(room)
                if _inside(loops, pt.X, pt.Y):
                    used_rooms.add(_iid(room.Id))
                    parts.append(room.Area * FT2)
                    if s.get("telja_herbergi", True):
                        col = core.classify_room(_name(room), keywords)
                        counts[col] = counts.get(col, 0) + 1
        upph = get_number(el, s["p_upphitad"])
        r = core.Rymi(
            number=num,
            notkun=_name(el),
            lokun=get_text(el, s["p_lokun"]) or "A",
            hofud=get_text(el, s["p_hofudflokkun"]),
            eignarhald=get_text(el, s["p_eignarhald"]),
            botn=botn,
            milli=get_bool(el, s["p_milliflotur"]),
            stigar=get_area(el, s["p_stigar"]),
            op=get_area(el, s["p_op"]),
            undir18=get_area(el, s["p_undir180"]),
            hmin=hmin, hmax=hmax,
            netto=netto, netto_parts=parts,
            reiknitala=get_number(el, s["p_reiknitala"]),
            upphitad=int(upph) if upph else None,
            floor_code=lv.get("code") or num[:2],
            floor_name=lv.get("name") or None,
            floor_elev=lv.get("elev", 0.0),
            sameign_sumra=get_text(el, s["p_sameign_sumra"]),
            counts=counts,
            element_id=el.Id,
        )
        rymi.append(r)

    if mode == "areas":
        for lvl_id, rooms in rooms_by_level.items():
            for room in rooms:
                if _iid(room.Id) not in used_rooms and \
                        any(_iid(e.LevelId) == lvl_id for e in els):
                    issues.append(core.Issue(
                        core.Issue.WARN,
                        "Herbergi %s %s er ekki innan neins svæðis (Area) - telst ekki með í nettóflöt"
                        % (_number(room), _name(room)), room.Id, _number(room)))

    staedi = []
    if s.get("bilastaedi", True):
        staedi = _collect_parking(doc, s, mode, els, rymi, loops_of, issues)
    return rymi, staedi, issues, floor_info


def _collect_parking(doc, s, mode, els, rymi, loops_of, issues):
    """Parking elements standing inside a B (bílgeymsla) rýmislína."""
    garages = []
    for el, r in zip(els, rymi):
        if r.hofud == "B" and not r.is_sereign:
            garages.append((el, r))
    if not garages:
        return []
    out = []
    unnumbered = []
    for p in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Parking) \
            .WhereElementIsNotElementType():
        pt = _point(p)
        if pt is None:
            continue
        host = None
        for el, r in garages:
            if mode == "rooms":
                try:
                    if el.IsPointInRoom(XYZ(pt.X, pt.Y, pt.Z + 1.0)):
                        host = r
                except Exception:
                    pass
            elif _iid(el.LevelId) == _iid(p.LevelId) and _inside(loops_of.get(_iid(el.Id), []),
                                                     pt.X, pt.Y):
                host = r
            if host:
                break
        if host is None:
            continue
        num = get_text(p, s["p_sameign_sumra"] and "Mark") or \
            (p.get_Parameter(BuiltInParameter.ALL_MODEL_MARK).AsString() or "")
        y = get_text(p, s["p_sameign_sumra"]) or host.eignarhald
        st = core.Staedi(num.strip().upper(), y, s.get("bilastaedi_notkun", "Bílastæði"), p.Id)
        if st.number:
            out.append(st)
        else:
            unnumbered.append((pt.Y, pt.X, st))
    if unnumbered:
        # number them B01.. after the highest existing number, by position
        unnumbered.sort(key=lambda t: (-t[0], t[1]))
        used = set(st.number for st in out)
        i = 1
        for _, _, st in unnumbered:
            while "B%02d" % i in used:
                i += 1
            st.number = "B%02d" % i
            used.add(st.number)
            out.append(st)
        issues.append(core.Issue(
            core.Issue.WARN,
            "%d bílastæði voru án númers (Mark) og fengu númer sjálfkrafa - setja Mark í líkanið"
            % len(unnumbered)))
    return out


# --------------------------------------------------------------------------
# project info / envelope

def project_data(doc, s):
    pi = doc.ProjectInformation
    heiti = get_text(pi, s["p_heiti"]) or (pi.Name or "") or (pi.Address or "")

    def num_or(name, default):
        v = get_number(pi, name)
        return int(v) if v else default

    return {
        "heiti": heiti,
        "landeign": get_text(pi, s["p_landeignanumer"]),
        "stadgreinir": get_text(pi, s["p_stadgreinir"]),
        "matshluti": num_or(s["p_matshlutanumer"], 1),
        "fjoldi": num_or(s["p_fjoldi_matshluta"], 1),
        "skrasetjari": get_text(pi, s["p_skrasetjari"]) or (pi.Author or ""),
        "kennitala": get_text(pi, s["p_kennitala"]),
        "lod": get_area(pi, s["p_lod"]),
        "efsti_koti": get_number(pi, s["p_efsti_koti"]),
        "ummal": get_length(pi, s["p_ummal"]),
        "athugasemdir": [l.strip() for l in
                         get_text(pi, s["p_athugasemdir"]).replace("\r", "").split("\n")
                         if l.strip()],
    }


def _opening_area(fi):
    """Width x height of a window/door in m² (instance, then type params)."""
    w = h = None
    for el in (fi, fi.Symbol):
        if el is None:
            continue
        for bip in (BuiltInParameter.FAMILY_ROUGH_WIDTH_PARAM, BuiltInParameter.FAMILY_WIDTH_PARAM,
                    BuiltInParameter.DOOR_WIDTH, BuiltInParameter.WINDOW_WIDTH):
            p = el.get_Parameter(bip)
            if w is None and p is not None and p.HasValue and p.AsDouble() > 0:
                w = p.AsDouble()
        for bip in (BuiltInParameter.FAMILY_ROUGH_HEIGHT_PARAM, BuiltInParameter.FAMILY_HEIGHT_PARAM,
                    BuiltInParameter.DOOR_HEIGHT, BuiltInParameter.WINDOW_HEIGHT):
            p = el.get_Parameter(bip)
            if h is None and p is not None and p.HasValue and p.AsDouble() > 0:
                h = p.AsDouble()
    if w and h:
        return w * h * FT2
    return 0.0


def envelope(doc):
    """Estimated hjúpfletir for Matshluti (m²): walls incl. openings,
    openings, roof, roof openings. Approximate - always check."""
    walls = op = roof = roof_op = 0.0
    ext_ids = set()
    for w in FilteredElementCollector(doc).OfClass(Wall):
        try:
            wt = w.WallType
            if wt.Function != WallFunction.Exterior:
                continue
        except Exception:
            continue
        p = w.get_Parameter(BuiltInParameter.HOST_AREA_COMPUTED)
        a = p.AsDouble() * FT2 if p is not None and p.HasValue else 0.0
        if wt.Kind == WallKind.Curtain:
            walls += a
            op += a
            continue
        walls += a
        ext_ids.add(_iid(w.Id))
    roof_ids = set()
    for r in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Roofs) \
            .WhereElementIsNotElementType():
        p = r.get_Parameter(BuiltInParameter.HOST_AREA_COMPUTED)
        if p is not None and p.HasValue:
            roof += p.AsDouble() * FT2
        roof_ids.add(_iid(r.Id))
    for cat in (BuiltInCategory.OST_Windows, BuiltInCategory.OST_Doors):
        for fi in FilteredElementCollector(doc).OfCategory(cat).OfClass(FamilyInstance):
            host = fi.Host
            if host is None:
                continue
            hid = _iid(host.Id)
            if hid in ext_ids:
                a = _opening_area(fi)
                op += a
                walls += a          # wall area in Revit excludes the cut
            elif hid in roof_ids:
                roof_op += _opening_area(fi)
    return {"utveggir": walls, "op": op, "thak": roof, "thakop": roof_op}
