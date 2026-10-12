# PesaClarity — Household Finance Dashboard
## Full Technical Development Plan

This document lists every technical step needed to build and deliver PesaClarity v1.0 by **18 December 2026**, in the order the steps should be done. Each step builds on the one before it. Later phases assume the earlier ones are complete, so do not reorder them. The dates assume about 12 build hours a week.

The starting point is the existing repository (`budget app/`, remote `Jenn-mawia/BUDGET-APP`). The M-Pesa and bank parsers already exist, and so do their tests and a first version of `categories.yaml`. `categorize.py`, `app/api/`, `app/ml/` and `dashboard/` are empty.

---

## Phase 0 — Clean-up and Orientation (12 – 18 Oct)

Before adding features, make the repository safe, repeatable and green. Skipping this phase means every later phase is built on tests nobody trusts.

### Step 0.1 — Take the real statements out of git (do this first)

The six I&M bank statements and the 12-month M-Pesa statement in `data/` were committed in `ad6e400` and pushed to GitHub. There is no `.gitignore` at the project root. `conftest.py` says these files are git-ignored, but they are not.

1. On GitHub, check that the `BUDGET-APP` repository is **Private** (Settings → General → Danger Zone → Change visibility).
2. Add a root `.gitignore`:
   ```
   # private financial data
   data/
   *.db
   exports/

   # Python / OS clutter
   __pycache__/
   *.pyc
   .pytest_cache/
   env/
   .DS_Store
   ```
3. Stop tracking the files without deleting them from your laptop. List the folders by name — git does not expand `**` here, and one unmatched path cancels the whole command:
   ```bash
   git rm -r --cached data app/__pycache__ app/parsers/__pycache__ tests/__pycache__ .DS_Store app/.DS_Store
   git add .gitignore
   git commit -m "Stop tracking private statements and build clutter"
   ```
4. The files are still in the **history** of earlier commits. If the repository was ever public, or will ever be shared, remove them from history with `git filter-repo --path data/ --invert-paths` and force-push. Rewriting history cannot be undone, so back up the folder first.

### Step 0.2 — Move the manual check scripts out of `tests/`

`tests/test_bank.py` and `tests/test_mpesa.py` are manual scripts with hard-coded Mac paths. pytest picks up any file named `test_*.py` and runs its top-level code, so they run (and print) during every test run. Move and rename them:

```bash
mkdir -p scripts
git mv tests/test_bank.py scripts/check_bank.py
git mv tests/test_mpesa.py scripts/check_mpesa.py
```

The real tests stay in `tests/test_bank_test.py` and `tests/test_mpesa_test.py`. You can rename those to `test_bank_parser.py` and `test_mpesa_parser.py`.

### Step 0.3 — Pin the dependencies

`requirements.txt` is empty. Install everything v1.0 needs, then freeze the exact versions:

```bash
source env/bin/activate
pip install openpyxl pdfplumber pikepdf pyyaml pandas streamlit plotly reportlab pytest
pip freeze > requirements.txt
```

### Step 0.4 — Run the full test suite

```bash
python -m pytest -v
```

The pytest cache still lists failures under the old file names (`tests/mpesa_test.py`, `tests/bank_test.py`). Those files no longer exist. Confirm everything passes under the current names. From now on, run tests before every commit.

### Step 0.5 — Know the data

Write these facts at the top of a `NOTES.md` so later decisions are grounded. They were checked against the current files:

- The M-Pesa .xlsx has **3,137 transactions** from 15 May 2025 to 14 May 2026, **newest first**.
- **494** rows are Fuliza advances (`OverDraft of Credit Party`) and 188 are `OD Loan Repayment`.
- **158** rows are `Transfer from Bank … IM BANK`. That is the household's own money moving, not income.
- **196** rows are `Unit Trust Invest To … ZIIDI MMF`. These are savings.
- All six I&M PDFs (Nov 2025 – Apr 2026) **reconcile to the cent** against their printed totals.
- The current `categories.yaml` leaves about **15% of outgoing value** uncategorised. It also puts all 408 `Customer Transfer of Funds Charge` rows into People Transfer.

---

## Phase 1 — Harden the Parsers (19 – 21 Oct)

### Step 1.1 — Give every transaction a unique `ref`

A `ref` lets the app recognise a transaction that was uploaded twice. The M-Pesa receipt number alone is **not** unique: in the 12-month statement, 912 receipt numbers appear on more than one row (a Fuliza advance and the payment it funded share one, and so do a transfer and its charge). Receipt + direction + amount + description is unique for all 3,137 rows. In `parsers/mpesa.py`, add it to the dict built in `transform()`:

