"""
The flask application package.
"""

from WSVINV.database import db
from WSVINV.routes import register_routes

from flask import Flask

from sqlalchemy import text

import dotenv
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

env_path = os.path.join(basedir, "..", ".env")
dotenv.load_dotenv(env_path, override=True)
app.logger.info(f"Found environment variable file: {env_path}")

# 2. Flask-SQLAlchemy Konfiguration
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = bool(os.getenv("SQLALCHEMY_TRACK_MODIFICATIONS"))
app.config['SQLALCHEMY_DATABASE_URI'] = f"mssql+pyodbc://{os.getenv("DATABASE_HOST")}/{os.getenv("DATABASE_NAME")}?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection={os.getenv("DATABASE_TRUSTED_CONNECTION").lower()}&TrustServerCertificate={os.getenv("DATABASE_TRUSTSERVERCERTIFICATE").lower()}"


# 4. Pfade konfigurieren (Jetzt sind die Variablen aus der .env verfügbar!)
# Falls in der .env nichts steht, nutzen wir den Standard-Pfad
raw_upload_path = os.getenv("UPLOAD_FOLDER", "static/uploads")

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
        app.logger.info("Database connection successfully established!")

    except Exception as e:
        app.logger.error(f"Database connection failed: {e}")

register_routes(app)