from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
UPLOADS = ROOT / "uploads"
DATA.mkdir(exist_ok=True)
UPLOADS.mkdir(exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(DATA / 'invoice_app.db').as_posix()}")
MAX_UPLOAD = 15 * 1024 * 1024
