# -*- coding: utf-8 -*-
"""Create the SKR_ shared parameters the export reads.

The parameters are made from a temporary shared parameter file with fixed
GUIDs (derived from the name), so schedules/tags made in one project work in
the next. The user's own shared parameter file setting is restored afterwards.
"""
from __future__ import unicode_literals

import os
import tempfile
import uuid

import clr
clr.AddReference("RevitAPI")
from System import Guid  # noqa: E402
from Autodesk.Revit.DB import (  # noqa: E402
    BuiltInCategory, Category, ExternalDefinitionCreationOptions,
)

GROUP_NAME = "Skraningartafla"
_NS = uuid.UUID("6f0c1c1e-5b1a-4d3e-9a52-2b8c7f3e0a11")

SPATIAL = (BuiltInCategory.OST_Areas, BuiltInCategory.OST_Rooms)
LEVELS = (BuiltInCategory.OST_Levels,)
PROJECT = (BuiltInCategory.OST_ProjectInformation,)
PARKING = (BuiltInCategory.OST_Parking,)


def definitions(s):
    """(settings key, kind, categories, description)"""
    return [
        ("p_lokun", "text", SPATIAL, "D0 Lokun: A, B eða C (tómt = A)"),
        ("p_hofudflokkun", "text", SPATIAL, "D3 Höfuðflokkun: N, U, T, B, F, V eða S"),
        ("p_eignarhald", "text", SPATIAL, "D4 Eignarhald: rýmisnúmer eignar, X eða Y, Y1, Y2..."),
        ("p_sameign_sumra", "text", SPATIAL + PARKING,
         "Á eignarlínu: hvaða sameignum sumra eignin á hlut í, t.d. 'Y1' eða 'Y; Y1:S'. "
         "Á bílastæði: Y-númer bílageymslu (tómt = eignarhald bílageymslu)"),
        ("p_milliflotur", "yesno", SPATIAL, "Flatarmál fer í D5M (milliflötur) í stað D5"),
        ("p_stigar", "area", SPATIAL, "D6 Flatarmál stiga í rýminu"),
        ("p_op", "area", SPATIAL, "D7 Flatarmál opa (stigaop o.fl. > 1 m²)"),
        ("p_undir180", "area", SPATIAL, "D9 Brúttóflötur með salarhæð undir 1,80 m"),
        ("p_salarhaed_min", "length", SPATIAL, "D10a Minnsta salarhæð (tómt = hæð milli hæðarskila)"),
        ("p_salarhaed_max", "length", SPATIAL, "D10b Mesta salarhæð (tómt = hæð milli hæðarskila)"),
        ("p_nettoflotur", "area", SPATIAL, "D12 Nettóflötur - yfirskrifar summu herbergja"),
        ("p_botnflotur", "area", SPATIAL, "D5 Botnflötur - yfirskrifar flatarmál svæðis/rýmis"),
        ("p_reiknitala", "number", SPATIAL, "D14 Reiknitala skiptarúmmáls (aðeins í undantekningum)"),
        ("p_upphitad", "integer", SPATIAL, "D16 Upphitað rými: númer mælis 1, 2..."),
        ("p_sleppa", "yesno", SPATIAL, "Sleppa þessu svæði/herbergi í skráningartöflu"),
        ("p_haednumer", "text", LEVELS, "Hæðarnúmer: 00, 01, 02..."),
        ("p_haedarheiti", "text", LEVELS, "Heiti hæðar: Kjallari, 1. hæð..."),
        ("p_salarhaed_haedar", "length", LEVELS, "Salarhæð hæðar (nauðsynlegt á efstu hæð)"),
        ("p_heiti", "text", PROJECT, "Heiti landeignar (tómt = Project Name)"),
        ("p_landeignanumer", "text", PROJECT, "Landeignanúmer, t.d. L123456"),
        ("p_stadgreinir", "text", PROJECT, "Staðgreinir"),
        ("p_matshlutanumer", "integer", PROJECT, "Matshlutanúmer"),
        ("p_fjoldi_matshluta", "integer", PROJECT, "Fjöldi matshluta á landeign"),
        ("p_skrasetjari", "text", PROJECT, "Skrásetjari"),
        ("p_kennitala", "text", PROJECT, "Kennitala skrásetjara"),
        ("p_lod", "area", PROJECT, "Stærð lóðar m²"),
        ("p_efsti_koti", "number", PROJECT, "Efsti hæðarkóti byggingar"),
        ("p_ummal", "length", PROJECT, "Ummál ofanjarðar"),
        ("p_athugasemdir", "multiline", PROJECT, "Athugasemdir - ein lína á hverja athugasemd"),
    ]


