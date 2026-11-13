from pathlib import Path

try:
    from config.local import XML_DUMP_PATH
except ImportError:
    XML_DUMP_PATH = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
DATABASE_DIR = DATA_DIR / "database"
PROCESSED_DIR = DATA_DIR / "processed"


def get_xml_dump_path() -> Path:
    if XML_DUMP_PATH is None:
        raise RuntimeError(
            "XML dump path is not configured. "
            "Set XML_DUMP_PATH in config/local.py."
        )

    if not XML_DUMP_PATH.is_file():
        raise FileNotFoundError(f"XML dump not found: {XML_DUMP_PATH}")

    return XML_DUMP_PATH
