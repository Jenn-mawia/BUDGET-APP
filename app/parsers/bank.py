"""Bank statement parser — Extract / Transform pipeline.

Reads an I&M bank PDF statement directly into normalized transactions, using the shared schema.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pdfplumber


# A transaction's "amount line": two dd-mm-yy dates, a number, a balance.
_TXN_RE = re.compile(r"^(\d{2}-\d{2}-\d{2})\s+(\d{2}-\d{2}-\d{2})\s+"
                     r"([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*Cr",)

# The 'B/F' opening-balance line: one date, a balance, then 'B/F'.
_BF_RE = re.compile(r"^(\d{2}-\d{2}-\d{2})\s+([\d,]+\.\d{2})\s*Cr\s+B/F")

# The 'Total' reconciliation line: 'Total  <withdrawals>  <deposits>'.
_TOTAL_RE = re.compile(r"^Total\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})")


## EXTRACT

def extract(file_path: str | Path) -> list[str]:
    """Read every text line from every page of the PDF."""
    lines: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines.extend(text.split("\n"))
    return lines


## TRANSFORM

def _num(text: str) -> float:
    """Converts strings to float: '1,234.56' -> 1234.56 """
    return float(text.replace(",", ""))


def transform(lines: list[str], account: str) -> list[dict]:
    """Clean raw PDF lines into normalized transactions.

    Direction is inferred from balance movement: a drop vs the previous balance means money out, a rise means money in.
    """
    txns: list[dict] = []
    prev_balance: float | None = None

    for i, line in enumerate(lines):
        line = line.strip()

        # The B/F line only seeds the opening balance.
        bf = _BF_RE.match(line)
        if bf:
            prev_balance = _num(bf.group(2))
            continue

        m = _TXN_RE.match(line)  
        if not m:
            continue

        # get transaction date, amount and balance    
        tran_date = dt.datetime.strptime(m.group(1), "%d-%m-%y").date()
        amount = _num(m.group(3))
        balance = _num(m.group(4))

        # Narrative wraps onto the lines just before and just after.
        before = lines[i - 1].strip() if i > 0 else ""
        after = lines[i + 1].strip() if i + 1 < len(lines) else ""

        # Keep only narrative fragments (skip other amount/BF lines).
        parts = [
            p for p in (before, after)
            if p and not _TXN_RE.match(p) and not _BF_RE.match(p)
            and not p.startswith("Total")
        ]
        description = " ".join(parts)

        # Direction from balance movement (ground truth).
        if prev_balance is not None:
            direction = "out" if balance < prev_balance else "in"
        else:
            direction = "out"
        prev_balance = balance

        txns.append({
            "date": tran_date,
            "description": description,
            "amount": amount,
            "direction": direction,
            "balance": balance,
            "source": "bank",
            "account": account,
            "is_overdraft_helper": False, # not needed for bank transactions here
        })
    return txns


def extract_totals(lines: list[str]) -> dict | None:
    """Pull the statement's stated Total row, for reconciliation checks."""
    for line in lines:
        m = _TOTAL_RE.match(line.strip())
        if m:
            return {"withdrawals": _num(m.group(1)), "deposits": _num(m.group(2))}
    return None


## ORCHESTRATOR

def run(file_path: str | Path, account: str | None = None) -> list[dict]:
    """Extract + Transform a bank PDF statement into normalized transactions."""
    file_path = Path(file_path)
    lines = extract(file_path)
    return transform(lines, account or file_path.stem)