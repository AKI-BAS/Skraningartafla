# -*- coding: utf-8 -*-
"""Write Excel files through Excel itself (COM automation).

Using Excel (instead of writing the file directly) keeps the skráningartafla
template's macros, buttons and data validation intact, so the user can open
the result and press "Reikna" as usual.

In pyRevit (IronPython on .NET 8, Revit 2025+) the COM object returned by
Activator.CreateInstance has no dynamic members ("'__ComObject' object has no
attribute 'Visible'"), so every call goes through IDispatch with
Type.InvokeMember. The small get/put/call helpers below hide that; in CPython
(tests) they map to pywin32 attribute access.
"""
from __future__ import unicode_literals

import os
import shutil
import datetime

try:                                    # IronPython / pyRevit
    import clr  # noqa: F401
    from System import Type, Activator, Array, Object, GC
    from System.Reflection import BindingFlags
    from System.Runtime.InteropServices import Marshal
    _DOTNET = True
except ImportError:                     # CPython + pywin32 (tests)
    _DOTNET = False

from skraning import core

MSO_AUTOMATION_SECURITY_FORCE_DISABLE = 3
XL_CALC_MANUAL = -4135
XL_CALC_AUTOMATIC = -4105
XL_OPENXML_WORKBOOK = 51


# --------------------------------------------------------------------------
# late-bound COM helpers

def _args(a):
    if not _DOTNET:
        return a
    arr = Array.CreateInstance(Object, len(a))
    for i, v in enumerate(a):
        arr[i] = v
    return arr


def _invoke(obj, name, flags, args):
    return obj.GetType().InvokeMember(name, flags, None, obj, _args(args))


def get(obj, name, *args):
    """Property get (with optional index arguments, e.g. Range("A1"))."""
    if _DOTNET:
        return _invoke(obj, name, BindingFlags.GetProperty, args)
    v = getattr(obj, name)
    return v(*args) if args else v


def put(obj, name, value):
    if _DOTNET:
        _invoke(obj, name, BindingFlags.SetProperty, (value,))
    else:
        setattr(obj, name, value)


def call(obj, name, *args):
    if _DOTNET:
        return _invoke(obj, name, BindingFlags.InvokeMethod, args)
    return getattr(obj, name)(*args)


def _try(fn, *a):
    try:
        return fn(*a)
    except Exception:
        return None


def _col_letter(i):
    """0 -> A, 28 -> AC"""
    s = ""
    i += 1
    while i:
        i, rem = divmod(i - 1, 26)
        s = chr(65 + rem) + s
    return s


def _make_2d(rows, ncols):
    if _DOTNET:
        arr = Array.CreateInstance(Object, len(rows), ncols)
        for i, row in enumerate(rows):
            for j in range(ncols):
                v = row[j] if j < len(row) else None
                if v is not None:
                    arr[i, j] = v
        return arr
    return tuple(tuple((row[j] if j < len(row) else None) for j in range(ncols))
                 for row in rows)


def _start_excel():
    if _DOTNET:
        t = Type.GetTypeFromProgID("Excel.Application")
        if t is None:
            raise RuntimeError("Excel fannst ekki á þessari tölvu.")
        return Activator.CreateInstance(t)
    import win32com.client
    return win32com.client.DispatchEx("Excel.Application")


def _prepare(xl):
    put(xl, "Visible", False)
    put(xl, "DisplayAlerts", False)
    put(xl, "ScreenUpdating", False)
    _try(put, xl, "AutomationSecurity", MSO_AUTOMATION_SECURITY_FORCE_DISABLE)


def _shutdown(xl, wb):
    if wb is not None:
        _try(call, wb, "Close", False)
    if xl is not None:
        _try(put, xl, "EnableEvents", True)
        _try(put, xl, "ScreenUpdating", True)
        _try(call, xl, "Quit")
    if _DOTNET:
        for o in (wb, xl):
            if o is not None:
                _try(Marshal.FinalReleaseComObject, o)
        GC.Collect()
        GC.WaitForPendingFinalizers()


def _sheets(wb):
    sheets = get(wb, "Worksheets")
    return [get(sheets, "Item", i + 1) for i in range(int(get(sheets, "Count")))]


def _sheet(wb, name):
    for ws in _sheets(wb):
        if get(ws, "Name") == name:
            return ws
    raise RuntimeError("Vinnublaðið '%s' fannst ekki í sniðmátinu." % name)


def _rng(ws, addr):
    return get(ws, "Range", addr)


def _write_block(ws, top_left_row, first_col, rows, ncols):
    """rows: list of lists. Writes formulas/values in one call."""
    if not rows:
        return
    a = "%s%d" % (_col_letter(first_col), top_left_row)
    b = "%s%d" % (_col_letter(first_col + ncols - 1), top_left_row + len(rows) - 1)
    put(_rng(ws, "%s:%s" % (a, b)), "Formula", _make_2d(rows, ncols))


def _set(ws, addr, value):
    if value is None or value == "":
        return
    put(_rng(ws, addr), "Formula", value)


def _clear(ws, addr):
    call(_rng(ws, addr), "ClearContents")


# --------------------------------------------------------------------------
# plain overview workbook