```python
        transactions.append({
            "ref": f"{str(row[0]).strip()}|{'out' if withdrawn else 'in'}|{amount:.2f}|{description}",
            "date": row[1].date(),
            ...
        })
```

Bank rows have no receipt number. In `parsers/bank.py`, build a stable one from the row itself:

```python
            "ref": f"{account}|{tran_date.isoformat()}|{amount:.2f}|{balance:.2f}",
```

### Step 1.2 — Use one name for the Fuliza flag

`mpesa.py` uses `is_loan_advance` and `bank.py` uses `is_overdraft_helper`. Use `is_loan_advance` in both, so the shared format really is shared:

```python
            "is_loan_advance": False,   # bank statements have no Fuliza advance rows
```

### Step 1.3 — Make the M-Pesa reconciliation test meaningful

The current test checks that money in equals money out. That is only true for this file because the balance starts and ends at zero. The real check is that the balances add up:

```python
def test_mpesa_reconciles(mpesa_files):
    """Opening balance + money in - money out must equal the closing balance."""
    txns = parse_mpesa(mpesa_files[0])            # newest first
    newest, oldest = txns[0], txns[-1]

    oldest_signed = oldest["amount"] if oldest["direction"] == "in" else -oldest["amount"]
    opening = oldest["balance"] - oldest_signed

    ins = sum(t["amount"] for t in txns if t["direction"] == "in")
    outs = sum(t["amount"] for t in txns if t["direction"] == "out")

    assert round(opening + ins - outs, 2) == round(newest["balance"], 2)
```

### Step 1.4 — One entry point for any statement

The Upload screen should not need to know which parser to call. Add `app/parsers/__init__.py`:

```python
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
        # M-Pesa PDFs are handled in Step 1.5; everything else is treated as I&M bank
        return bank.run(file_path, account)
    raise ValueError(f"Unsupported statement type: {suffix}")
```

### Step 1.5 — M-Pesa PDF statements (stretch — only if Gate 1 is on track)

Safaricom emails M-Pesa statements as password-protected PDFs. The .xlsx route already works, so this step is optional for v1.0. If you do it, create `parsers/mpesa_pdf.py`. Open the file in memory, then reuse the same `transform()` idea:

```python
import io
import pikepdf
import pdfplumber


def extract(file_path, password: str) -> list[list]:
    """Decrypts the PDF in memory and returns every table row from every page."""
    with pikepdf.open(file_path, password=password) as pdf:
        buffer = io.BytesIO()
        pdf.save(buffer)                       # decrypted copy, never written to disk
    buffer.seek(0)
    rows = []
    with pdfplumber.open(buffer) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                rows.extend(table)
    return rows
```

Map the PDF columns to the same shared format. Add a reconciliation test, and add a branch in `load_statement()` that asks for the password.

---

## Phase 2 — The Categorisation Engine (22 – 26 Oct)

### Step 2.1 — Fix the rule order in `categories.yaml`

Three changes, based on the test run in Step 0.5:

1. **Move the charge rules to the very top** and make them specific. Otherwise `customer transfer` (People Transfer) catches `Customer Transfer of Funds Charge` first:
   ```yaml
   Charges & Fees:
     - transfer of funds charge
     - pay bill charge
     - withdrawal charge
     - pay merchant charge
     - excise duty
   ```
2. **Merge the two `Shopping` blocks.** YAML keeps only the second one, so `naivas`, `quickmart` and `carrefour` are being ignored right now. Also remove `merchant` and `direct pay`. They catch almost every till payment and hide the real category.
3. **Add the missing rules** found in the data:
   ```yaml
   Fuliza Advance:
     - overdraft of credit party

   Bank Transfer:
     - transfer from bank          # own I&M money moving to M-Pesa

   Savings:
     - ziidi mmf
     - unit trust invest
   ```

Remove the `Fuliza` rule (`fuliza m-pesa amount is`). It is SMS wording and never appears in the statement.

### Step 2.2 — Write `core/categorize.py`

Keep the same "first match wins" behaviour the YAML comments already describe:

