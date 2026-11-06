# -*- coding: utf-8 -*-
"""Fill a copy of the HMS skráningartafla template through Excel (COM).

Using Excel itself (instead of writing the file directly) keeps the
template's macros, buttons and data validation intact, so the user can open
the result and press "Reikna" as usual.

Works in pyRevit's IronPython (late-bound COM through .NET) and, for testing,
in CPython with pywin32.
"""
from __future__ import unicode_literals

import os
import shutil
import datetime

try:                                    # IronPython / pyRevit
    import clr  # noqa: F401
    from System import Type, Activator, Array, Object
    from System.Runtime.InteropServices import Marshal
    _DOTNET = True
except ImportError:                     # CPython + pywin32 (tests)
    _DOTNET = False

from skraning import core

MSO_AUTOMATION_SECURITY_FORCE_DISABLE = 3
XL_CALC_MANUAL = -4135
XL_CALC_AUTOMATIC = -4105


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


def _release(obj):
    if _DOTNET and obj is not None:
        try:
            Marshal.ReleaseComObject(obj)
        except Exception:
            pass


def _sheet(wb, name):
    sheets = wb.Worksheets
    for get in (lambda: sheets(name), lambda: sheets[name], lambda: sheets.Item(name)):
        try:
            ws = get()
            if ws is not None and ws.Name == name:
                return ws
        except Exception:
            pass
    for ws in sheets:
        if ws.Name == name:
            return ws
    raise RuntimeError("Vinnublaðið '%s' fannst ekki í sniðmátinu." % name)


def _rng(ws, addr):
    """ws.Range(addr): call syntax (pywin32 / IronPython), else index syntax."""
    try:
        return ws.Range(addr)
    except Exception:
        return ws.Range[addr]


def _write_block(ws, top_left_row, first_col, rows, ncols):
    """rows: list of lists. Writes formulas/values in one call."""
    if not rows:
        return
    a = "%s%d" % (_col_letter(first_col), top_left_row)
    b = "%s%d" % (_col_letter(first_col + ncols - 1), top_left_row + len(rows) - 1)
    _rng(ws, "%s:%s" % (a, b)).Formula = _make_2d(rows, ncols)


def _set(ws, addr, value):
    if value is None or value == "":
        return
    _rng(ws, addr).Formula = value


def _clear(ws, addr):
    _rng(ws, addr).ClearContents()


XL_OPENXML_WORKBOOK = 51


def _sheet_at(wb, index):
    """1-based worksheet by position."""
    for i, ws in enumerate(wb.Worksheets):
        if i + 1 == index:
            return ws
    raise RuntimeError("Vinnublað %d vantar" % index)


def write_plain_workbook(out_path, sheets):
    """New .xlsx with one worksheet per entry of `sheets`
    ({"name", "headers", "rows", "formats": {col: fmt}, "note"}). Plain values."""
    xl = wb = None
    if os.path.exists(out_path):
        os.remove(out_path)
    try:
        xl = _start_excel()
        xl.Visible = False
        xl.DisplayAlerts = False
        xl.ScreenUpdating = False
        old_n = xl.SheetsInNewWorkbook
        xl.SheetsInNewWorkbook = len(sheets)
        try:
            wb = xl.Workbooks.Add()
        finally:
            xl.SheetsInNewWorkbook = old_n
        for i, sh in enumerate(sheets):
            ws = _sheet_at(wb, i + 1)
            ws.Name = sh["name"][:31]
            ncols = len(sh["headers"])
            top = 1
            if sh.get("note"):
                _rng(ws, "A1").Value2 = sh["note"]
                _rng(ws, "A1").Font.Italic = True
                top = 3
            _write_block(ws, top, 0, [sh["headers"]], ncols)
            hdr = _rng(ws, "A%d:%s%d" % (top, _col_letter(ncols - 1), top))
            hdr.Font.Bold = True
            hdr.Interior.Color = 0xEBD9C6          # light blue (BGR)
            hdr.WrapText = True
            rows = sh["rows"]
            if rows:
                last = top + len(rows)
                for col, fmt in sh.get("formats", {}).items():
                    _rng(ws, "%s%d:%s%d" % (_col_letter(col), top + 1,
                                            _col_letter(col), last)).NumberFormat = fmt
                _write_block(ws, top + 1, 0, rows, ncols)
            data = _rng(ws, "A%d:%s%d" % (top, _col_letter(ncols - 1), top + max(len(rows), 1)))
            try:
                data.AutoFilter()
            except Exception:
                pass
            data.Columns.AutoFit()
            for c in range(ncols):                # keep long text columns readable
                col = _rng(ws, "%s1" % _col_letter(c)).EntireColumn
                if col.ColumnWidth > 60:
                    col.ColumnWidth = 60
            try:
                ws.Activate()
                xl.ActiveWindow.SplitRow = top
                xl.ActiveWindow.SplitColumn = 0
                xl.ActiveWindow.FreezePanes = True
            except Exception:
                pass
        _sheet_at(wb, 1).Activate()
        wb.SaveAs(out_path, XL_OPENXML_WORKBOOK)
    finally:
        if wb is not None:
            try:
                wb.Close(False)
            except Exception:
                pass
        if xl is not None:
            try:
                xl.ScreenUpdating = True
                xl.Quit()
            except Exception:
                pass
        _release(wb)
        _release(xl)
    return out_path


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
        xl.Visible = False
        xl.DisplayAlerts = False
        xl.ScreenUpdating = False
        try:
            xl.AutomationSecurity = MSO_AUTOMATION_SECURITY_FORCE_DISABLE
        except Exception:
            pass
        wb = xl.Workbooks.Open(out_path)
        xl.EnableEvents = False          # Einingar has a Worksheet_Change checker
        try:
            xl.Calculation = XL_CALC_MANUAL
        except Exception:
            pass

        # Forsíða
        ws = _sheet(wb, "Forsíða")
        for addr, v in sorted(data.get("forsida", {}).items()):
            if isinstance(v, datetime.date):
                _rng(ws, addr).NumberFormat = "dd.mm.yyyy"
                v = "=DATE(%d,%d,%d)" % (v.year, v.month, v.day)
            _set(ws, addr, v)
        try:                             # keep the date a value, not a formula
            cell = _rng(ws, "E13")
            cell.Value2 = cell.Value2
        except Exception:
            pass

        # Matshluti (sheet is protected, the input cells B8:J8 are not)
        ws = _sheet(wb, "Matshluti")
        for addr, v in sorted(data.get("matshluti", {}).items()):
            _set(ws, addr, v)

        # Hæðir: A9.. (line 7 empty, no blank lines between floors)
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

        try:
            xl.Calculation = XL_CALC_AUTOMATIC
        except Exception:
            pass
        _sheet(wb, "Forsíða").Activate()
        wb.Save()
    finally:
        if wb is not None:
            try:
                wb.Close(False)
            except Exception:
                pass
        if xl is not None:
            try:
                xl.EnableEvents = True
                xl.ScreenUpdating = True
                xl.Quit()
            except Exception:
                pass
        _release(wb)
        _release(xl)
    return out_path
