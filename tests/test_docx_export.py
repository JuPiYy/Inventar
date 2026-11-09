import base64
import json
import random
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

from docx import Document
import pytest
from flask import Flask

from WSVINV.database import (
    Category,
    Equipment,
    Location,
    MaintenanceLog,
    MaintenanceTypes,
    Status,
    db,
)
from WSVINV.docx_export import build_docx
from WSVINV.routes import register_routes


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.fixture
def docx_client(tmp_path):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_FOLDER=str(tmp_path),
    )
    db.init_app(app)
    register_routes(app)
    with app.app_context():
        db.create_all()
        db.session.add_all([
            Category(id=1, name="Boote"),
            Status(id=1, name="Aktiv", color_class="success"),
            Location(id=1, name="Lager"),
            MaintenanceTypes(id=1, name="Inspektion"),
        ])
        db.session.commit()
        yield app.test_client(), tmp_path
        db.session.remove()
        db.drop_all()


def _item(image="boot.png", specs=None):
    return SimpleNamespace(
        EquipmentID=1,
        AssetTag="BOOT/Ä-001",
        ModelName="Touryak 🚣",
        category=SimpleNamespace(name="Boote"),
        status=SimpleNamespace(name="Aktiv"),
        location=SimpleNamespace(name="Lager"),
        Quantity=2,
        Vendor="Händler & Co.",
        PurchaseDate=date(2025, 1, 2),
        PurchasePrice=Decimal("100.50"),
        CurrentValue=Decimal("80.25"),
        WarrantyMonths=12,
        Notes="Zeile 1\nZeile 2 & mehr",
        Specs=json.dumps(specs or {"Farbe": "Blau", "Gewicht": 12}),
        ImageFile=image,
    )


def _log():
    return SimpleNamespace(
        LogDate=datetime(2025, 2, 3, 4, 5),
        maintenance_type=SimpleNamespace(name="Inspektion"),
        Description="Prüfung & Reinigung",
        Costs=Decimal("12.34"),
        PerformedBy="Ärger",
    )


def _text(document):
    return "\n".join(p.text for p in document.paragraphs) + "\n" + "\n".join(
        cell.text
        for table in document.tables
        for row in table.rows
        for cell in row.cells
    )


def test_docx_contains_data_tables_and_embedded_image(tmp_path):
    image = tmp_path / "boot.png"
    image.write_bytes(PNG)
    document = Document(build_docx(_item(), [_log()], image))

    text = _text(document)
    assert len(document.tables) == 2
    assert "Gegenstandsdaten" in text
    assert "Wartungslog" in text
    assert "Durchgeführt von" in text
    assert "Touryak" in text
    assert "Prüfung & Reinigung" in text
    assert "Kosten" in text
    assert len(document.inline_shapes) == 1


def test_route_download_headers_filename_and_missing_image(docx_client):
    client, upload_folder = docx_client
    item = Equipment(
        EquipmentID=1, AssetTag="BOOT/Ä-001", ModelName="Touryak",
        Specs="{}", ImageFile="missing.png",
    )
    db.session.add(item)
    db.session.commit()

    response = client.get("/equipment/1/export/docx")
    assert response.status_code == 200
    assert response.mimetype == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert response.headers["Content-Disposition"].endswith("BOOT_A-001.docx")
    Document(BytesIO(response.data))
    assert not list(upload_folder.iterdir())
    assert client.get("/equipment/999/export/docx").status_code == 404


def test_empty_values_and_empty_log_are_explained():
    item = _item(image=None, specs="{}")
    item.ModelName = None
    item.Vendor = None
    item.Notes = None
    document = Document(build_docx(item, [], image_path=None))
    text = _text(document)
    assert "Keine Einträge" in text
    assert "Nicht angegeben" in text


def test_invalid_image_does_not_prevent_export(tmp_path):
    image = tmp_path / "invalid.png"
    image.write_text("not an image", encoding="utf-8")
    document = Document(build_docx(_item(), [], image))
    assert len(document.tables) == 2
    assert len(document.inline_shapes) == 0


def test_bounded_deterministic_fuzz_exports_open():
    rng = random.Random(20261109)
    alphabet = "äöü 🚣 &<>\"'\\n/[]{}"
    for index in range(40):
        value = "".join(rng.choice(alphabet) for _ in range(index * 3))
        item = _item(
            image=None,
            specs={"Schlüssel": value, "Leer": "" if index % 2 else value},
        )
        logs = [
            SimpleNamespace(
                LogDate=None if index % 3 == 0 else datetime(2026, 1, 1),
                maintenance_type=SimpleNamespace(name=value),
                Description=value,
                Costs=Decimal("0") if index % 2 else Decimal("999999.99"),
                PerformedBy=value,
            )
        ]
        Document(build_docx(item, logs))
