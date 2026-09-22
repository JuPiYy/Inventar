"""
Handling connections from and to the database
"""

from flask_sqlalchemy import SQLAlchemy

import json

db = SQLAlchemy()

class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)

class Status(db.Model):
    __tablename__ = 'statuses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)#
    color_class = db.Column(db.String(20), default='secondary') # Neu!

class MaintenanceTypes(db.Model):
    __tablename__ = 'MaintenanceTypes'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)

class Equipment(db.Model):
    __tablename__ = 'equipment'

    EquipmentID = db.Column(db.Integer, primary_key=True)
    AssetTag = db.Column(db.String(20), unique=True, nullable=False)
    CategoryID = db.Column(db.Integer, db.ForeignKey('categories.id'))
    ModelName = db.Column(db.String(100))
    PurchaseDate = db.Column(db.Date)
    StatusID = db.Column(db.Integer, db.ForeignKey('statuses.id'))
    LocationID = db.Column(db.Integer, db.ForeignKey('locations.id'))
    PurchasePrice = db.Column(db.Numeric(10, 2))
    CurrentValue = db.Column(db.Numeric(10, 2))
    WarrantyMonths = db.Column(db.Integer, default=0)
    Quantity = db.Column(db.Integer, default=1)
    Vendor = db.Column(db.String(255))
    ImageFile = db.Column(db.String(255))
    # SQL Server 2025 JSON Support via Text
    Specs = db.Column(db.Text)
    Notes = db.Column(db.Text)

    location = db.relationship('Location', backref='items')
    category = db.relationship('Category', backref='items')
    status = db.relationship('Status', backref='items')

    @property
    def specs_dict(self):
        if self.Specs:
            try:
                # The stored JSON string is loaded into a dictionary
                data = json.loads(self.Specs)
                return data
            except:
                return {}
        return {}

class MaintenanceLog(db.Model):
    __tablename__ = 'MaintenanceLog'

    LogID = db.Column(db.Integer, primary_key=True)
    EquipmentID = db.Column(db.Integer, db.ForeignKey('equipment.EquipmentID'))
    LogDate = db.Column(db.DateTime, server_default=db.func.now())
    TypeID = db.Column(db.Integer, db.ForeignKey('MaintenanceTypes.id'))
    Description = db.Column(db.Text)
    Costs = db.Column(db.Numeric(10, 2))
    PerformedBy = db.Column(db.String(100))

    maintenance_type = db.relationship('MaintenanceTypes', backref='logs')

class Location(db.Model):
    __tablename__ = 'locations'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)