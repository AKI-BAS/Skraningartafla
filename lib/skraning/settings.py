# -*- coding: utf-8 -*-
"""Settings: parameter names, area scheme, template, room-count keywords.

Stored as JSON in %APPDATA%\\pyRevit\\Skraningartafla_settings.json so each
user can change parameter names without touching the code. Missing keys fall
back to DEFAULTS, so new settings appear automatically after an update.
"""
from __future__ import unicode_literals

import io
import json
import os

EXT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_TEMPLATE = os.path.join(EXT_DIR, "templates", "Skraningartafla_5.03_tom.xlsm")

DEFAULTS = {
    "_lesa_mig": "Breyttu gildum hér og vistaðu. Eyddu skránni til að fá sjálfgefin gildi aftur.",

    # Where rýmislínur come from: "areas" (an Area Scheme) or "rooms".
    "uppruni": "areas",
    "area_scheme": "Skráning",
    "template": "",                     # empty = the bundled HMS 5.03 template

    # Parameter names on Areas / Rooms (one rýmislína each)
    "p_lokun": "SKR_Lokun",               # A / B / C            (D0, default A)
    "p_hofudflokkun": "SKR_Hofudflokkun", # N U T B F V S        (D3)
    "p_eignarhald": "SKR_Eignarhald",     # 0101 / X / Y / Y1    (D4)
    "p_milliflotur": "SKR_Milliflotur",   # Yes/No: area goes in D5M
    "p_stigar": "SKR_Stigar",             # m²                   (D6)
    "p_op": "SKR_Op",                     # m²                   (D7)
    "p_undir180": "SKR_Undir180",         # m² under 1,8 m       (D9)
    "p_salarhaed_min": "SKR_SalarhaedMin",  # m                  (D10a)
    "p_salarhaed_max": "SKR_SalarhaedMax",  # m                  (D10b)
    "p_nettoflotur": "SKR_Nettoflotur",   # m² override          (D12)
    "p_botnflotur": "SKR_Botnflotur",     # m² override          (D5)
    "p_reiknitala": "SKR_Reiknitala",     # override             (D14)
    "p_upphitad": "SKR_Upphitad",         # mælir nr. 1, 2...    (D16)
    "p_sameign_sumra": "SKR_SameignSumra",  # on eignarlína / bílastæði: "Y1; Y:J"
    "p_sleppa": "SKR_Sleppa",             # Yes/No: leave out of the table

    # Levels
    "p_haednumer": "SKR_Haednumer",       # "00", "01" ...
    "p_haedarheiti": "SKR_Haedarheiti",   # "Kjallari", "1. hæð" ...
    "p_salarhaed_haedar": "SKR_SalarhaedHaedar",  # m, default salarhæð for the floor

    # Project Information
    "p_heiti": "SKR_Heiti",               # empty -> Project Name
    "p_landeignanumer": "SKR_Landeignanumer",
    "p_stadgreinir": "SKR_Stadgreinir",
    "p_matshlutanumer": "SKR_Matshlutanumer",
    "p_fjoldi_matshluta": "SKR_FjoldiMatshluta",
    "p_skrasetjari": "SKR_Skrasetjari",
    "p_kennitala": "SKR_Kennitala",
    "p_lod": "SKR_Lod",                   # m²
    "p_efsti_koti": "SKR_EfstiKoti",      # m (hæðarkóti)
    "p_ummal": "SKR_Ummal",               # m
    "p_athugasemdir": "SKR_Athugasemdir", # one line per comment

    # Parking spaces (E-lines)
    "bilastaedi": True,                   # export Parking elements inside B rými
    "bilastaedi_notkun": "Bílastæði",

    # Options
    "fylla_reiknada_dalka": True,         # D8, D13, D14, D15 as formulas (as in the mockup)
    "aud_lina_milli_haeda": True,
    "salarhaed_haedarskil": True,         # no height param -> level-to-level height
    "reikna_hjupfleti": True,             # estimate walls / openings / roof for Matshluti
    "botnplata_thykkt": 0.2,              # m, botnplata m³ = m² x this
    "telja_herbergi": True,               # room counts T..AC (areas mode)

    # Room name -> count column. Checked in order; each prefix matches the
    # start of a word in the room name.
    "herbergi_lyklar": [
        ["Alrými", ["alrými", "alrym"]],
        ["Svefnherbergi", ["svefn"]],
        ["Baðherbergi", ["bað", "baðh"]],
        ["Snyrtingar", ["snyrting", "wc", "salerni"]],
        ["Eldhús", ["eldhús", "eldh"]],
        ["Stofur", ["stofa", "stofur", "borðstofa", "setustofa", "dagstofa"]],
        ["Þvottahús", ["þvott"]],
        ["Geymslur", ["geymsla", "geymslur", "geymsl"]],
        ["Önnur herbergi", ["herbergi", "vinnuherbergi", "skrifstofa"]]
    ],
}

PATH = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                    "pyRevit", "Skraningartafla_settings.json")


def load():
    data = dict(DEFAULTS)
    if os.path.exists(PATH):
        try:
            with io.open(PATH, "r", encoding="utf-8") as f:
                data.update(json.load(f))
        except Exception as ex:
            print("Gat ekki lesið stillingar {} ({}) - nota sjálfgefin gildi".format(PATH, ex))
    return data


def save(data):
    folder = os.path.dirname(PATH)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    text = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False)
    with io.open(PATH, "w", encoding="utf-8") as f:
        f.write(text if isinstance(text, type(u"")) else text.decode("utf-8"))


def template_path(data):
    p = data.get("template") or ""
    return p if p and os.path.exists(p) else DEFAULT_TEMPLATE
