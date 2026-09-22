"""
This script runs the WSVINV application using a development server.
"""

from WSVINV import app
from WSVINV.config import settings

from waitress import serve

if __name__ == '__main__':
    host = settings.server.host
    port = settings.server.port
    debug = settings.server.debug

    if debug:
        app.run(host=host, port=port, debug=debug)

    else:
        serve(app, host=host, port=port)