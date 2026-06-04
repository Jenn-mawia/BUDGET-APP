"""Shared pytest fixtures.
 
The reconciliation tests need the real statement files in data/. These files are git-ignored (they contain private financial data), so the
fixtures below skip those tests gracefully when the files are absent — e.g. in a fresh clone or CI. Unit tests use fake data and always run.
"""

from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def _find(pattern:str) ->list[Path]:
    """Helper to find files matching a glob pattern in the data/ directory."""
    return sorted(DATA_DIR.glob(pattern)) if DATA_DIR.exists() else []

@pytest.fixture
def mpesa_files():
    """Fixture to find M-PESA statement files in data/. Returns a list of file paths, or skips the test if none are found."""
    files = _find("MPESA_Statement_*.xlsx")
    if not files:
        pytest.skip("No M-PESA statement files found in data/. Skipping reconciliation tests.")
    return files

@pytest.fixture
def bank_files()-> list[Path]:
    """Fixture to find bank statement files in data/. Returns a list of file paths, or skips the test if none are found."""
    files = _find("Statement for *.pdf")
    if not files:
        pytest.skip("No bank statement files found in data/. Skipping reconciliation tests.")
    return files
