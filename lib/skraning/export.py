# -*- coding: utf-8 -*-
"""The export / check commands (used by the pushbuttons)."""
from __future__ import unicode_literals

import datetime
import os
import re

from pyrevit import revit, forms, script

from skraning import core, settings, revit_collect

ROOMS_OPTION = "Herbergi (Rooms) - hvert herbergi er ein rýmislína"


def _choose_source(doc, s):
    schemes = revit_collect.area_schemes(doc)
    if not schemes:
        return "rooms"
    options = []
    pref = s.get("area_scheme")
    if pref in schemes:
        options.append("Svæði: " + pref)
    options += ["Svæði: " + n for n in schemes if n != pref]
    options.append(ROOMS_OPTION)
    if s.get("uppruni") == "rooms":
        options.remove(ROOMS_OPTION)
        options.insert(0, ROOMS_OPTION)
    pick = forms.CommandSwitchWindow.show(
        options, message="Hvaðan koma rýmislínurnar?")
    if not pick:
        script.exit()
    if pick == ROOMS_OPTION:
        return "rooms"
    s["area_scheme"] = pick.split(": ", 1)[1]
    return "areas"


def _link(out, issue):
    if issue.element_id is None:
        return ""
    try:
        return out.linkify(issue.element_id)
    except Exception:
        return ""


def _report(out, mode, s, rymi, staedi, issues, haedir, tot, env):
    out.print_md("# Skráningartafla - yfirlit úr líkani")
    src = ("Svæði (Area Scheme: **%s**)" % s.get("area_scheme")) if mode == "areas" \
        else "Herbergi (Rooms)"
    out.print_md("Uppruni: %s &nbsp;·&nbsp; **%d** rýmislínur &nbsp;·&nbsp; **%d** bílastæði (E-línur)"
                 % (src, len(rymi), len(staedi)))

    out.print_table(
        [[c, n, "%.1f" % b, "%.1f" % v] for c, n, b, v in haedir] +
        [["", "**Samtals A**", "%.1f" % tot["botn"], "%.1f" % tot["rummal"]]],
        columns=["Hæð", "Texti", "Botnflötur m² (A)", "Brúttórúmmál m³ (A)"],
        title="Hæðir")
    out.print_md("Brúttóflötur A: **%.1f m²** · Nettóflötur A: **%.1f m²** · Birt flatarmál: **%.1f m²**"
                 % (tot["brutto"], tot["netto"], tot["birt"]))
    if env:
        out.print_md("Hjúpfletir (áætlað úr líkani, yfirfarið!): útveggir %.1f m², þar af op %.1f m², "
                     "þak %.1f m², þar af þakop %.1f m²"
                     % (env["utveggir"], env["op"], env["thak"], env["thakop"]))

    order = {core.Issue.ERROR: 0, core.Issue.WARN: 1, core.Issue.INFO: 2}
    issues = sorted(issues, key=lambda i: (order.get(i.level, 9), i.number))
    n_err = len([i for i in issues if i.level == core.Issue.ERROR])
    n_warn = len([i for i in issues if i.level == core.Issue.WARN])
    if issues:
        out.print_table([[i.level, i.message, _link(out, i)] for i in issues],
                        columns=["", "Athugasemd", "Eining"],
                        title="Villuleit: %d villur, %d aðvaranir" % (n_err, n_warn))
    else:
        out.print_md("**Villuleit: engar villur fundust.**")

    rows = []
    for r in core.sort_rymi(rymi):
        rows.append([r.lokun, r.number, r.notkun, r.hofud, r.eignarhald,
                     "%.1f" % r.flatur(),
                     "" if r.mean_height() is None else "%.2f" % r.mean_height(),
                     "" if r.rummal() is None else "%.1f" % r.rummal(),
                     "" if r.netto_value() is None else "%.1f" % r.netto_value(),
                     "" if r.birt() is None else "%.1f" % r.birt(),
                     out.linkify(r.element_id) if r.element_id is not None else ""])
    out.print_table(rows, columns=["D0", "D1 Rými", "D2 Notkun", "D3", "D4 Eign",
                                   "D5 m²", "Salarh.", "D11 m³", "D12 m²", "D13 m²", ""],
                    title="Rýmislínur")
    return n_err


