"""
Handles webpage management.  Contains all available endpoints/sites
"""

from WSVINV.config import settings

from WSVINV.database import Category, Status, MaintenanceTypes, Equipment, MaintenanceLog, Location
from WSVINV.database import db
from WSVINV.excel_export import build_export_data, render_xlsx
from WSVINV.docx_export import build_docx

from flask import jsonify, render_template, request, redirect, url_for, send_file
from datetime import datetime, timedelta

from werkzeug.utils import secure_filename

from io import BytesIO

import json
import os


def _validate_specs(specs):
    if not isinstance(specs, dict):
        return None, "JSON-Details müssen als Objekt angegeben werden."

    normalized_specs = {}
    for key, value in specs.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            return None, "JSON-Details dürfen keinen leeren Schlüssel enthalten."
        if isinstance(value, (dict, list)):
            return None, "JSON-Details dürfen nur flache Schlüssel/Wert-Paare enthalten."
        if normalized_key in normalized_specs:
            return None, f"Der Schlüssel '{normalized_key}' ist doppelt vorhanden."
        normalized_specs[normalized_key] = value

    return normalized_specs, None


def _specs_from_form(request):
    spec_keys = request.form.getlist('spec_key[]')
    spec_values = request.form.getlist('spec_value[]')

    if len(spec_keys) != len(spec_values):
        return None, "Ungültige JSON-Details: Schlüssel und Werte müssen paarweise angegeben werden."

    specs = {}
    for key, value in zip(spec_keys, spec_values):
        normalized_key = key.strip()
        if not normalized_key:
            if value.strip():
                return None, "Ungültige JSON-Details: Ein Wert darf keinen leeren Schlüssel haben."
            continue
        if normalized_key in specs:
            return None, f"Ungültige JSON-Details: Der Schlüssel '{normalized_key}' ist doppelt vorhanden."
        specs[normalized_key] = value

    return _validate_specs(specs)


