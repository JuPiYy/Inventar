"""
This script runs the WSVINV application using a development server.
"""

from WSVINV import app

from waitress import serve

import dotenv
import os

if __name__ == '__main__':
    env_path = os.path.join(os.path.dirname(__file__), '.env')

    dotenv.load_dotenv(env_path, override=True)

    host = os.getenv("SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("SERVER_PORT", "8080"))

    debug = os.getenv("SERVER_DEBUG", "False").lower() in ["true", "1", "yes"]

    if debug:
        app.run(host=host, port=port, debug=debug)

    else:
        serve(app, host=host, port=port)