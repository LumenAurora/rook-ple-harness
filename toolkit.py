"""Task-agnostic engineering helpers installed into the PLE task container.

The harness copies this module to /tmp/ple_toolkit.py at the start of every
task. Use it from the task container with:

    python3 -c 'import sys; sys.path.insert(0, "/tmp"); import ple_toolkit as pk'

It has no network access, no task-specific data and only the standard library
as a hard dependency. Office/PDF writers degrade gracefully when the optional
libraries are not installed.
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
import zipfile
from typing import Any, Iterable, Sequence

# --------------------------------------------------------------------------
# Unit conversion. Every quantity is expressed as its SI base unit.
# --------------------------------------------------------------------------

FACTORS: dict[str, float] = {
    "mm": 0.001, "cm": 0.01, "m": 1.0, "km": 1000.0,
    "in": 0.0254, "ft": 0.3048, "yd": 0.9144, "mi": 1609.344,
    "mm2": 1e-6, "cm2": 1e-4, "m2": 1.0, "ft2": 0.09290304,
    "mm3": 1e-9, "cm3": 1e-6, "m3": 1.0, "l": 0.001,
    "gal_us": 0.003785411784,
    "g": 0.001, "kg": 1.0, "lb": 0.45359237,
    "n": 1.0, "kn": 1000.0, "kip": 4448.2216152605,
    "pa": 1.0, "kpa": 1000.0, "mpa": 1e6, "psi": 6894.757293168,
    "bar": 100000.0,
    "w": 1.0, "kw": 1000.0, "mw": 1e6, "hp": 745.6998715822702,
    "j": 1.0, "kj": 1000.0, "kwh": 3600000.0, "btu": 1055.05585262,
    "s": 1.0, "min": 60.0, "h": 3600.0, "day": 86400.0,
    "yr": 31557600.0,
}

DIMENSIONS: dict[str, set[str]] = {
    "length": {"mm", "cm", "m", "km", "in", "ft", "yd", "mi"},
    "area": {"mm2", "cm2", "m2", "ft2"},
    "volume": {"mm3", "cm3", "m3", "l", "gal_us"},
    "mass": {"g", "kg", "lb"},
    "force": {"n", "kn", "kip"},
    "pressure": {"pa", "kpa", "mpa", "psi", "bar"},
    "power": {"w", "kw", "mw", "hp"},
    "energy": {"j", "kj", "kwh", "btu"},
    "time": {"s", "min", "h", "day", "yr"},
}
DIM_OF = {unit: dim for dim, units in DIMENSIONS.items() for unit in units}


def convert(value: float, src: str, dst: str) -> float:
    """Converts value from src units to dst units, refusing mixed dimensions."""
    a, b = src.strip().lower(), dst.strip().lower()
    if a not in FACTORS or b not in FACTORS:
        raise ValueError("unknown unit: %r -> %r" % (src, dst))
    if DIM_OF[a] != DIM_OF[b]:
        raise ValueError(
            "incompatible dimensions: %s (%s) -> %s (%s)"
            % (src, DIM_OF[a], dst, DIM_OF[b])
        )
    return float(value) * FACTORS[a] / FACTORS[b]


def c_to_f(celsius: float) -> float:
    return float(celsius) * 9.0 / 5.0 + 32.0


def f_to_c(fahrenheit: float) -> float:
    return (float(fahrenheit) - 32.0) * 5.0 / 9.0


# --------------------------------------------------------------------------
# Numeric hygiene for drawing callouts, spreadsheet cells and code tables.
# --------------------------------------------------------------------------

_NUM = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def number(text: Any) -> float:
    """Extracts the first numeric value from a callout, cell or label."""
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)
    cleaned = str(text).replace(",", "").strip()
    match = _NUM.search(cleaned)
    if not match:
        raise ValueError("no number found in %r" % (text,))
    return float(match.group(0))


def close(a: float, b: float, rel: float = 1e-6, absolute: float = 1e-9) -> bool:
    return math.isclose(float(a), float(b), rel_tol=rel, abs_tol=absolute)


def check(
    value: float,
    *,
    lo: float | None = None,
    hi: float | None = None,
    target: float | None = None,
    tolerance: float = 1e-6,
    name: str = "value",
) -> dict[str, Any]:
    """Checks one numeric constraint and returns a machine-readable verdict."""
    v = float(value)
    ok = True
    reasons: list[str] = []
    if lo is not None and v < lo - tolerance:
        ok, _ = False, reasons.append("%s = %g below minimum %g" % (name, v, lo))
    if hi is not None and v > hi + tolerance:
        ok, _ = False, reasons.append("%s = %g above maximum %g" % (name, v, hi))
    if target is not None and not close(v, target, rel=tolerance):
        ok, _ = False, reasons.append(
            "%s = %g differs from expected %g" % (name, v, target)
        )
    return {"name": name, "value": v, "ok": ok, "reasons": reasons}


def constraint_report(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Aggregates check() verdicts; hard failures cap the achievable score."""
    hard = [r for r in rows if r.get("hard", True) and not r.get("ok", False)]
    soft = [r for r in rows if not r.get("hard", True) and not r.get("ok", False)]
    return {
        "total": len(rows),
        "passed": sum(1 for r in rows if r.get("ok", False)),
        "hard_violations": [r.get("name") for r in hard],
        "soft_violations": [r.get("name") for r in soft],
        "all_hard_constraints_met": not hard,
    }


