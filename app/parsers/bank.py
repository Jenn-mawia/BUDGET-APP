"""
Bank statement parser

Reads a bank .xlsx statement (PDF-converted) into normalized transactions, using the same schema as the M-PESA parser

The converter produces a messy layout: column positions drift between files, and balance + narrative are mashed into one cell. So we detect
fields by content, not fixed positions, and infer direction from how the running balance moves between rows.
"""


from __future__ import annotations
 
import datetime as _dt
from pathlib import Path
import re
 
import openpyxl

## EXTRACT
def extract(file_path: str | Path) -> list[tuple]:
   # Read the raw .xlsx rows.
    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    rows = list(wb[wb.sheetnames[0]].iter_rows(values_only=True))
    wb.close()
    return rows

## TRANSFORM
def _to_amount(value) -> float:
    """
    Converts the amount value to a positive float.
    Handles various formats including numeric types, strings with commas, and blanks e.g.'1,234.56'
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace(",", ""))
    except ValueError:
        return 0.0
    

def _split_balance_narrative(text: str) -> tuple[float | None, str]:
    """
    Split a 'balance Cr/Dr narrative' cell into (balance, description).
    Example: '17,013.40 Cr   254729920461/MPESA Payment to ...'
             -> (17013.40, '254729920461/MPESA Payment to ...')
    """
    text = str(text).replace("\\n", " ").strip()
    m = re.match(r"([\d,]+\.\d{2})\s*(Cr|Dr)?\s*(.*)", text, re.DOTALL)
    if not m:
        return None, text
    balance = _to_amount(m.group(1))
    description = " ".join(m.group(3).split())
    return balance, description

def _find_amount(row: tuple, date_col: int, bal_col: int) -> float:
    """
    Find the lone transaction-amount number between date and balance.
    The amount sits in a drifting column somewhere after the dates and before the balance string. It is the only stray numeric cell there.
    """
    for i in range(date_col + 1, bal_col):
        if isinstance(row[i], (int, float)):
            return float(row[i])
        if isinstance(row[i], str) and re.match(r"^\s*[\d,]+\.\d{2}\s*$", row[i]):
            return _to_amount(row[i])
    return 0.0


