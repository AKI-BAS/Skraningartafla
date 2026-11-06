# -*- coding: utf-8 -*-
"""Opna stillingaskrána (JSON) í Notepad."""
__title__ = "Stillingar"
__doc__ = ("Opnar stillingar (nöfn færibreyta, Area Scheme, sniðmát, lyklar fyrir herbergjatalningu). "
           "Eyddu skránni til að fá sjálfgefin gildi.")

import subprocess
from pyrevit import forms
from skraning import settings

s = settings.load()
settings.save(s)          # writes defaults for any missing keys
if forms.alert("Stillingar eru í:\n%s\n\nVelja annað sniðmát (.xlsm) en HMS 5.03 sem fylgir?"
               % settings.PATH, yes=True, no=True):
    path = forms.pick_file(file_ext="xlsm")
    if path:
        s["template"] = path
        settings.save(s)
subprocess.Popen(["notepad.exe", settings.PATH])