```python
"""
Rule-based transaction categoriser.

Rules are read top to bottom from categories.yaml; the first category with a matching keyword wins.
Learned rules (from the review queue) are checked before the YAML rules.
"""
from __future__ import annotations

from pathlib import Path
import yaml

RULES_PATH = Path(__file__).parent / "categories.yaml"
UNCATEGORIZED = "Uncategorized"


def load_rules(path: str | Path = RULES_PATH) -> list[tuple[str, list[str]]]:
    """
    Loads category rules from YAML, keeping file order.
    Returns:
        A list of (category, [lower-case keywords]) tuples. Blank keywords are dropped.
    """
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    return [
        (category, [str(k).lower().strip() for k in (keywords or []) if k is not None and str(k).strip()])
        for category, keywords in raw.items()
    ]


def categorize(txn: dict, rules: list[tuple[str, list[str]]], learned: list[tuple[str, str]] | None = None) -> str:
    """
    Returns the category for one transaction.
    Args:
        txn: a normalized transaction dict.
        rules: output of load_rules().
        learned: optional (keyword, category) pairs saved from the review queue; checked first.
    """
    text = txn["description"].lower()
    for keyword, category in learned or []:
        if keyword in text:
            return category
    for category, keywords in rules:
        if any(k in text for k in keywords):
            return category
    return UNCATEGORIZED


def categorize_all(txns: list[dict], rules, learned=None) -> list[dict]:
    """Adds a 'category' key to every transaction and returns the list."""
    for t in txns:
        t["category"] = categorize(t, rules, learned)
    return txns
```

### Step 2.3 — Map every category to a flow type

Create `core/flows.py`. This one table stops Fuliza advances from looking like income and stops bank top-ups from being counted twice:

```python
FLOW_TYPES = {
    # counted as spending
    "Rent": "spend", "Power": "spend", "Water": "spend", "Internet & TV Subscriptions": "spend",
    "Airtime": "spend", "Shopping": "spend", "Groceries": "spend", "Restaurant": "spend",
    "Butchery": "spend", "Beauty": "spend", "Transport": "spend", "Travel": "spend",
    "People Transfer": "spend", "Family Support": "spend", "Personal": "spend",
    "Withdrawal": "spend", "Charges & Fees": "spend",
    # not spending
    "Salary": "income",
    "Bank Transfer": "own_transfer",
    "Savings": "savings",
    "Fuliza Advance": "loan", "Loan Repayment": "loan",
    "Uncategorized": "spend",   # unknown outflow is still spending — it just isn't accounted for
}


def flow_type(category: str, direction: str) -> str:
    """Flow type for a category; money coming in with no known category is treated as income."""
    if direction == "in" and category == "Uncategorized":
        return "income"
    return FLOW_TYPES.get(category, "spend")
```

### Step 2.4 — Measure the baseline accountability score

Write `scripts/score_rules.py`. It runs the categoriser over all real files and prints the score, plus the 20 most common uncategorised descriptions (digits replaced with `#`, so similar rows group together). Re-run it after every change to the YAML. This is the number that decides Gate 1.

```python
import re, collections, glob
from app.parsers import load_statement
from app.core.categorize import load_rules, categorize_all, UNCATEGORIZED
from app.core.flows import flow_type

rules = load_rules()
txns = [t for f in glob.glob("data/*") for t in categorize_all(load_statement(f), rules)]
spend = [t for t in txns if t["direction"] == "out" and flow_type(t["category"], "out") == "spend"]

total = sum(t["amount"] for t in spend)
known = sum(t["amount"] for t in spend if t["category"] != UNCATEGORIZED)
print(f"Accountability score: {known / total:.1%}")

misses = collections.Counter(re.sub(r"\d", "#", t["description"])[:50]
                             for t in spend if t["category"] == UNCATEGORIZED)
for text, n in misses.most_common(20):
    print(n, text)
```

### Step 2.5 — Unit tests for the categoriser

Create `tests/test_categorize.py` with made-up descriptions copied from the real patterns:

```python
from app.core.categorize import load_rules, categorize

RULES = load_rules()

def test_transfer_charge_is_a_fee():
    assert categorize({"description": "Customer Transfer of Funds Charge"}, RULES) == "Charges & Fees"

def test_fuliza_advance_is_not_spending():
    assert categorize({"description": "OverDraft of Credit Party"}, RULES) == "Fuliza Advance"

def test_ziidi_is_savings():
    assert categorize({"description": "Unit Trust Invest To 4155651 - ZIIDI MMF"}, RULES) == "Savings"

def test_learned_rule_beats_yaml():
    learned = [("milka", "Family Support")]
    assert categorize({"description": "Customer Transfer to - 07******123 MILKA"}, RULES, learned) == "Family Support"

def test_unknown_is_uncategorized():
    assert categorize({"description": "something new"}, RULES) == "Uncategorized"
```