def write_plain_workbook(out_path, sheets):
    """New .xlsx with one worksheet per entry of `sheets`
    ({"name", "headers", "rows", "formats": {col: fmt}, "note"}). Plain values."""
    xl = wb = None
    if os.path.exists(out_path):
        os.remove(out_path)
    try:
        xl = _start_excel()
        _prepare(xl)
        old_n = get(xl, "SheetsInNewWorkbook")
        put(xl, "SheetsInNewWorkbook", len(sheets))
        try:
            wb = call(get(xl, "Workbooks"), "Add")
        finally:
            put(xl, "SheetsInNewWorkbook", old_n)
        wss = _sheets(wb)
        for ws, sh in zip(wss, sheets):
            put(ws, "Name", sh["name"][:31])
            ncols = len(sh["headers"])
            last_col = _col_letter(ncols - 1)
            top = 1
            if sh.get("note"):
                cell = _rng(ws, "A1")
                put(cell, "Value2", sh["note"])
                put(get(cell, "Font"), "Italic", True)
                top = 3
            _write_block(ws, top, 0, [sh["headers"]], ncols)
            hdr = _rng(ws, "A%d:%s%d" % (top, last_col, top))
            put(get(hdr, "Font"), "Bold", True)
            put(get(hdr, "Interior"), "Color", 0xEBD9C6)     # light blue (BGR)
            put(hdr, "WrapText", True)
            rows = sh["rows"]
            if rows:
                last = top + len(rows)
                for col, fmt in sh.get("formats", {}).items():
                    c = _col_letter(col)
                    put(_rng(ws, "%s%d:%s%d" % (c, top + 1, c, last)), "NumberFormat", fmt)
                _write_block(ws, top + 1, 0, rows, ncols)
            data = _rng(ws, "A%d:%s%d" % (top, last_col, top + max(len(rows), 1)))
            _try(call, data, "AutoFilter")
            call(get(data, "Columns"), "AutoFit")
            for c in range(ncols):                # keep long text columns readable
                col = get(_rng(ws, "%s1" % _col_letter(c)), "EntireColumn")
                if float(get(col, "ColumnWidth")) > 60:
                    put(col, "ColumnWidth", 60)
            try:
                call(ws, "Activate")
                win = get(xl, "ActiveWindow")
                put(win, "SplitRow", top)
                put(win, "SplitColumn", 0)
                put(win, "FreezePanes", True)
            except Exception:
                pass
        call(wss[0], "Activate")
        call(wb, "SaveAs", out_path, XL_OPENXML_WORKBOOK)
    finally:
        _shutdown(xl, wb)
    return out_path


# --------------------------------------------------------------------------
# skráningartafla (template copy)

def write_workbook(template, out_path, data):
    """data: dict with keys
        forsida   {cell: value}
        matshluti {cell: value}
        haedir    [(code, name, botn, rummal)]
        einingar  [[29 values]]
        sameign   [(eignarhald, notkun, Y, Y notkun, regla)]
        athugasemdir [line, ...]
    """
    if os.path.abspath(template) != os.path.abspath(out_path):
        shutil.copyfile(template, out_path)

    xl = wb = None
    try:
        xl = _start_excel()
        _prepare(xl)
        wb = call(get(xl, "Workbooks"), "Open", out_path)
        put(xl, "EnableEvents", False)    # Einingar has a Worksheet_Change checker
        _try(put, xl, "Calculation", XL_CALC_MANUAL)

        # Forsíða
        ws = _sheet(wb, "Forsíða")
        for addr, v in sorted(data.get("forsida", {}).items()):
            if isinstance(v, datetime.date):
                put(_rng(ws, addr), "NumberFormat", "dd.mm.yyyy")
                v = "=DATE(%d,%d,%d)" % (v.year, v.month, v.day)
            _set(ws, addr, v)
        try:                             # keep the date a value, not a formula
            cell = _rng(ws, "E13")
            put(cell, "Value2", get(cell, "Value2"))
        except Exception:
            pass

        # Matshluti (sheet is protected, the input cells B8:J8 are not)
        ws = _sheet(wb, "Matshluti")
        for addr, v in sorted(data.get("matshluti", {}).items()):
            _set(ws, addr, v)

        # Hæðir: A9.. (no blank lines between floors)
        ws = _sheet(wb, "Hæðir")
        _clear(ws, "A9:D60")
        rows = [[core.text(c), n, b or None, v or None]
                for c, n, b, v in data.get("haedir", [])]
        _write_block(ws, 9, 0, rows, 4)

        # Einingar
        ws = _sheet(wb, "Einingar")
        rows = data.get("einingar", [])
        _clear(ws, "A%d:AC%d" % (core.FIRST_ROW, max(core.FIRST_ROW + len(rows) + 50, 300)))
        _write_block(ws, core.FIRST_ROW, 0, rows, core.N_COLS)

        # Sameign sumra: B..F from row 8, no blank lines
        ws = _sheet(wb, "Sameign_sumra")
        _clear(ws, "B8:G400")
        rows = [[core.text(e) if core.RE_SEREIGN.match(e) else e, n, y, yn, rule]
                for e, n, y, yn, rule in data.get("sameign", [])]
        _write_block(ws, 8, 1, rows, 5)

        # Athugasemdir: A8..
        ws = _sheet(wb, "Athugasemdir")
        lines = [[l] for l in data.get("athugasemdir", [])]
        _write_block(ws, 8, 0, lines, 1)

        _try(put, xl, "Calculation", XL_CALC_AUTOMATIC)
        call(_sheet(wb, "Forsíða"), "Activate")
        call(wb, "Save")
    finally:
        _shutdown(xl, wb)
    return out_path
