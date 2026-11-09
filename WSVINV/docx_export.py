"""Generate a user-friendly DOCX export for one equipment item."""

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
import json
import os
from typing import Iterable

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Inches, Pt, RGBColor


ACCENT = RGBColor(31, 78, 121)
MISSING = "Nicht angegeben"


def _display(value, fallback=MISSING):
    if value is None or value == "":
        return fallback
    return str(value)


def _date(value):
    if not value:
        return MISSING
    if isinstance(value, (datetime, date)):
        return value.strftime("%d.%m.%Y")
    return str(value)


def _money(value):
    if value is None or value == "":
        return MISSING
    try:
        return f"{Decimal(str(value)):.2f} €"
    except Exception:
        return str(value)


def _json_specs(item):
    raw = getattr(item, "Specs", None)
    if not raw:
        return []
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return [("Spezifikationen", "Ungültiges JSON-Format")]
    if not isinstance(parsed, dict):
        return [("Spezifikationen", _display(parsed))]
    return [(str(key), _display(value)) for key, value in parsed.items()]


def _set_cell(cell, text, *, header=False):
    cell.text = str(text)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    for paragraph in cell.paragraphs:
        paragraph.paragraph_format.space_after = Pt(0)
        for run in paragraph.runs:
            run.font.name = "Aptos"
            run.font.size = Pt(9 if not header else 9)
            run.font.bold = header
            if header:
                run.font.color.rgb = RGBColor(255, 255, 255)
    if header:
        shading = cell._tc.get_or_add_tcPr().add_new("w:shd")
        shading.set(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}fill",
            "1F4E79",
        )


def _table(document, headers, rows):
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for cell, header in zip(table.rows[0].cells, headers):
        _set_cell(cell, header, header=True)
    for row in rows:
        cells = table.add_row().cells
        for cell, value in zip(cells, row):
            _set_cell(cell, _display(value))
    return table


def build_docx(item, maintenance_logs: Iterable, image_path=None):
    """Return a seekable DOCX stream for *item* and its maintenance logs.

    Image failures are intentionally ignored: the data export remains useful even
    when an uploaded file has been deleted or is not a supported image format.
    """
    document = Document()
    section = document.sections[0]
    section.top_margin = Cm(1.8)
    section.bottom_margin = Cm(1.8)
    section.left_margin = Cm(2)
    section.right_margin = Cm(2)

    normal = document.styles["Normal"]
    normal.font.name = "Aptos"
    normal.font.size = Pt(10)
    title = document.add_heading(_display(getattr(item, "ModelName", None), "Gegenstand"), 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in title.runs:
        run.font.color.rgb = ACCENT
    subtitle = document.add_paragraph(f"Inventar-Export · {_display(getattr(item, 'AssetTag', None))}")
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER

    if image_path and os.path.isfile(image_path):
        try:
            paragraph = document.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.add_run().add_picture(image_path, width=Inches(4.8))
        except (OSError, ValueError, TypeError):
            pass

    document.add_heading("Gegenstandsdaten", level=1)
    rows = [
        ("Inventarnummer", getattr(item, "AssetTag", None)),
        ("Geräte-ID", getattr(item, "EquipmentID", None)),
        ("Modell", getattr(item, "ModelName", None)),
        ("Kategorie", getattr(getattr(item, "category", None), "name", None)),
        ("Status", getattr(getattr(item, "status", None), "name", None)),
        ("Standort", getattr(getattr(item, "location", None), "name", None)),
        ("Anzahl", getattr(item, "Quantity", None) or 1),
        ("Lieferant", getattr(item, "Vendor", None)),
        ("Kaufdatum", _date(getattr(item, "PurchaseDate", None))),
        ("Kaufpreis", _money(getattr(item, "PurchasePrice", None))),
        ("Aktueller Wert", _money(getattr(item, "CurrentValue", None))),
        ("Garantie (Monate)", getattr(item, "WarrantyMonths", None) or 0),
        ("Bemerkungen", getattr(item, "Notes", None)),
    ]
    rows.extend(_json_specs(item))
    _table(document, ("Bezeichnung", "Wert"), rows)

    document.add_page_break()
    document.add_heading("Wartungslog", level=1)
    logs = list(maintenance_logs or [])
    log_rows = [
        (
            _date(getattr(log, "LogDate", None)),
            getattr(getattr(log, "maintenance_type", None), "name", None),
            getattr(log, "Description", None),
            _money(getattr(log, "Costs", None)),
            getattr(log, "PerformedBy", None),
        )
        for log in logs
    ]
    if not log_rows:
        log_rows = [("Keine Einträge", MISSING, MISSING, MISSING, MISSING)]
    _table(
        document,
        ("Datum", "Wartungstyp", "Beschreibung", "Kosten", "Durchgeführt von"),
        log_rows,
    )

    output = BytesIO()
    document.save(output)
    output.seek(0)
    return output
