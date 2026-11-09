import json

import pytest
from flask import Flask

from WSVINV.database import Equipment, db
from WSVINV.routes import register_routes
from WSVINV.config import settings


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setattr(settings.app, "json_details", "True")

    test_app = Flask(__name__)
    test_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_FOLDER=str(tmp_path),
    )
    db.init_app(test_app)
    register_routes(test_app)

    with test_app.app_context():
        db.create_all()
        item = Equipment(
            EquipmentID=1,
            AssetTag="TEST-001",
            ModelName="Testgerät",
            Specs=json.dumps({"alt": "Wert"}),
        )
        db.session.add(item)
        db.session.commit()
        yield test_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def stored_specs(app):
    with app.app_context():
        item = db.session.get(Equipment, 1)
        return json.loads(item.Specs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"data": '{"Farbe":"Blau"}'},
        {"data": '{"Farbe":"Blau"}', "content_type": "text/plain"},
        {"data": "not-json", "content_type": "application/json"},
    ],
)
def test_rejects_missing_or_invalid_content_type_without_server_error(
    client, app, kwargs
):
    response = client.put("/api/equipment/1/specs", **kwargs)

    assert 400 <= response.status_code < 500
    assert response.status_code != 500
    assert stored_specs(app) == {"alt": "Wert"}


@pytest.mark.parametrize("payload", [None, [], ["value"], "text", 42, True])
def test_rejects_non_object_json_payloads(client, app, payload):
    response = client.put("/api/equipment/1/specs", json=payload)

    assert response.status_code == 400
    assert response.get_json()["error"]
    assert stored_specs(app) == {"alt": "Wert"}


@pytest.mark.parametrize(
    "payload",
    [
        {"nested": {"key": "value"}},
        {"array": ["value"]},
        {"": "value"},
        {"   ": "value"},
    ],
)
def test_rejects_nested_values_and_empty_keys(client, app, payload):
    response = client.put("/api/equipment/1/specs", json=payload)

    assert response.status_code == 400
    assert response.get_json()["error"]
    assert stored_specs(app) == {"alt": "Wert"}


def test_accepts_unicode_scalars_and_long_values(client, app):
    payload = {
        " Beschreibung ": "Äußeres Gerät 🚣",
        "Anzahl": 2,
        "Aktiv": True,
        "Leer": None,
        "Lang": "x" * 10000,
    }

    response = client.put("/api/equipment/1/specs", json=payload)

    assert response.status_code == 200
    assert response.get_json()["specs"] == {
        "Beschreibung": "Äußeres Gerät 🚣",
        "Anzahl": 2,
        "Aktiv": True,
        "Leer": None,
        "Lang": "x" * 10000,
    }
    assert stored_specs(app) == response.get_json()["specs"]


def test_empty_object_clears_existing_specs(client, app):
    response = client.put("/api/equipment/1/specs", json={})

    assert response.status_code == 200
    assert response.get_json()["specs"] == {}
    assert stored_specs(app) == {}


def test_unknown_equipment_returns_not_found_without_server_error(client):
    response = client.put("/api/equipment/999/specs", json={"Farbe": "Blau"})

    assert response.status_code == 404
    assert response.status_code < 500


def test_disabled_json_setting_rejects_update_and_preserves_data(client, app, monkeypatch):
    monkeypatch.setattr(settings.app, "json_details", "False")

    response = client.put("/api/equipment/1/specs", json={"neu": "Wert"})

    assert response.status_code == 403
    assert response.get_json() == {"error": "JSON-Details sind deaktiviert."}
    assert stored_specs(app) == {"alt": "Wert"}

