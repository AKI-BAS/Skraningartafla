# -*- coding: utf-8 -*-
"""Búa til SKR_ færibreyturnar sem útflutningurinn les."""
__title__ = "Búa til\nfæribreytur"
__doc__ = ("Bætir SKR_ shared parameters við verkefnið: á Areas/Rooms (lokun, höfuðflokkun, "
           "eignarhald...), Levels (hæðarnúmer, heiti), Project Information (landeignanúmer...) "
           "og Parking (sameign sumra).")

from pyrevit import revit, script
from skraning import settings, revit_params

doc = revit.doc
s = settings.load()
with revit.Transaction("Skráningartafla: færibreytur"):
    rep = revit_params.ensure_parameters(doc, s)

out = script.get_output()
out.print_md("# Skráningartafla - færibreytur")
if rep["added"]:
    out.print_md("**Bætt við:** " + ", ".join(rep["added"]))
if rep["extended"]:
    out.print_md("**Fleiri flokkum bætt við:** " + ", ".join(rep["extended"]))
for p in rep["problems"]:
    out.print_md("**Vandamál:** " + p)
if not (rep["added"] or rep["extended"] or rep["problems"]):
    out.print_md("Allar færibreytur voru þegar til staðar.")
for key, kind, cats, desc in revit_params.definitions(s):
    out.print_md("- `%s` - %s" % (s.get(key), desc))