---

## Phase 3 — Local Storage (27 – 29 Oct)

### Step 3.1 — Design the SQLite schema

Create `core/db.py`. Use plain `sqlite3`; no ORM is needed for one local user. All data lives in one database file, `pesaclarity.db` in the project root (git-ignored).

```python
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "pesaclarity.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    personal_budget REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY,
    ref         TEXT NOT NULL UNIQUE,          -- built key from Step 1.1
    member_id   INTEGER REFERENCES members(id),
    date        TEXT NOT NULL,                 -- ISO yyyy-mm-dd
    description TEXT NOT NULL,
    amount      REAL NOT NULL,
    direction   TEXT NOT NULL CHECK (direction IN ('in','out')),
    balance     REAL,
    source      TEXT NOT NULL,
    account     TEXT NOT NULL,
    category    TEXT NOT NULL,
    flow_type   TEXT NOT NULL,
    is_loan_advance INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS splits (
    id             INTEGER PRIMARY KEY,
    transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    category       TEXT NOT NULL,
    amount         REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS learned_rules (
    id       INTEGER PRIMARY KEY,
    keyword  TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    created  TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS budgets (
    month    TEXT NOT NULL,                    -- yyyy-mm
    category TEXT NOT NULL,
    amount   REAL NOT NULL,
    PRIMARY KEY (month, category)
);
CREATE TABLE IF NOT EXISTS goals (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL,
    target  REAL NOT NULL,
    saved   REAL NOT NULL DEFAULT 0,
    due     TEXT
);
CREATE TABLE IF NOT EXISTS support_envelope (
    year          INTEGER NOT NULL,
    monthly_limit REAL NOT NULL,
    PRIMARY KEY (year)
);
CREATE TABLE IF NOT EXISTS support_lump_sums (
    id     INTEGER PRIMARY KEY,
    year   INTEGER NOT NULL,
    label  TEXT NOT NULL,                      -- e.g. "School fees — nephew, Term 1"
    amount REAL NOT NULL,
    due    TEXT
);
CREATE TABLE IF NOT EXISTS uploads (
    id        INTEGER PRIMARY KEY,
    file_name TEXT NOT NULL,
    member_id INTEGER REFERENCES members(id),
    added     INTEGER NOT NULL,
    skipped   INTEGER NOT NULL,
    uploaded  TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    """Opens the database and makes sure every table exists."""
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    return con
```

### Step 3.2 — Save transactions without duplicates

The `UNIQUE` on `ref` does the work. `INSERT OR IGNORE` skips anything already stored, so uploading the same statement twice is harmless:

```python
def save_transactions(con, txns: list[dict], member_id: int) -> tuple[int, int]:
    """Inserts transactions; returns (added, skipped)."""
    before = con.total_changes
    con.executemany(
        """INSERT OR IGNORE INTO transactions
           (ref, member_id, date, description, amount, direction, balance,
            source, account, category, flow_type, is_loan_advance)
           VALUES (:ref, :member_id, :date, :description, :amount, :direction, :balance,
                   :source, :account, :category, :flow_type, :is_loan_advance)""",
        [{**t, "member_id": member_id, "date": t["date"].isoformat(),
          "is_loan_advance": int(t.get("is_loan_advance", False))} for t in txns],
    )
    con.commit()
    added = con.total_changes - before
    return added, len(txns) - added
```

### Step 3.3 — One function for the whole import

`core/pipeline.py` joins Phases 1–3. The Upload screen calls only this:

```python
from app.parsers import load_statement
from app.core.categorize import load_rules, categorize_all
from app.core.flows import flow_type
from app.core import db


def import_statement(file_path, member_id: int, con=None) -> dict:
    con = con or db.connect()
    learned = [(r["keyword"], r["category"]) for r in con.execute("SELECT keyword, category FROM learned_rules")]
    txns = categorize_all(load_statement(file_path), load_rules(), learned)
    for t in txns:
        t["flow_type"] = flow_type(t["category"], t["direction"])
    added, skipped = db.save_transactions(con, txns, member_id)
    con.execute("INSERT INTO uploads (file_name, member_id, added, skipped) VALUES (?,?,?,?)",
                (str(file_path), member_id, added, skipped))
    con.commit()
    return {"added": added, "skipped": skipped,
            "to_review": sum(t["category"] == "Uncategorized" for t in txns)}
```

