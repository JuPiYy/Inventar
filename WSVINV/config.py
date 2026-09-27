import dotenv
import os

dotenv.load_dotenv(os.path.join('.env'))

class Settings():
    class Server:
        def __init__(self):
            self.host = os.getenv("SERVER_HOST", "127.0.0.1")
            self.port = int(os.getenv("SERVER_PORT", "8080"))
            self.debug = os.getenv("SERVER_DEBUG", "False").lower() in ["true", "1", "yes"]

    class Database:
        def __init__(self):
            self.host = os.getenv("DATABASE_HOST", "localhost")
            self.name = os.getenv("DATABASE_NAME", "Inventar")
            self.username = os.getenv("DATABASE_USERNAME", "sa")
            self.password = os.getenv("DATABASE_PASSWORD", "Password123!")
            self.trusted_connection = os.getenv("DATABASE_TRUSTED_CONNECTION") if os.getenv("DATABASE_TRUSTED_CONNECTION") is not None else "yes"
            self.trustservercertificate = os.getenv("DATABASE_TRUSTSERVERCERTIFICATE") if os.getenv("DATABASE_TRUSTSERVERCERTIFICATE") is not None else "yes"
            self.track_modifications = bool(os.getenv("SQLALCHEMY_TRACK_MODIFICATIONS"))
    
    class App:
        def __init__(self):
            self.admin_enabled = os.getenv("ADMIN_ENABLED", "False")
            self.xlsx_export = os.getenv("XLSX_EXPORT_ENABLED", "False")
            self.upload_enabled = os.getenv("UPLOAD_ENABLED", "False")
            self.upload_folder = os.getenv("UPLOAD_FOLDER", "static/uploads")
            self.json_details = os.getenv("JSON_ENABLED", "False")
            
    def __init__(self):
        self.server = self.Server()
        self.database = self.Database()
        self.app = self.App()

settings = Settings()