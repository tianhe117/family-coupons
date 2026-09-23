"""Isolated browser-test server; never opens production data."""
import tempfile
from pathlib import Path
from app import create_app

with tempfile.TemporaryDirectory() as directory:
    app = create_app({'DATA_FILE': str(Path(directory) / 'data.json'), 'COOKIE_SECURE': False})
    app.run(port=8081, threaded=True)