Test it with a temporary database: `db.connect(tmp_path / "test.db")`.

---

## Phase 4 — Review Queue, Learned Rules and Splits (30 Oct – 1 Nov)

### Step 4.1 — Review queue

The queue is a query, not a separate table:

```python
def review_queue(con, month: str | None = None):
    sql = "SELECT * FROM transactions WHERE category = 'Uncategorized' AND direction = 'out'"
    args = []
    if month:
        sql += " AND substr(date, 1, 7) = ?"
        args.append(month)
    return con.execute(sql + " ORDER BY amount DESC", args).fetchall()
```

Sort by amount so the household fixes the biggest unknowns first. That raises the score fastest.

### Step 4.2 — Turn a correction into a rule

When the household relabels a row, they choose the keyword (pre-filled with the payee name from the description). Save the rule, then re-label every matching row:

```python
from app.core.flows import flow_type


def learn_rule(con, keyword: str, category: str) -> int:
    """Saves a learned rule and applies it to all matching Uncategorized rows. Returns rows updated."""
    keyword = keyword.lower().strip()
    con.execute("INSERT OR REPLACE INTO learned_rules (keyword, category) VALUES (?, ?)", (keyword, category))
    cur = con.execute(
        """UPDATE transactions SET category = ?, flow_type = ?
           WHERE category = 'Uncategorized' AND lower(description) LIKE ?""",
        (category, flow_type(category, "out"), f"%{keyword}%"),
    )
    con.commit()
    return cur.rowcount
```

Learned rules live in the database, not in `categories.yaml`. That keeps the YAML clean and lets the household undo a rule from the app.

### Step 4.3 — Split a transaction

A Naivas trip of KES 4,200 can be KES 3,500 Groceries and KES 700 Personal. Splits must add up to the original amount exactly:

```python
def split_transaction(con, transaction_id: int, parts: list[tuple[str, float]]) -> None:
    amount = con.execute("SELECT amount FROM transactions WHERE id = ?", (transaction_id,)).fetchone()["amount"]
    if round(sum(a for _, a in parts), 2) != round(amount, 2):
        raise ValueError(f"Split parts must add up to {amount:,.2f}")
    con.execute("DELETE FROM splits WHERE transaction_id = ?", (transaction_id,))
    con.executemany("INSERT INTO splits (transaction_id, category, amount) VALUES (?, ?, ?)",
                    [(transaction_id, c, a) for c, a in parts])
    con.commit()
```

Every total in Phase 5 must use split amounts when a split exists. Build them on one SQL view so this is never forgotten:

```sql
CREATE VIEW IF NOT EXISTS ledger AS
SELECT t.id, t.member_id, t.date, t.direction, t.flow_type,
       COALESCE(s.category, t.category) AS category,
       COALESCE(s.amount,   t.amount)   AS amount
FROM transactions t LEFT JOIN splits s ON s.transaction_id = t.id;
```

### Step 4.4 — Gate 1 (1 Nov)

Run `scripts/score_rules.py` and the full test suite. **Pass:** accountability score ≥ 90% on all six months, all tests green, every file reconciles. **If it fails:** spend the first days of Phase 5 clearing the top uncategorised patterns, and move the Kiswahili work (Phase 8) to after December.

---

## Phase 5 — Analytics and Privacy (2 – 4 Nov)

Create `core/analytics.py`. Every function reads from the `ledger` view and returns plain Python or a pandas DataFrame, so the dashboard only displays results.

### Step 5.1 — Monthly totals and the accountability score

```python
import pandas as pd


def month_ledger(con, month: str) -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM ledger WHERE substr(date, 1, 7) = ?", con, params=(month,))


def accountability_score(df: pd.DataFrame) -> float:
    spend = df[(df.direction == "out") & (df.flow_type == "spend")]
    total = spend.amount.sum()
    if total == 0:
        return 1.0
    return spend.loc[spend.category != "Uncategorized", "amount"].sum() / total


def month_summary(con, month: str) -> dict:
    df = month_ledger(con, month)
    return {
        "income": df.loc[(df.direction == "in") & (df.flow_type == "income"), "amount"].sum(),
        "spending": df.loc[(df.direction == "out") & (df.flow_type == "spend"), "amount"].sum(),
        "saved": df.loc[(df.direction == "out") & (df.flow_type == "savings"), "amount"].sum(),
        "fees": df.loc[df.category == "Charges & Fees", "amount"].sum(),
        "fuliza_repaid": df.loc[df.category == "Loan Repayment", "amount"].sum(),
        "score": accountability_score(df),
    }
```

