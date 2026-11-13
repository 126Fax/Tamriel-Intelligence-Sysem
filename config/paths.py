from pathlib import Path

from config.local import XML_DUMP_PATH

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
DATABASE_DIR = DATA_DIR / "database"
PROCESSED_DIR = DATA_DIR / "processed"