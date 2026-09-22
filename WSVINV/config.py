import dotenv
import os

dotenv.load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

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
            self.trusted_connection = os.getenv("DATABASE_TRUSTED_CONNECTION") if os.getenv("DATABASE_TRUSTED_CONNECTION") is not None else "yes"
            self.trustservercertificate = os.getenv("DATABASE_TRUSTSERVERCERTIFICATE") if os.getenv("DATABASE_TRUSTSERVERCERTIFICATE") is not None else "yes"
            self.track_modifications = bool(os.getenv("SQLALCHEMY_TRACK_MODIFICATIONS"))
    
    class App:
        def __init__(self):
            self.upload_folder = os.getenv("UPLOAD_FOLDER", "static/uploads")
            
    def __init__(self):
        self.server = self.Server()
        self.database = self.Database()
        self.app = self.App()

settings = Settings()