# --------------------------------------------------------------------------
# Deliverable hygiene. Graders read only the declared deliverable paths.
# --------------------------------------------------------------------------

def ensure_parent(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def write_text(path: str, text: str) -> str:
    ensure_parent(path)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def write_json(path: str, obj: Any) -> str:
    return write_text(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def write_csv(path: str, rows: Iterable[Sequence[Any]], header: Sequence[Any] | None = None) -> str:
    ensure_parent(path)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if header is not None:
            writer.writerow(list(header))
        for row in rows:
            writer.writerow(list(row))
    return path


def inspect(paths: Sequence[str]) -> list[dict[str, Any]]:
    """Reports whether each declared deliverable exists and is readable."""
    out: list[dict[str, Any]] = []
    for path in paths:
        item: dict[str, Any] = {"path": path, "exists": os.path.exists(path)}
        if item["exists"]:
            item["is_dir"] = os.path.isdir(path)
            item["size"] = os.path.getsize(path) if os.path.isfile(path) else None
            if os.path.isfile(path):
                try:
                    with open(path, "rb") as handle:
                        head = handle.read(8192)
                    item["readable"] = True
                    item["empty"] = len(head) == 0
                    item["looks_binary"] = b"\x00" in head[:1024]
                    if path.lower().endswith(".json"):
                        json.loads(open(path, encoding="utf-8").read())
                        item["json_valid"] = True
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    item["readable"] = False
                    item["error"] = "%s: %s" % (type(exc).__name__, exc)
        out.append(item)
    return out


def make_zip(path: str, files: Sequence[tuple[str, str]]) -> str:
    """Packs (absolute_path, archive_name) pairs into a real zip archive."""
    ensure_parent(path)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for source, name in files:
            if os.path.isfile(source):
                archive.write(source, name)
    return path


def _xml_escape(value: Any) -> str:
    """Escapes text for OOXML inline strings."""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _col_letter(index: int) -> str:
    """Turns a 1-based column index into spreadsheet letters."""
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _xlsx_cell(ref: str, value: Any) -> str:
    if isinstance(value, bool):
        return '<c r="%s" t="inlineStr"><is><t>%s</t></is></c>' % (
            ref, "TRUE" if value else "FALSE"
        )
    if isinstance(value, (int, float)):
        return '<c r="%s"><v>%s</v></c>' % (ref, value)
    return (
        '<c r="%s" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
        % (ref, _xml_escape(value))
    )


def _ooxml_xlsx(path: str, sheets: dict[str, Sequence[Sequence[Any]]]) -> str:
    """Writes a valid multi-sheet .xlsx using only the standard library."""
    names = [str(name)[:31] or "Sheet%d" % (i + 1)
             for i, name in enumerate(sheets)] or ["Sheet1"]
    values = list(sheets.values()) or [[]]
    types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
    ]
    types.extend(
        '<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % (i + 1)
        for i in range(len(names))
    )
    types.append("</Types>")
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    sheet_tags = "".join(
        '<sheet name="%s" sheetId="%d" r:id="rId%d"/>'
        % (_xml_escape(name), i + 1, i + 1)
        for i, name in enumerate(names)
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>" + sheet_tags + "</sheets></workbook>"
    )
    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>'
            % (i + 1, i + 1)
            for i in range(len(names))
        )
        + "</Relationships>"
    )
    parts: dict[str, str] = {
        "[Content_Types].xml": "".join(types),
        "_rels/.rels": root_rels,
        "xl/workbook.xml": workbook,
        "xl/_rels/workbook.xml.rels": wb_rels,
    }
    for i, rows in enumerate(values, start=1):
        body = []
        for r, row in enumerate(rows, start=1):
            cells = "".join(
                _xlsx_cell("%s%d" % (_col_letter(c), r), value)
                for c, value in enumerate(row, start=1)
            )
            body.append('<row r="%d">%s</row>' % (r, cells))
        parts["xl/worksheets/sheet%d.xml" % i] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<sheetData>" + "".join(body) + "</sheetData></worksheet>"
        )
    ensure_parent(path)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return path