The month-on-month nudge is `month_summary(this)["score"] - month_summary(last)["score"]`, shown as a positive message when it goes up.

### Step 5.2 — Budget status (one colour system everywhere)

```python
def budget_status(spent: float, budget: float) -> str:
    """'green' under 80%, 'amber' 80–100%, 'red' over 100%."""
    if budget <= 0:
        return "green" if spent == 0 else "red"
    ratio = spent / budget
    if ratio < 0.8:
        return "green"
    if ratio <= 1.0:
        return "amber"
    return "red"
```

Put the matching colours in one place (`dashboard/theme.py`) and use them on every screen.

### Step 5.3 — The privacy layer

Create `core/privacy.py`. Shared screens must only ever receive data that has been through this function:

```python
PRIVATE_CATEGORIES = {"Personal"}


def shared_view(df: pd.DataFrame, members: pd.DataFrame) -> pd.DataFrame:
    """
    Replaces each member's private rows with one total per member, so no shared screen
    can list individual personal purchases.
    """
    private = df[df.category.isin(PRIVATE_CATEGORIES)]
    public = df[~df.category.isin(PRIVATE_CATEGORIES)]
    totals = (private.groupby("member_id", as_index=False)["amount"].sum()
                     .assign(category="Personal (total)", direction="out", flow_type="spend",
                             description="Private — total only"))
    return pd.concat([public, totals], ignore_index=True)
```

Add the test that protects the promise:

```python
def test_shared_view_never_lists_personal_rows():
    out = shared_view(sample_df_with_personal(), sample_members())
    assert "Personal" not in set(out.category)
    assert (out.category == "Personal (total)").sum() == sample_members().shape[0]
```

---

## Phase 6 — Streamlit Dashboard: Core Screens (5 – 15 Nov)

### Step 6.1 — Structure

```
dashboard/
├── app.py                 ← entry point: sidebar (member, month, language), then Overview
├── theme.py               ← status colours, number formatting (KES 12,345)
├── i18n.py                ← t("key") helper, reads app/i18n/en.yaml or sw.yaml
└── pages/
    ├── 1_Spending.py
    ├── 2_Shared_Goals.py
    ├── 3_Family_and_Friends.py
    ├── 4_Monthly_Summary.py
    └── 5_Upload.py
```

Run with `streamlit run dashboard/app.py`. Add a `start.command` file (macOS) that does the same, so a family member can double-click it.

### Step 6.2 — Upload screen (build first — every other screen needs data)

```python
import tempfile, streamlit as st
from pathlib import Path
from app.core.pipeline import import_statement

st.title(t("upload.title"))
member_id = st.session_state["member_id"]
file = st.file_uploader(t("upload.prompt"), type=["xlsx", "pdf"])
if file:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / file.name
        path.write_bytes(file.getvalue())          # temporary copy, deleted straight after
        result = import_statement(path, member_id)
    st.success(t("upload.done").format(**result))
    if result["to_review"]:
        st.info(t("upload.review_prompt").format(n=result["to_review"]))
```

### Step 6.3 — Overview screen

Use the four `st.metric` tiles from `month_summary()` (income, spending, saved, fees), plus a Plotly gauge for the accountability score with the month-on-month change as its delta. Add one line of plain-language nudge text, for example *"You can account for 8 more shillings in every 100 than last month."*

### Step 6.4 — Spending screen

- Category breakdown: a horizontal bar chart, sorted largest first.
- Budget vs actual table, with the status colour from Step 5.2 per row and an editable budget column (`st.data_editor`) that saves to `budgets`.
- Transaction table (from `shared_view`), filterable by category.
- Review queue section: each row shows the description, amount and a category drop-down. A pre-filled keyword box calls `learn_rule()`.
- "Split" button on any row: opens a small form that calls `split_transaction()`.

### Step 6.5 — Gate 2 (15 Nov)

Primary Partner 1 uploads the **October** statement on his own and answers three questions from the screens: How much came in? Where did the most go? What is our score? **If it fails:** simplify the Upload flow and the wording before starting Phase 7.

---

## Phase 7 — Goals, Family Support Envelope, Private Budgets (16 – 29 Nov)

### Step 7.1 — Shared Goals screen

