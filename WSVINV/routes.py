"""
Handles webpage management.  Contains all available endpoints/sites
"""

from WSVINV.database import Category, Status, MaintenanceTypes, Equipment, MaintenanceLog, Location
from WSVINV.database import db

from flask import render_template, request, redirect, url_for, send_file
from datetime import datetime, timedelta

from werkzeug.utils import secure_filename

from io import BytesIO

import json
import pandas as pd
import os

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
                               statuses=statuses)

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
                               locations=all_locations)

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
            keys = request.form.getlist('spec_key[]')
            values = request.form.getlist('spec_value[]')
        
            # Dictionary erstellen und leere Keys filtern
            specs_dict = {k: v for k, v in zip(keys, values) if k.strip()}
            new_item.Specs = json.dumps(specs_dict)

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
            locations=locations
        )




    @app.route('/admin', methods=['GET', 'POST'])
    def admin_panel():
        if request.method == 'POST':
            target = request.form.get('target')
            name = request.form.get('name')
        
            if name:
                if target == 'category':
                    db.session.add(Category(name=name))
                elif target == 'status':
                    db.session.add(Status(name=name))
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
                               maint_types=MaintenanceTypes.query.all())

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
    
        # Datum handling
        p_date = request.form.get('PurchaseDate')
        if p_date:
            item.PurchaseDate = datetime.strptime(p_date, '%Y-%m-%d')
        else:
            item.PurchaseDate = None

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
        # 1. Alle Daten aus der Datenbank abrufen
        items = Equipment.query.all()
    
        # 2. Daten für den Export vorbereiten (Listen von Dictionaries)
        data = []
        for item in items:
            data.append({
                'Asset Tag': item.AssetTag,
                'Modellname': item.ModelName,
                'Kategorie': item.category.name if item.category else '',
                'Status': item.status.name if item.status else '',
                'Standort': item.location.name if item.location else '',
                'Anzahl': item.Quantity or 1,
                'Händler': item.Vendor or '',
                'Bemerkungen': item.Notes or '',
                'Kaufdatum': item.PurchaseDate.strftime('%d.%m.%Y') if item.PurchaseDate else '',
                'Kaufpreis [€]': item.PurchasePrice,
                'Garantie [Monate]': item.WarrantyMonths
            })
    
        # 3. DataFrame erstellen
        df = pd.DataFrame(data)
    
        # 4. Datei im Speicher erstellen (nicht auf der Festplatte)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Inventar')
    
        output.seek(0)
    
        # 5. Datei an den User senden
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'WSV_Inventar_{timestamp}.xlsx'
        )