def _workbook_data(proj, s, rymi, staedi, haedir, env):
    rows, _ = core.einingar_rows(rymi, staedi,
                                 fill_calculated=s.get("fylla_reiknada_dalka", True),
                                 blank_between_floors=s.get("aud_lina_milli_haeda", True))
    forsida = {
        "E6": proj["heiti"],
        "E8": proj["landeign"],
        "I8": proj["stadgreinir"],
        "E9": proj["matshluti"],
        "E10": proj["fjoldi"],
        "E11": proj["skrasetjari"],
        "E12": core.text(proj["kennitala"]) if proj["kennitala"] else None,
        "E13": datetime.date.today(),
    }
    matshluti = {}
    if proj["lod"]:
        matshluti["B8"] = core.r1(proj["lod"])
    if haedir:
        lowest = haedir[0][2]
        if lowest:
            matshluti["D8"] = lowest
            matshluti["C8"] = core.r1(lowest * float(s.get("botnplata_thykkt", 0.2)))
    if env:
        for addr, key in (("E8", "utveggir"), ("F8", "op"), ("G8", "thak"), ("H8", "thakop")):
            if env.get(key):
                matshluti[addr] = core.r1(env[key])
    if proj["efsti_koti"]:
        matshluti["I8"] = core.r2(proj["efsti_koti"])
    if proj["ummal"]:
        matshluti["J8"] = core.r1(proj["ummal"])
    return {
        "forsida": forsida,
        "matshluti": matshluti,
        "haedir": haedir,
        "einingar": rows,
        "sameign": core.sameign_rows(rymi, staedi),
        "athugasemdir": proj["athugasemdir"],
    }


def _safe_name(s):
    return re.sub(r'[\\/:*?"<>|]+', "-", s or "").strip() or "Skraningartafla"


def run(check_only=False):
    doc = revit.doc
    out = script.get_output()
    out.set_width(1200)
    s = settings.load()

    mode = _choose_source(doc, s)
    with forms.ProgressBar(title="Les líkan...", indeterminate=True):
        rymi, staedi, issues, _ = revit_collect.collect(doc, s, mode)
        env = None
        if s.get("reikna_hjupfleti", True) and not check_only:
            try:
                env = revit_collect.envelope(doc)
            except Exception as ex:
                issues.append(core.Issue(core.Issue.INFO, "Hjúpfletir reiknuðust ekki: %s" % ex))
    if not rymi:
        forms.alert("Engar rýmislínur fundust.\n\nSvæði þurfa að vera staðsett (placed) og lokuð, "
                    "eða veldu Herbergi (Rooms).", exitscript=True)

    issues = issues + core.validate(rymi, staedi)
    haedir = core.haedir_rows(rymi)
    tot = core.totals(rymi)
    n_err = _report(out, mode, s, rymi, staedi, issues, haedir, tot, env)

    # remember the choice for next time
    s["uppruni"] = mode
    try:
        settings.save(s)
    except Exception:
        pass

    if check_only:
        return

    if n_err and not forms.alert("Villuleitin fann %d villur (sjá úttaksglugga).\n"
                                 "Flytja samt út í Excel?" % n_err,
                                 yes=True, no=True):
        return

    proj = revit_collect.project_data(doc, s)
    template = settings.template_path(s)
    if not os.path.exists(template):
        forms.alert("Sniðmát fannst ekki:\n%s" % template, exitscript=True)
    default = "%s Skráningartafla_%s.xlsm" % (
        _safe_name(proj["heiti"]), datetime.date.today().strftime("%d.%m.%Y"))
    target = forms.save_file(file_ext="xlsm", default_name=default)
    if not target:
        return
    if not target.lower().endswith(".xlsm"):
        target += ".xlsm"

    from skraning import excel_com
    data = _workbook_data(proj, s, rymi, staedi, haedir, env)
    with forms.ProgressBar(title="Skrifa í Excel...", indeterminate=True):
        try:
            excel_com.write_workbook(template, target, data)
        except Exception as ex:
            forms.alert("Gat ekki skrifað Excel skjalið:\n%s\n\n"
                        "Er skjalið opið í Excel?" % ex, exitscript=True)

    out.print_md("**Vistað:** `%s`" % target)
    out.print_md("Næstu skref í Excel: villutékka Einingar, ýta á **Reikna** á Forsíðu, "
                 "yfirfara Samantekt og Hjúpfleti á Matshluti.")
    if forms.alert("Skráningartafla vistuð:\n%s\n\nOpna í Excel?" % target, yes=True, no=True):
        os.startfile(target)