Goals come from the `goals` table. `saved` is updated in two ways: automatically from `Savings` rows linked to a goal, and manually for MMF or SACCO balances the statements cannot see. Show one `st.progress` bar per goal, with "KES X of Y — due Z".

### Step 7.2 — Family & Friends envelope (monthly and yearly)

The yearly lump sums (school fees for a relative, a wedding contribution) are spread across the year, so the monthly set-aside is predictable:

```python
def envelope_for_month(con, year: int) -> float:
    monthly = con.execute("SELECT monthly_limit FROM support_envelope WHERE year = ?", (year,)).fetchone()
    lumps = con.execute("SELECT COALESCE(SUM(amount), 0) AS s FROM support_lump_sums WHERE year = ?",
                        (year,)).fetchone()["s"]
    return (monthly["monthly_limit"] if monthly else 0) + lumps / 12


def check_support_request(con, month: str, request_amount: float) -> dict:
    """What happens if we send this amount now? Used for the before-you-send alert."""
    limit = envelope_for_month(con, int(month[:4]))
    used = con.execute("""SELECT COALESCE(SUM(amount), 0) AS s FROM ledger
                          WHERE category = 'Family Support' AND substr(date, 1, 7) = ?""",
                       (month,)).fetchone()["s"]
    over_by = max(0.0, used + request_amount - limit)
    return {"limit": limit, "used": used, "remaining": limit - used, "over_by": over_by,
            "options": ["approve", "delay", "split"] if over_by else ["approve"]}
```

On the screen, a small "Planning to send?" box takes an amount and shows the result before any money moves. Example: *"This would go KES 1,000 over this month's envelope. Approve anyway, move it to next month, or split it?"* That is the alert Family Friend 1 singled out in testing.

### Step 7.3 — Private personal budgets

Each member sets `members.personal_budget`. Shared screens show only `Personal (total)` and a status colour. A member viewing **their own** profile in the sidebar can see their own itemised list. Everyone else cannot.

### Step 7.4 — Gate 3 (29 Nov)

All of F1–F9 work on real data. The privacy test passes, and a manual check confirms no shared screen lists personal purchases. **If it fails:** drop PDF export and reminders (Phase 8) from v1.0.

---

## Phase 8 — Monthly Summary, Kiswahili, Reminders (30 Nov – 6 Dec)

### Step 8.1 — WhatsApp-ready summary

Build the message from `month_summary()` and the top three categories. Plain text only, so it pastes cleanly into WhatsApp:

```python
def whatsapp_summary(s: dict, top: list[tuple[str, float]], lang: str = "en") -> str:
    lines = [
        t("summary.header", lang).format(month=s["month"]),
        t("summary.income", lang).format(v=s["income"]),
        t("summary.spending", lang).format(v=s["spending"]),
        t("summary.saved", lang).format(v=s["saved"]),
        t("summary.score", lang).format(v=s["score"]),
        t("summary.top", lang),
        *[f"• {c}: KES {a:,.0f}" for c, a in top],
    ]
    return "\n".join(lines)
```

Show it in `st.code()` so it has a copy button. The summary uses `shared_view`, so it never reveals personal items.

### Step 8.2 — PDF export

Use ReportLab to produce a one-page PDF with the same figures, the budget table and the goal progress. Offer it with `st.download_button`. Save nothing to disk except what the user downloads.

### Step 8.3 — Kiswahili toggle

Every string on screen goes through `t("key")`. Store the strings in `app/i18n/en.yaml` and `app/i18n/sw.yaml`, with the same keys in both:

```yaml
# sw.yaml
overview.score: "Kiwango cha kufuatilia pesa"
overview.income: "Mapato"
overview.spending: "Matumizi"
upload.prompt: "Pakia taarifa yako ya M-Pesa au benki"
```

Add a test that both files have exactly the same keys, so a missing translation is caught before release. Ask Family Friend 2 to review the Kiswahili wording in Phase 10.

### Step 8.4 — Statement reminder

On app start, read the latest `uploads.uploaded`. If it is more than 30 days old, or a new calendar month has started since then, show an `st.info` banner on the Overview: *"Your new M-Pesa statement should be ready — download it and upload it here."* No background service is needed. The reminder appears whenever the app is opened.

---

## Phase 9 — Tests (written alongside every phase, completed by 6 Dec)

By release, `tests/` should contain at least:

