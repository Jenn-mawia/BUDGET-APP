from pathlib import Path
from .mpesa import parse_mpesa
from . import bank


def load_statement(file_path: str | Path, account: str | None = None) -> list[dict]:
    """Picks the right parser from the file type and returns normalized transactions."""
    file_path = Path(file_path)
    suffix = file_path.suffix.lower()
    if suffix == ".xlsx":
        return parse_mpesa(file_path, account)
    if suffix == ".pdf":
        return bank.run(file_path, account)   
    raise ValueError(f"Unsupported statement type: {suffix}")