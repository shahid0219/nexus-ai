"""Test bootstrap — redirect all state into a temp directory (never the real DB)."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app import config  # noqa: E402

_tmp = Path(tempfile.mkdtemp(prefix="nexus_test_"))
config.DATA_DIR = _tmp
config.DB_PATH = _tmp / "nexus.db"
config.ARTIFACTS_DIR = _tmp / "artifacts"
config.REPORTS_DIR = _tmp / "reports"
config.UPLOADS_DIR = _tmp / "uploads"
config.CREDENTIALS_FILE = _tmp / "credentials.json"
for d in (config.ARTIFACTS_DIR, config.REPORTS_DIR, config.UPLOADS_DIR):
    d.mkdir(parents=True, exist_ok=True)
