from pathlib import Path

try:
    from config.local import XML_DUMP_PATH
except ImportError:
    XML_DUMP_PATH = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
DATABASE_DIR = DATA_DIR / "database"
PROCESSED_DIR = DATA_DIR / "processed"