"""Isolated browser-test server; never opens production data."""
import tempfile
from pathlib import Path
from app import create_app

with tempfile.TemporaryDirectory() as directory:
    app = create_app({'DATA_FILE': str(Path(directory) / 'data.json'), 'INITIAL_ACCESS_PASSWORD': '0012', 'INITIAL_ADMIN_PASSWORD': 'admin-test-123', 'COOKIE_SECURE': False})
    app.run(port=8081, threaded=True)