| File | What it checks |
|---|---|
| `test_mpesa_parser.py` | Existing tests + receipt `ref` captured + balance reconciliation (Step 1.3) |
| `test_bank_parser.py` | Existing tests + `ref` and unified `is_loan_advance` key |
| `test_categorize.py` | Rule order (charges, Fuliza, Ziidi), learned rules win, unknown → Uncategorized |
| `test_flows.py` | Fuliza advance is `loan`, bank top-up is `own_transfer`, uncategorised inflow is `income` |
| `test_db.py` | Re-importing the same file adds 0 rows; splits must add up |
| `test_analytics.py` | Score = 100% when everything is categorised; budget status boundaries at 80% and 100% |
| `test_privacy.py` | `shared_view` never returns a `Personal` row |
| `test_envelope.py` | Lump sums spread ÷ 12; `over_by` correct; options offered only when over |
| `test_i18n.py` | `en.yaml` and `sw.yaml` have identical keys |

Use made-up transactions in every unit test. Only the reconciliation tests touch `data/`, and they skip when it is missing.

```bash
python -m pytest -v
```

All tests must pass before Phase 10.

---

## Phase 10 — User Testing and Release (7 – 18 Dec)

### Step 10.1 — Prepare a demo database

Write `scripts/seed_demo.py`. It fills a separate `demo.db` with made-up members, transactions, goals and an envelope near its limit. Use it for any screenshots or presentations, never the real database.

### Step 10.2 — Test with the five original participants (7 – 13 Dec)

Give each person the same short task list and note where they get stuck:

1. Upload this month's statement.
2. Tell me your accountability score and whether it went up.
3. Find the category you spent most on.
4. Fix one item in the review queue.
5. Check whether a KES 3,000 request from a relative fits this month's envelope.
6. Switch to Kiswahili and copy the WhatsApp summary.
7. *(Young adult only)* Confirm that no one else can see what is in your Personal spending.

Fix anything that blocks a task. Log everything else as v1.1 work.

### Step 10.3 — README

Write the README with these sections, in this order:

1. **Problem statement** — one paragraph from `OVERVIEW.md`.
2. **What it does** — the four layers and six screens, with a screenshot from the demo database.
3. **Install and run** — `python -m venv env`, `pip install -r requirements.txt`, `streamlit run dashboard/app.py`.
4. **Adding your own rules** — how `categories.yaml` and the review queue work.
5. **Privacy** — data stays local, `data/` and `*.db` are git-ignored, how personal spending is protected.
6. **Known limitations** — rule-based categories only; M-Pesa PDF support (if not built); one laptop, no sync between devices.

### Step 10.4 — Tag the release (18 Dec)

```bash
python -m pytest
git add .
git commit -m "PesaClarity v1.0"
git tag v1.0
git push origin main --tags
```

---

## After December (v1.1 and later)

- **ML-assisted categorisation** (`app/ml/`): train a simple text classifier (TF-IDF + logistic regression) on the categories the household has confirmed. Use it only to *suggest* a category in the review queue, never to override a rule.
- **Multi-device access**: optional, and only with a clear privacy design.
- **More banks**: one parser per bank, using the same shared format.

---

## Implementation Order Summary

| Phase | Dates | What you build | Why this order |
|---|---|---|---|
| 0 | 12 – 18 Oct | Remove statements from git, clean tests, pin dependencies, note data facts | Safe, repeatable starting point |
| 1 | 19 – 21 Oct | Receipt refs, unified schema, real reconciliation, `load_statement()` | Everything downstream depends on correct, de-duplicable rows |
| 2 | 22 – 26 Oct | Fixed YAML, `categorize.py`, flow types, scoring script | The score decides Gate 1 |
| 3 | 27 – 29 Oct | SQLite schema, de-duplicated saves, `import_statement()` | Screens need stored data |
| 4 | 30 Oct – 1 Nov | Review queue, learned rules, splits, **Gate 1** | Pushes the score past 90% |
| 5 | 2 – 4 Nov | Analytics + privacy layer | Screens only display; logic lives here |
| 6 | 5 – 15 Nov | Upload, Overview, Spending screens, **Gate 2** | First real use by the household |
| 7 | 16 – 29 Nov | Goals, support envelope, private budgets, **Gate 3** | Builds on analytics and storage |
| 8 | 30 Nov – 6 Dec | WhatsApp summary, PDF, Kiswahili, reminders | Polish that depends on stable screens |
| 9 | ongoing → 6 Dec | Full test suite | Written alongside each phase |
| 10 | 7 – 18 Dec | Demo data, participant testing, README, **v1.0 release** | Final step — assumes everything works |
