from pathlib import Path

try:
    from config.local import XML_DUMP_PATH
except ImportError:
    XML_DUMP_PATH = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
DATABASE_DIR = DATA_DIR / "database"
PROCESSED_DIR = DATA_DIR / "processed"


def get_xml_dump_path() -> Path:
    """Use config/local.py when set; otherwise find a dump in data/raw."""
    if XML_DUMP_PATH is not None:
        dump_path = Path(XML_DUMP_PATH).expanduser()
        if not dump_path.is_file():
            raise FileNotFoundError(f"XML dump not found: {dump_path}")
        return dump_path

    if not RAW_DATA_DIR.is_dir():
        raise FileNotFoundError(
            f"Raw data folder not found: {RAW_DATA_DIR}. "
            "Create data/raw and place the .xml.bz2 dump inside it."
        )

    candidates = sorted(RAW_DATA_DIR.glob("*.xml.bz2"))
    if not candidates:
        raise FileNotFoundError(
            f"No .xml.bz2 dump found in {RAW_DATA_DIR}. "
            "Place the UESP dump in data/raw."
        )
    if len(candidates) > 1:
        names = ", ".join(path.name for path in candidates)
        raise RuntimeError(
            "More than one .xml.bz2 dump found in data/raw. "
            f"Set XML_DUMP_PATH in config/local.py to choose one: {names}"
        )

    return candidates[0]