def _spec(kind):
    from Autodesk.Revit.DB import SpecTypeId
    return {
        "text": SpecTypeId.String.Text,
        "multiline": SpecTypeId.String.MultilineText,
        "length": SpecTypeId.Length,
        "area": SpecTypeId.Area,
        "number": SpecTypeId.Number,
        "integer": SpecTypeId.Int.Integer,
        "yesno": SpecTypeId.Boolean.YesNo,
    }[kind]


def _bound(doc):
    out = {}
    it = doc.ParameterBindings.ForwardIterator()
    while it.MoveNext():
        out[it.Key.Name] = (it.Key, it.Current)
    return out


def ensure_parameters(doc, s):
    """Add the missing SKR_ parameters (and missing categories on existing
    ones). Call inside a transaction. Returns {"added", "extended", "problems"}."""
    from Autodesk.Revit.DB import GroupTypeId
    report = {"added": [], "extended": [], "problems": []}
    have = _bound(doc)
    app = doc.Application

    def catset(cats):
        cs = app.Create.NewCategorySet()
        for bic in cats:
            c = Category.GetCategory(doc, bic)
            if c is not None and c.AllowsBoundParameters:
                cs.Insert(c)
        return cs

    todo = []
    for key, kind, cats, desc in definitions(s):
        name = s.get(key)
        if not name:
            continue
        if name in have:
            definition, binding = have[name]
            missing = [b for b in cats if not _has_cat(doc, binding, b)]
            if missing:
                cs = binding.Categories
                for bic in missing:
                    c = Category.GetCategory(doc, bic)
                    if c is not None:
                        cs.Insert(c)
                binding.Categories = cs
                try:
                    doc.ParameterBindings.ReInsert(definition, binding, GroupTypeId.Data)
                    report["extended"].append(name)
                except Exception as ex:
                    report["problems"].append("%s: %s" % (name, ex))
            continue
        todo.append((name, kind, cats, desc))
    if not todo:
        return report

    original = app.SharedParametersFilename
    path = os.path.join(tempfile.gettempdir(), "Skraningartafla_SharedParameters.txt")
    if not os.path.exists(path):
        open(path, "w").close()
    try:
        app.SharedParametersFilename = path
        sp = app.OpenSharedParameterFile()
        if sp is None:
            raise RuntimeError("Gat ekki opnað shared parameter skrá: " + path)
        group = sp.Groups.get_Item(GROUP_NAME) or sp.Groups.Create(GROUP_NAME)
        for name, kind, cats, desc in todo:
            d = group.Definitions.get_Item(name)
            if d is None:
                opts = ExternalDefinitionCreationOptions(name, _spec(kind))
                opts.GUID = Guid(str(uuid.uuid5(_NS, name)))
                opts.Description = desc
                d = group.Definitions.Create(opts)
            binding = app.Create.NewInstanceBinding(catset(cats))
            try:
                ok = doc.ParameterBindings.Insert(d, binding, GroupTypeId.Data)
            except Exception:
                ok = doc.ParameterBindings.Insert(d, binding)
            (report["added"] if ok else report["problems"]).append(
                name if ok else "%s: Revit hafnaði" % name)
    finally:
        try:
            app.SharedParametersFilename = original or ""
        except Exception:
            pass
    return report


def _has_cat(doc, binding, bic):
    c = Category.GetCategory(doc, bic)
    return c is None or binding.Categories.Contains(c)
