"""
The flask application package.
"""

from WSVINV.config import settings
from WSVINV.database import db
from WSVINV.routes import register_routes

from flask import Flask

from sqlalchemy import text

import os
import logging
import sys

# Configure standard Python logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)

# 2. Flask-SQLAlchemy Konfiguration
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = settings.database.track_modifications

if settings.database.trusted_connection.lower() == "yes":
    app.config['SQLALCHEMY_DATABASE_URI'] = f"mssql+pyodbc://{settings.database.host}/{settings.database.name}?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes&TrustServerCertificate={settings.database.trustservercertificate}"
    app.logger.info(f"Es besteht eine vertrauenswürdige Verbindung, weswegen die Benutzerdatenkonfiguration ignoriert wurde")
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = f"mssql+pyodbc://{settings.database.username}:{settings.database.password}@{settings.database.host}/{settings.database.name}?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate={settings.database.trustservercertificate}"
    app.logger.info(f"Es besteht keine vertrauenswürdige Verbindung.  Die angegebenen Benutzerdaten werden verwendet.")

app.logger.info(f"Database URI: {app.config['SQLALCHEMY_DATABASE_URI']}")

app.logger.info(f"Das hochladen von Bildern ist " + ("aktiviert" if settings.app.upload_enabled == "True" else "deaktiviert") + ".")
app.logger.info(f"Das hinzufügen von JSON-Daten ist " + ("aktiviert" if settings.app.json_details == "True" else "deaktiviert" + "."))
app.logger.info(f"Das Exportieren von XLSX-Dateien ist " + ("aktiviert" if settings.app.xlsx_export == "True" else "deaktiviert") + ".")

app.logger.info(f"Der Administrator-Bereich ist " + ("aktiviert" if settings.app.admin_enabled == "True" else "deaktiviert.  Bitte aktivieren Sie ihn in der .env-Datei um Änderungen vorzunehmen."))


# 4. Pfade konfigurieren (Jetzt sind die Variablen aus der .env verfügbar!)
# Falls in der .env nichts steht, nutzen wir den Standard-Pfad
raw_upload_path = settings.app.upload_folder or "static/uploads"

# Falls der Pfad in der .env relativ angegeben ist (z.B. "static/uploads"), 
# machen wir ihn hier absolut zum basedir
if not os.path.isabs(raw_upload_path):
    upload_path = os.path.abspath(os.path.join(basedir, raw_upload_path))
else:
    upload_path = raw_upload_path

app.config['UPLOAD_FOLDER'] = upload_path

# 5. Ordner-Check (Erstellen, falls er fehlt)
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.logger.info(f"Upload-Ordner erstellt: {app.config['UPLOAD_FOLDER']}")

db.init_app(app)

with app.app_context():
    try:
        db.session.execute(text('SELECT 1'))
        app.logger.info("Die Verbindung mit der Datenbank wurde erfolgreich hergestellt!")

    except Exception as e:
        app.logger.error(f"Beim Verbinden mit der Datenbank ist ein Fehler aufgetreten: {e}")

register_routes(app)