def _ooxml_docx(path: str, paragraphs: Sequence[str]) -> str:
    """Writes a valid .docx using only the standard library."""
    body = "".join(
        "<w:p><w:r><w:t xml:space=\"preserve\">%s</w:t></w:r></w:p>"
        % _xml_escape(line)
        for line in paragraphs
    )
    parts = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>"
        ),
        "word/document.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body>" + body + "<w:sectPr/></w:body></w:document>"
        ),
    }
    ensure_parent(path)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return path


def _minimal_pdf(path: str, lines: Sequence[str]) -> str:
    """Writes a valid single-page PDF using only the standard library."""
    def escaped(value: Any) -> str:
        return (
            str(value)
            .replace("\\", r"\\")
            .replace("(", r"\(")
            .replace(")", r"\)")
        )

    content = ["BT", "/F1 11 Tf", "14 TL", "50 750 Td"]
    for line in lines:
        content.append("(%s) Tj" % escaped(line))
        content.append("T*")
    content.append("ET")
    stream = "\n".join(content).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets[1:]:
        out += b"%010d 00000 n \n" % offset
    out += (
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objects) + 1, xref)
    )
    ensure_parent(path)
    with open(path, "wb") as handle:
        handle.write(bytes(out))
    return path


def write_docx(path: str, paragraphs: Sequence[str]) -> str:
    """Writes a real .docx, with or without python-docx installed."""
    ensure_parent(path)
    try:
        from docx import Document  # type: ignore

        doc = Document()
        for line in paragraphs:
            doc.add_paragraph(line)
        doc.save(path)
        return path
    except Exception:  # pylint: disable=broad-exception-caught
        return _ooxml_docx(path, paragraphs)


def write_xlsx(path: str, sheets: dict[str, Sequence[Sequence[Any]]]) -> str:
    """Writes a real .xlsx, with or without openpyxl installed."""
    ensure_parent(path)
    try:
        from openpyxl import Workbook  # type: ignore

        book = Workbook()
        book.remove(book.active)
        for name, rows in sheets.items():
            sheet = book.create_sheet(title=str(name)[:31])
            for row in rows:
                sheet.append(list(row))
        book.save(path)
        return path
    except Exception:  # pylint: disable=broad-exception-caught
        return _ooxml_xlsx(path, sheets)


def write_pdf(path: str, lines: Sequence[str]) -> str:
    """Writes a real PDF, with or without fpdf installed."""
    ensure_parent(path)
    try:
        from fpdf import FPDF  # type: ignore

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=11)
        for line in lines:
            pdf.multi_cell(0, 6, str(line))
        pdf.output(path)
        return path
    except Exception:  # pylint: disable=broad-exception-caught
        return _minimal_pdf(path, lines)


def life_cycle_cost(
    first_cost: float,
    annual_cost: float,
    years: float,
    discount_rate: float,
    residual: float = 0.0,
) -> dict[str, float]:
    """Present-value life-cycle cost, the usual 20- to 30-year study basis."""
    r = float(discount_rate)
    n = int(years)
    pv_annual = (
        annual_cost * (1.0 - (1.0 + r) ** (-n)) / r
        if abs(r) > 1e-12
        else annual_cost * n
    )
    pv_residual = residual / ((1.0 + r) ** n) if abs(r) > 1e-12 else residual
    total = float(first_cost) + pv_annual - pv_residual
    return {
        "first_cost": float(first_cost),
        "present_value_annual": pv_annual,
        "present_value_residual": pv_residual,
        "total_present_value": total,
    }


def voltage_drop_percent(
    current_a: float,
    length_m: float,
    resistance_ohm_per_m: float,
    phases: int,
    voltage_v: float,
    power_factor: float = 1.0,
) -> float:
    """Balanced feeder voltage drop in percent of nominal voltage."""
    drop_v = (
        phases * float(current_a) * float(length_m)
        * float(resistance_ohm_per_m) * float(power_factor)
    )
    return 100.0 * drop_v / float(voltage_v)
