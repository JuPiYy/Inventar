"""Structured XLSX export helpers."""

from datetime import datetime
from decimal import Decimal
import json
from copy import copy
from io import BytesIO

from openpyxl import Workbook
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter


EXPORT_VERSION = "2.0"

EQUIPMENT_HEADERS = [
    "EquipmentID", "AssetTag", "CategoryID", "Kategorie", "ModelName",
    "PurchaseDate", "StatusID", "Status", "LocationID", "Standort",
    "PurchasePrice", "CurrentValue", "WarrantyMonths", "Quantity", "Vendor",
    "ImageFile", "SpecsJSON", "Notes",
]
SPECS_HEADERS = ["EquipmentID", "Key", "Value", "ValueType"]
MAINTENANCE_HEADERS = [
    "LogID", "EquipmentID", "LogDate", "TypeID", "MaintenanceType",
    "Description", "Costs", "PerformedBy",
]
OVERVIEW_HEADERS = ["Kennzahl", "Wert"]
INFO_HEADERS = ["Eigenschaft", "Wert"]


def _json_value_type(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float, Decimal)):
        return "number"
    return "string"


def _json_specs(raw, equipment_id, warnings):
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        warnings.append(
            f"EquipmentID {equipment_id}: ungültiges SpecsJSON; Rohwert wurde erhalten."
        )
        return {}
    if not isinstance(parsed, dict):
        warnings.append(
            f"EquipmentID {equipment_id}: SpecsJSON ist kein Objekt; Rohwert wurde erhalten."
        )
        return {}
    specs = {}
    for key, value in parsed.items():
        if isinstance(value, (dict, list)):
            warnings.append(
                f"EquipmentID {equipment_id}: verschachtelter Specs-Wert für '{key}' "
                "wurde als JSON-Text exportiert."
            )
            value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        specs[str(key).strip()] = value
    return specs


def build_export_data(items, maintenance_logs, now=None):
    """Convert model instances into serializable export rows and metrics."""
    export_time = now or datetime.now()
    warnings = []
    equipment_rows = []
    specs_rows = []
    maintenance_rows = []
    total_value = Decimal("0")
    maintenance_costs = Decimal("0")

    for item in items:
        current_value = item.CurrentValue
        if current_value is not None:
            total_value += Decimal(str(current_value))
        raw_specs = item.Specs or ""
        equipment_rows.append([
            item.EquipmentID, item.AssetTag, item.CategoryID,
            item.category.name if item.category else "", item.ModelName,
            item.PurchaseDate, item.StatusID,
            item.status.name if item.status else "", item.LocationID,
            item.location.name if item.location else "", item.PurchasePrice,
            current_value, item.WarrantyMonths, item.Quantity or 1,
            item.Vendor, item.ImageFile, raw_specs, item.Notes,
        ])
        if not item.ImageFile:
            warnings.append(f"EquipmentID {item.EquipmentID}: Bild fehlt.")
        for key, value in _json_specs(raw_specs, item.EquipmentID, warnings).items():
            specs_rows.append([
                item.EquipmentID, key,
                value if value is not None else "",
                _json_value_type(value),
            ])

    equipment_ids = {item.EquipmentID for item in items}
    for log in maintenance_logs:
        if log.Costs is not None:
            maintenance_costs += Decimal(str(log.Costs))
        if log.EquipmentID not in equipment_ids:
            warnings.append(
                f"MaintenanceLog {log.LogID}: EquipmentID {log.EquipmentID} fehlt."
            )
        maintenance_rows.append([
            log.LogID, log.EquipmentID, log.LogDate, log.TypeID,
            log.maintenance_type.name if log.maintenance_type else "",
            log.Description, log.Costs, log.PerformedBy,
        ])

    overview = [
        ("Exportzeitpunkt", export_time),
        ("Equipmentanzahl", len(equipment_rows)),
        ("Spezifikationsanzahl", len(specs_rows)),
        ("Wartungsanzahl", len(maintenance_rows)),
        ("Gesamtwert", total_value),
        ("Wartungskosten", maintenance_costs),
        ("Fehlende Bilder", sum(not item.ImageFile for item in items)),
        ("JSON-Warnungen", sum("SpecsJSON" in warning for warning in warnings)),
        ("Warnungsanzahl", len(warnings)),
    ]
    return {
        "export_time": export_time,
        "equipment": equipment_rows,
        "specs": specs_rows,
        "maintenance": maintenance_rows,
        "overview": overview,
        "warnings": warnings,
    }


def _write_sheet(workbook, title, headers, rows):
    sheet = workbook.create_sheet(title)
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    if rows:
        ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"
        table = Table(displayName=f"{title.replace(' ', '')}Table", ref=ref)
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2", showFirstColumn=False,
            showLastColumn=False, showRowStripes=True, showColumnStripes=False,
        )
        sheet.add_table(table)
    for column in sheet.columns:
        values = [str(cell.value) if cell.value is not None else "" for cell in column]
        sheet.column_dimensions[get_column_letter(column[0].column)].width = min(
            max(len(value) for value in values) + 2, 60
        )
    return sheet


def render_xlsx(data):
    """Render structured export data to an in-memory XLSX document."""
    workbook = Workbook()
    del workbook[workbook.sheetnames[0]]
    _write_sheet(workbook, "Equipment", EQUIPMENT_HEADERS, data["equipment"])
    _write_sheet(workbook, "Spezifikationen", SPECS_HEADERS, data["specs"])
    _write_sheet(workbook, "Wartungen", MAINTENANCE_HEADERS, data["maintenance"])
    overview = _write_sheet(workbook, "Übersicht", OVERVIEW_HEADERS, data["overview"])
    _write_sheet(
        workbook, "Export-Info", INFO_HEADERS,
        [
            ("Exportzeitpunkt", data["export_time"]),
            ("Exportversion", EXPORT_VERSION),
            ("Quelle", "WSVINV-Datenbank"),
            ("Equipment-Datensätze", len(data["equipment"])),
            ("Spezifikations-Datensätze", len(data["specs"])),
            ("Wartungs-Datensätze", len(data["maintenance"])),
            ("Warnungen", "\n".join(data["warnings"]) or "Keine"),
        ],
    )
    overview.column_dimensions["B"].width = 28
    for sheet in workbook.worksheets:
        for cell in sheet[1]:
            font = copy(cell.font)
            font.bold = True
            cell.font = font
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output
