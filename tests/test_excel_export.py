import json
import random
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from openpyxl import load_workbook

from WSVINV.excel_export import build_export_data, render_xlsx


def equipment(equipment_id, specs, image="photo.png"):
    return SimpleNamespace(
        EquipmentID=equipment_id, AssetTag=f"TAG-{equipment_id}",
        CategoryID=1, category=SimpleNamespace(name="Boote"),
        ModelName="Modell 🚣", PurchaseDate=date(2025, 1, 2),
        StatusID=2, status=SimpleNamespace(name="Aktiv"),
        LocationID=3, location=SimpleNamespace(name="Lager"),
        PurchasePrice=Decimal("100.50"), CurrentValue=Decimal("80.25"),
        WarrantyMonths=12, Quantity=1, Vendor="Händler & Co.",
        ImageFile=image, Specs=specs, Notes="Notiz",
    )


def maintenance(log_id=10, equipment_id=1):
    return SimpleNamespace(
        LogID=log_id, EquipmentID=equipment_id, LogDate=datetime(2025, 2, 3, 4, 5),
        TypeID=4, maintenance_type=SimpleNamespace(name="Inspektion"),
        Description="Prüfung", Costs=Decimal("12.34"), PerformedBy="Ärger",
    )


def test_xlsx_structure_and_values():
    data = build_export_data(
        [equipment(1, json.dumps({"Farbe": "Blau", "Anzahl": 2, "Aktiv": True}))],
        [maintenance()],
        now=datetime(2025, 3, 4, 5, 6),
    )
    workbook = load_workbook(render_xlsx(data))

    assert workbook.sheetnames == [
        "Equipment", "Spezifikationen", "Wartungen", "Übersicht", "Export-Info"
    ]
    equipment_sheet = workbook["Equipment"]
    assert equipment_sheet.max_row == 2
    assert equipment_sheet["A2"].value == 1
    assert equipment_sheet["L2"].value == Decimal("80.25")
    assert equipment_sheet["F2"].value.date() == date(2025, 1, 2)
    assert equipment_sheet["Q2"].value.startswith("{")
    assert equipment_sheet.freeze_panes == "A2"
    assert equipment_sheet.auto_filter.ref == "A1:R2"
    assert len(equipment_sheet.tables) == 1

    specs_sheet = workbook["Spezifikationen"]
    assert specs_sheet.max_row == 4
    assert {(row[1].value, row[3].value) for row in specs_sheet.iter_rows(min_row=2)} == {
        ("Farbe", "string"), ("Anzahl", "number"), ("Aktiv", "boolean")
    }
    maintenance_sheet = workbook["Wartungen"]
    assert maintenance_sheet.max_row == 2
    assert maintenance_sheet["B2"].value == 1
    assert maintenance_sheet["C2"].value == datetime(2025, 2, 3, 4, 5)
    assert Decimal(str(maintenance_sheet["G2"].value)) == Decimal("12.34")

    overview = dict(workbook["Übersicht"].iter_rows(min_row=2, values_only=True))
    assert overview["Equipmentanzahl"] == 1
    assert overview["Spezifikationsanzahl"] == 3
    assert overview["Gesamtwert"] == Decimal("80.25")
    assert Decimal(str(overview["Wartungskosten"])) == Decimal("12.34")


def test_invalid_json_missing_image_and_orphan_maintenance_are_warned():
    data = build_export_data(
        [equipment(1, "{invalid", image="")],
        [maintenance(equipment_id=999)],
    )
    assert data["equipment"][0][16] == "{invalid"
    assert len(data["specs"]) == 0
    assert any("ungültiges SpecsJSON" in warning for warning in data["warnings"])
    assert any("Bild fehlt" in warning for warning in data["warnings"])
    assert any("fehlt" in warning for warning in data["warnings"])
    info = load_workbook(render_xlsx(data))["Export-Info"]
    warning_text = "\n".join(str(row[1].value) for row in info.iter_rows(min_row=2))
    assert "ungültiges SpecsJSON" in warning_text


def test_empty_data_has_headers_and_no_data_rows():
    workbook = load_workbook(render_xlsx(build_export_data([], [])))
    for sheet_name in workbook.sheetnames[:3]:
        sheet = workbook[sheet_name]
        assert sheet.max_row == 1
        assert sheet.freeze_panes == "A2"
        assert not sheet.tables


def test_deterministic_fuzz_payloads_are_flat_and_bounded():
    rng = random.Random(20261109)
    for index in range(50):
        payload = {
            f" Schlüssel {index} ": rng.choice(
                ["äöü 🚣 !@#", index, True, None, "x" * (index % 25)]
            )
        }
        data = build_export_data(
            [equipment(index + 1, json.dumps(payload, ensure_ascii=False))], []
        )
        assert len(data["specs"]) == 1
        assert data["specs"][0][0] == index + 1
    nested_specs = json.dumps({"nested": {"x": 1}})
    data = build_export_data([equipment(1, nested_specs)], [])
    assert data["specs"][0][2] == '{"x":1}'
    assert data["specs"][0][3] == "string"