def register_routes(app):
    @app.route('/')
    def index():
        # 1. Basis-Query erstellen
        query = Equipment.query

        # 2. Filter aus der URL holen
        search = request.args.get('search', '').strip() # .strip() entfernt Leerzeichen
        cat_id = request.args.get('category')
        stat_id = request.args.get('status')

        # 3. Query dynamisch erweitern
        if search:
            search_term = f"%{search.lower()}%"
            
            # Wir müssen Specs explizit als String (Text) behandeln für SQL Server
            # cast() wandelt den Datentyp für die Abfrage um
            specs_as_text = db.cast(Equipment.Specs, db.String)

            query = query.filter(
                (db.func.lower(Equipment.ModelName).like(search_term)) | 
                (db.func.lower(Equipment.AssetTag).like(search_term)) |
                (db.func.lower(db.func.coalesce(Equipment.Vendor, '')).like(search_term)) |
                (db.func.lower(db.func.coalesce(Equipment.Notes, '')).like(search_term)) |
                (db.func.lower(db.func.coalesce(specs_as_text, '')).like(search_term)) # Hier die umgewandelte Variable nutzen
            )

        if cat_id and cat_id.strip():
            # Wir filtern hier vorsichtshalber direkt auf den String-Wert, 
            # falls die DB-Spalte kein echter Integer ist
            query = query.filter(Equipment.CategoryID == cat_id)

        if stat_id and stat_id.strip():
            query = query.filter(Equipment.StatusID == stat_id)

        app.logger.debug(str(query))

        # 4. Daten ausführen und Hilfslisten für die Dropdowns laden
        inventory = query.join(Category).order_by(Category.name, Equipment.ModelName).all()
        categories = Category.query.all()
        statuses = Status.query.all()

        return render_template('index.html', 
                               inventory=inventory, 
                               categories=categories, 
                               statuses=statuses,
                               settings=settings.app)

    @app.route('/equipment/<int:item_id>')
    def details(item_id):
        item = Equipment.query.get_or_404(item_id)
    
        # Garantie-Logik hier berechnen
        warranty_info = None
        if item.PurchaseDate and item.WarrantyMonths:
            # Grobe Berechnung: Monate * 30 Tage
            end_date = item.PurchaseDate + timedelta(days=item.WarrantyMonths * 30)
            today = datetime.now().date()
            is_active = today <= end_date
        
            # Wir schicken ein fertiges Dictionary ans Template
            warranty_info = {
                'end_date': end_date,
                'is_active': is_active,
                'remaining_months': max(0, (end_date - today).days // 30)
            }
    
        # JSON-String aus der DB in ein Python-Dictionary umwandeln
        specs_dict = {}
        if item.Specs:
            try:
                specs_dict = json.loads(item.Specs)
            except:
                specs_dict = {"Fehler": "Ungültiges JSON-Format"}

        # Wartungslogs laden
        logs = MaintenanceLog.query.filter_by(EquipmentID=item_id)\
                               .order_by(MaintenanceLog.LogDate.desc())\
                               .all()
    
        maint_types = MaintenanceTypes.query.all()
        today_date = datetime.now().strftime('%Y-%m-%d')

        all_categories = Category.query.all()
        all_statuses = Status.query.all()
        all_locations = Location.query.all()
        all_maint_types = MaintenanceTypes.query.all()    

        return render_template('details.html', 
                               item=item, 
                               specs=specs_dict, 
                               logs=logs, 
                               warranty=warranty_info,
                               maint_types=maint_types, # Wichtig fürs Modal
                               today_date=today_date,   # Wichtig fürs Modal
                               categories=all_categories,  # Hier mitschicken!
                               statuses=all_statuses,      # Hier mitschicken!
                               locations=all_locations,
                               settings=settings.app
                               )

    @app.route('/equipment/<int:item_id>/export/docx')
    def export_docx(item_id):
        item = Equipment.query.get_or_404(item_id)
        logs = MaintenanceLog.query.filter_by(EquipmentID=item_id)\
            .order_by(MaintenanceLog.LogDate.desc(), MaintenanceLog.LogID.desc()).all()

        image_path = None
        image_name = getattr(item, 'ImageFile', None)
        if image_name:
            # Only resolve a file name inside the configured upload directory.
            safe_image_name = os.path.basename(image_name)
            candidate = os.path.join(app.config['UPLOAD_FOLDER'], safe_image_name)
            if os.path.isfile(candidate):
                image_path = candidate

        output = build_docx(item, logs, image_path=image_path)
        safe_asset = secure_filename(str(item.AssetTag or f"equipment-{item_id}"))
        if not safe_asset:
            safe_asset = f"equipment-{item_id}"
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            as_attachment=True,
            download_name=f'{safe_asset}.docx',
        )

    @app.route('/equipment/add', methods=['GET', 'POST'])
    def add_equipment():
        if request.method == 'POST':
            # 1. Basis-Daten aus dem Formular in Variablen speichern
            # Wir brauchen diese Variablen oben, um später den Bildnamen zu bauen
            asset_tag = request.form.get('AssetTag')
            model_name = request.form.get('ModelName')
        
            # 2. Bild-Verarbeitung
            file = request.files.get('image')
            final_filename = None
    
            if file and file.filename != '':
                # Dateiendung extrahieren (z.B. .jpg)
                ext = os.path.splitext(file.filename)[1]
            
                # Dateinamen generieren und säubern (Leerzeichen zu Unterstrichen)
                safe_model = model_name.replace(" ", "_") if model_name else "item"
                new_filename = f"{asset_tag}_{safe_model}{ext}"
    
                # Physikalisch im Ordner speichern (WSVINV/static/uploads/)
                # Pfad wurde in der App-Config definiert
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], new_filename))
                final_filename = new_filename

            # 3. Das neue Datenbank-Objekt (Equipment) erstellen
            new_item = Equipment(
                AssetTag=asset_tag,
                ModelName=model_name,
                CategoryID=request.form.get('CategoryID'),
                StatusID=request.form.get('StatusID'),
                LocationID=request.form.get('LocationID'),
                Vendor=request.form.get('Vendor'),
                Quantity=int(request.form.get('Quantity') or 1),
                Notes=request.form.get('Notes'),
                # Hier nutzen wir das Feld aus deinem Screenshot
                ImageFile=final_filename, 
                PurchaseDate=request.form.get('PurchaseDate') if request.form.get('PurchaseDate') else None,
                PurchasePrice=request.form.get('PurchasePrice') if request.form.get('PurchasePrice') else None,
                WarrantyMonths=request.form.get('WarrantyMonths') if request.form.get('WarrantyMonths') else 0,
                CurrentValue=request.form.get('CurrentValue') if request.form.get('CurrentValue') else None
            )

            # 4. Dynamische JSON-Specs verarbeiten
            specs_dict, specs_error = _specs_from_form(request)
            if specs_error:
                return specs_error, 400
            new_item.Specs = json.dumps(specs_dict, ensure_ascii=False)

            # 5. In die Datenbank schreiben
            try:
                db.session.add(new_item)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                app.logger.error(f"Fehler beim Speichern des Equipments: {e}")
                return "Datenbankfehler beim Speichern", 500

            return redirect(url_for('index'))

        # --- GET-Teil (Anzeige des leeren Formulars) ---
        categories = Category.query.all()
        statuses = Status.query.all()
        locations = Location.query.all()
    
        return render_template(
            'add_equipment.html', 
            categories=categories, 
            statuses=statuses, 
            locations=locations,
            settings=settings.app
        )

    @app.route('/api/equipment/<int:item_id>/specs', methods=['PUT'])
    def update_equipment_specs(item_id):
        if settings.app.json_details.lower() != 'true':
            return jsonify({'error': 'JSON-Details sind deaktiviert.'}), 403

        item = Equipment.query.get_or_404(item_id)
        payload = request.get_json(silent=True)
        specs, error = _validate_specs(payload)
        if error:
            return jsonify({'error': error}), 400

        item.Specs = json.dumps(specs, ensure_ascii=False)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Fehler beim Speichern der JSON-Details: {e}")
            return jsonify({'error': 'Fehler beim Speichern der JSON-Details.'}), 500

        return jsonify({
            'equipment_id': item.EquipmentID,
            'specs': specs
        })

    @app.route('/admin', methods=['GET', 'POST'])
    def admin_panel():
        if request.method == 'POST':
            target = request.form.get('target')
            name = request.form.get('name')
        
            if name:
                if target == 'category':
                    db.session.add(Category(name=name))
                elif target == 'status':
                    color = request.form.get('color_class', 'secondary')
                    db.session.add(Status(name=name, color_class=color))
                elif target == 'location':  # NEU: Standort speichern
                    db.session.add(Location(name=name))
                elif target == 'maint_type':
                    db.session.add(MaintenanceTypes(name=name))
            
                db.session.commit()
            return redirect(url_for('admin_panel'))

        # Alle Daten laden, um sie in den Listen anzuzeigen
        return render_template('admin.html', 
                               categories=Category.query.all(), 
                               statuses=Status.query.all(),
                               locations=Location.query.all(), # NEU: Standorte laden
                               maint_types=MaintenanceTypes.query.all(),
                               settings=settings.app)

    @app.route('/equipment/<int:item_id>/add_log', methods=['POST'])
    def add_log(item_id):
        # 1. Daten aus dem Formular holen
        date_str = request.form.get('LogDate')
        log_date_full = datetime.strptime(date_str, '%Y-%m-%d')
        new_location_id = request.form.get('NewLocationID')
    
        item = Equipment.query.get_or_404(item_id)
        description = request.form.get('Description')

        # 2. Standortänderung prüfen und protokollieren
        if new_location_id and int(new_location_id) != item.LocationID:
            old_location_name = item.location.name.strip() if item.location else "Unbekannt"
        
            # Den neuen Standort-Namen für die Beschreibung holen
            new_loc_obj = Location.query.get(int(new_location_id))
            new_location_name = new_loc_obj.name.strip() if new_loc_obj else "Unbekannt"
        
            # Die Beschreibung automatisch ergänzen
            # Benutze ein einfaches Trennzeichen, das keine Probleme macht
            move_text = f"\n[Standort geändert: {old_location_name} >>> {new_location_name}]"
            description += move_text
        
            # Den Standort am Gerät selbst aktualisieren
            item.LocationID = int(new_location_id)

        # --- STATUS-LOGIK (Neu & Analog dazu) ---
        new_status_id = request.form.get('NewStatusID')
        if new_status_id and int(new_status_id) != item.StatusID:
            # Den alten Status-Namen holen
            old_status_name = item.status.name.strip() if item.status else "Unbekannt"
    
            # Den neuen Status-Namen für die Beschreibung holen
            new_status_obj = Status.query.get(int(new_status_id))
            new_status_name = new_status_obj.name.strip() if new_status_obj else "Unbekannt"
    
            # Die Beschreibung automatisch ergänzen (analog zum Standort)
            status_text = f"\n[Status geändert: {old_status_name} >>> {new_status_name}]"
            description += status_text
    
            # Den Status am Gerät selbst aktualisieren
            item.StatusID = int(new_status_id)

        # 3. Den Wartungseintrag mit der erweiterten Beschreibung speichern
        new_log = MaintenanceLog(
            EquipmentID=item_id,
            LogDate=log_date_full,
            TypeID=request.form.get('TypeID'),
            Description=description, # Hier ist jetzt der Umzugstext drin
            Costs=float(request.form.get('Costs') or 0),
            PerformedBy=request.form.get('PerformedBy')
        )
    
        db.session.add(new_log)
        db.session.commit()
    
        return redirect(url_for('details', item_id=item_id))

    @app.route('/equipment/<int:item_id>/edit', methods=['POST'])
    def edit_item(item_id):
        item = Equipment.query.get_or_404(item_id)

        specs_json = None
        if settings.app.json_details.lower() == 'true':
            specs, error = _specs_from_form(request)
            if error:
                return error, 400
            specs_json = json.dumps(specs, ensure_ascii=False)
    
        # Grunddaten
        item.ModelName = request.form.get('ModelName')
        item.AssetTag = request.form.get('AssetTag')
        item.CategoryID = request.form.get('CategoryID')
        item.StatusID = request.form.get('StatusID')
        item.Notes = request.form.get('Notes')
        item.LocationID = request.form.get('LocationID')
        item.Vendor = request.form.get('Vendor') # Hinzufügen
    
        # Finanzdaten & Garantie
        item.PurchasePrice = float(request.form.get('PurchasePrice') or 0)
        item.CurrentValue = float(request.form.get('CurrentValue') or 0)
        item.WarrantyMonths = int(request.form.get('WarrantyMonths') or 0)

        item.Quantity = int(request.form.get('Quantity') or 1)
        if specs_json is not None:
            item.Specs = specs_json
    
        # Datum handling
        p_date = request.form.get('PurchaseDate')
        if p_date:
            item.PurchaseDate = datetime.strptime(p_date, '%Y-%m-%d')
        else:
            item.PurchaseDate = None

        # --- NEUER CODE: Bildupload verarbeiten ---
        if settings.app.upload_enabled and settings.app.upload_enabled.lower() == 'true':
            if 'image' in request.files:
                file = request.files['image']
                
                if file and file.filename != '':
                    # Dateiendung validieren
                    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
                    
                    if ext in ALLOWED_EXTENSIONS:
                        # Altes Bild löschen
                        if item.ImageFile:
                            old_path = os.path.join(app.config['UPLOAD_FOLDER'], item.ImageFile)
                            if os.path.exists(old_path):
                                try:
                                    os.remove(old_path)
                                except Exception as e:
                                    app.logger.warning(f"Konnte altes Bild nicht löschen: {e}")
                        
                        # Neuen Dateinamen generieren
                        safe_model = item.ModelName.replace(" ", "_") if item.ModelName else "item"
                        new_filename = f"{item.AssetTag}_{safe_model}.{ext}"
                        
                        try:
                            file.save(os.path.join(app.config['UPLOAD_FOLDER'], new_filename))
                            item.ImageFile = new_filename
                        except Exception as e:
                            app.logger.error(f"Fehler beim Bildupload: {e}")

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Fehler beim Update: {e}")
            return "Fehler beim Speichern", 500
        
        return redirect(url_for('details', item_id=item_id))

    @app.route('/equipment/<int:item_id>/delete', methods=['POST'])
    def delete_item(item_id):
        item = Equipment.query.get_or_404(item_id)
    
        # Optional: Zuerst alle zugehörigen Wartungslogs löschen 
        # (Falls keine "Cascade Delete" in der DB eingestellt ist)
        MaintenanceLog.query.filter_by(EquipmentID=item_id).delete()
    
        db.session.delete(item)
        db.session.commit()
        return redirect(url_for('index'))

    @app.route('/export/excel')
    def export_excel():
        items = Equipment.query.all()
        maintenance_logs = MaintenanceLog.query.order_by(MaintenanceLog.LogID).all()
        export_data = build_export_data(items, maintenance_logs)
        output = render_xlsx(export_data)
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'WSV_Inventar_{timestamp}.xlsx'
        )