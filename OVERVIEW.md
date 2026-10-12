# PesaClarity — Household Finance Dashboard

## Problem Statement

Many hard-working Kenyan households earn steadily and still reach the end of the month with a near-zero balance and no way to explain where the money went. Most of their money moves through M-Pesa: salaries come in by bank transfer and go out again through paybills, tills, Fuliza and send-money. Each transaction leaves a record, but nobody in the household can read those records as a whole.

This creates three problems:

**1. Nobody can account for the money.** The only way to find out where money went is to scroll through hundreds of SMS alerts or a long statement and write the figures down by hand. One participant in the design thinking interviews spent hours copying M-Pesa messages into a notebook. Most people simply guess.

**2. Money conversations turn into arguments.** Because no one has trusted numbers, end-of-month talks happen from memory. The person who buys small, visible things gets blamed while the large, invisible costs (transaction charges, Fuliza repayments, unplanned support to relatives) go unnoticed.

**3. Existing tools see only part of the picture.** The M-Pesa app and bank apps each show one account. Generic budgeting apps expect manual entry and do not understand M-Pesa's data. None of them handle the social pressure of supporting extended family, or the need to keep one member's personal spending private.

Our own data shows the scale. Twelve months of one household's M-Pesa statement (May 2025 – May 2026) holds **3,137 transactions**, including:
- **494 Fuliza overdraft advances** and 188 Fuliza repayments. Each advance looks like money coming in, even though it is borrowed.
- **About 600 separate charge lines** (transfer, paybill, withdrawal and merchant charges), each one too small to notice.
- **158 transfers from the household's own bank account.** If they are counted as income, earnings look much higher than they really are.

## What We Are Building

PesaClarity is a local Python app that reads a household's M-Pesa and bank statements, sorts every transaction into a category, and shows the whole family the same trusted numbers. It works as four layers:

- **Layer 1 — Ingestion:** reads each statement file (M-Pesa .xlsx or PDF, I&M bank PDF) and turns it into one shared transaction format.
- **Layer 2 — Categorisation:** a configurable rules engine that labels every transaction (Rent, Groceries, Fuliza, Charges and so on). Anything it cannot label goes into a review queue. A correction made there becomes a permanent new rule.
- **Layer 3 — Analytics and privacy:** stores everything in a local SQLite database and works out the numbers the family cares about: the shilling accountability score, budget vs actual, savings goal progress and the family support envelope. Personal spending is summed per member **before** any screen can see it.
- **Layer 4 — Dashboard:** a Streamlit app with the six screens from prototype v2: Overview, Spending, Shared Goals, Family & Friends, Monthly Summary and Upload. It also has an English/Kiswahili toggle.

The household does one thing a month: upload the statement. Everything else is automatic. The result is a single number the family can work on together ("we can account for 93% of last month's spending"), budgets they can see, and a calm, evidence-based money conversation.

Everything runs on the household's own laptop. No data goes to a server, and running it costs KES 0.

---

## Technical Overview

Think of the app as a household accountant who never gets tired. First they collect every statement and copy each line into one ledger in the same format (ingestion). Then they go through the ledger with a rulebook: "anything to paybill 7629905 is rent", "anything to KPLC is power" (categorisation). Any line they do not recognise goes to a "please check" pile, and once you tell them what it is, they write that into the rulebook so they never ask again. Finally they prepare the monthly report. They are careful to show each person's private spending only as one total (analytics and privacy). The dashboard is that report, available any time.

---

## Layer 1 — Ingestion (Parsers)

### What problem does it solve?

Each statement has its own layout. The M-Pesa .xlsx export puts the transaction details across two columns and shows withdrawals as negative numbers. The I&M bank PDF has no "money in / money out" column, so the direction has to be worked out from whether the balance went up or down. The rest of the app should not have to care about any of that.

### What it does

Each parser follows the same **Extract → Transform** pattern already in `app/parsers/`. It returns a list of dictionaries in one shared format:

| Field | Example | Notes |
|---|---|---|
| `date` | `2026-05-14` | `datetime.date` |
| `description` | `Merchant Payment Online to 7937386 - SUSAN MUTUKU` | Details text, joined |
| `amount` | `200.0` | Always positive |
| `direction` | `"out"` | `"in"` or `"out"` |
| `balance` | `0.0` | Running balance after the transaction |
| `source` | `"mpesa"` | `"mpesa"` or `"bank"` |
| `account` | `"MPESA_Statement_2026-05-15…"` | Which file/account it came from |
| `ref` | `"UEEMF3V8QT\|out\|200.00\|Merchant Payment…"` | **To add.** Receipt no. + direction + amount + description (the receipt alone repeats), used to skip duplicates when a file is uploaded twice |
| `is_loan_advance` | `True` | Fuliza advance rows: kept for traceability, never counted as income |

### Current state

- `parsers/mpesa.py` works on the .xlsx statement. **Done.**
- `parsers/bank.py` works on I&M PDFs, and all six real statements (Nov 2025 – Apr 2026) match their own printed totals to the cent. **Done.**
- The two parsers name the Fuliza flag differently (`is_loan_advance` and `is_overdraft_helper`). This must be unified.
- M-Pesa PDF statements (password-protected, opened with `pikepdf`) are **not yet supported**.

---

## Layer 2 — The Categorisation Engine

### What problem does it solve?

Without categories, 3,137 transactions are just a long list. The household's real question is "where did it go?", and that needs every line labelled.

### What does "configurable" mean?

The rules are not written into the code. They live in `app/core/categories.yaml`, which the household can edit without touching Python. Rules are checked **from top to bottom and the first match wins**. Specific rules go at the top and greedy ones (like `charge`) go near the bottom:

```yaml
# Fees first — otherwise "Customer Transfer of Funds Charge" is caught by People Transfer
Charges & Fees:
  - transfer of funds charge
  - pay bill charge
  - withdrawal charge
  - pay merchant charge

Loan Repayment:
  - od loan repayment
  - overdraw

Rent:
  - "7629905"          # landlord paybill — numbers must be quoted

Savings:
  - ziidi mmf
  - unit trust invest
  - m-shwari
  - sacco
```

### How does it plug into the app?

```
Household uploads a statement
        ↓
Parser turns each row into the shared transaction format
        ↓
categorize.py checks learned rules (from past corrections) first, then categories.yaml
        ↓
First match → category set   |   No match → "Uncategorized" + added to the review queue
        ↓
Transaction saved to SQLite with its category and flow type (spend / income / own transfer / loan / savings)
        ↓
Household opens the Review screen, fixes "Uncategorized" rows, and each fix is saved as a new rule
```

### Why flow types matter

Not every outgoing shilling is spending, and not every incoming one is income. A Fuliza advance is a loan. A top-up from your own bank to M-Pesa just moves your own money. If these are counted the wrong way, income looks higher than it is and spending gets counted twice. Each category therefore maps to one **flow type**, and only `spend` rows count towards spending totals:

| Flow type | Example categories | Counted as spending? |
|---|---|---|
| `spend` | Rent, Groceries, Transport, Charges & Fees, Family Support | Yes |
| `income` | Salary, Business income | No (income) |
| `own_transfer` | Bank Transfer, KCB M-Pesa / M-Shwari moves | No — neutral |
| `loan` | Fuliza advance, Loan Repayment | Shown separately as "cost of borrowing" |
| `savings` | Savings, Investments (Ziidi MMF, SACCO) | No — shown on the Goals screen |

### Where it lives

```
app/
├── parsers/
│   ├── mpesa.py          ← done
│   ├── bank.py           ← done
│   └── mpesa_pdf.py      ← to build (pikepdf + pdfplumber)
├── core/
│   ├── categories.yaml   ← rules (fix order first)
│   ├── categorize.py     ← rules engine (currently empty)
│   ├── flows.py          ← category → flow type map
│   ├── db.py             ← SQLite schema + save/load
│   ├── analytics.py      ← accountability score, budgets, envelope
│   └── privacy.py        ← personal spending → totals only
├── i18n/
│   ├── en.yaml
│   └── sw.yaml
dashboard/
├── app.py                ← Streamlit entry point
└── pages/                ← one file per screen
tests/
```

The empty `app/api/` and `app/ml/` folders are **not used in v1.0**. Streamlit calls `app/core` directly, so a separate API is not needed. Machine-learning categorisation moves to after December, once there are enough corrected labels to train on.

### What are unit tests here?

Each rule and calculation gets a small test with made-up data, in the same style as the existing parser tests:

```python
def test_transfer_charge_is_a_fee_not_a_person():
    rules = load_rules()
    txn = {"description": "Customer Transfer of Funds Charge", "direction": "out"}
    assert categorize(txn, rules) == "Charges & Fees"
```

---

## Layer 3 — Analytics and Privacy

### The shilling accountability score

The headline number on the Overview screen:

```
accountability score = spending with a real category ÷ all spending   (for the month)
```

"Uncategorized" does not count as accounted for. The score rises as the household clears the review queue and the rulebook learns. **Target for v1.0: at least 90%.** Today's rules, run over the 12-month M-Pesa statement, leave about **15% of outgoing value uncategorised**, and much of the rest is in the wrong category. Fixing that is the first piece of work.

### Budgets and status colours

Each category has a monthly budget. One colour system is used everywhere, as the testers asked:

| Status | Rule |
|---|---|
| Green — on track | spent < 80% of budget |
| Amber — near limit | 80% – 100% |
| Red — exceeded | > 100% |

### Privacy

The young adult's main worry in the empathy interviews was feeling micromanaged. So `privacy.py` turns each member's `Personal` transactions into **one total and one status** before anything is passed to a shared screen. This happens in the data layer, not the UI, so a screen cannot show the detail even by accident. A test checks this.

---

## Layer 4 — The Dashboard

| Screen | What the household sees |
|---|---|
| Overview | Income, spending, accountability score with month-on-month nudge, cost of borrowing |
| Spending | Category breakdown, budget vs actual with status colours, transaction table, review queue, split a transaction |
| Shared Goals | Emergency fund, holiday, school fees progress bars; MMF and SACCO balances |
| Family & Friends | Monthly support envelope plus yearly view (lump sums ÷ 12); alert before a request would go over the limit, with approve / delay / split |
| Monthly Summary | WhatsApp-ready text message and PDF export |
| Upload | Upload a statement, see what was added, reminder when the next statement is due |

An English/Kiswahili toggle in the sidebar switches every label.

---

## How the layers work together — a monthly session

This is the walkthrough to show testers in December:

1. On 1 December, the Upload screen shows: *"Your November statement is ready to download."* Primary Partner 1 downloads it from the M-Pesa app and drags it in.
2. In about a second, 214 new transactions are added and 9 duplicates are skipped. 197 are categorised automatically. 17 go to the review queue.
3. He opens the review queue. Seven of the transfers are to his mother, so he labels them **Family Support** once. Next month those are automatic.
4. The Overview screen shows **accountability 96% (up from 88% in October)**, total spending, and a separate line for Fuliza fees, a cost nobody had noticed before.
5. The Family & Friends screen shows the support envelope is amber: KES 8,500 of 10,000 used. A planned school-fees lump sum for a relative is already set aside in the yearly view.
6. He taps **Monthly Summary**, copies the Kiswahili message, and pastes it into the family WhatsApp group. Members who never open the app still see the result.

*(The figures in this walkthrough are illustrative; the real numbers come from the household's own statement.)*

---

## What the success report looks like

The design thinking evaluation could only test reactions to a prototype. The working app makes real measurement possible:

| Measure | How it is calculated | v1.0 target |
|---|---|---|
| **Accountability score** | Categorised spend ÷ total spend, per month | ≥ 90% |
| **Review queue size** | Uncategorized transactions per new statement | Falls month on month |
| **Reconciliation** | Parsed totals vs the statement's own totals or balances | Exact match, every file |
| **Upload-to-insight time** | Time from upload to seeing the Overview | Under 1 minute |
| **Usability** | Testers who finish the set task list without help | 5 of 5 participants |
| **Privacy** | Shared screens showing itemised personal spending | Zero (enforced by a test) |

---

## Privacy note on our data

The statements in `data/` are real household financial records. They contain phone numbers (partly masked), full names of people money was sent to, paybill account numbers and balances.

1. `data/`, the SQLite database file and any exports must stay in `.gitignore` and must never be committed or uploaded.
2. Test files use **made-up** transactions only. The reconciliation tests that need real files already skip themselves when `data/` is missing. Keep it that way.
3. Password-protected M-Pesa PDFs are decrypted in memory only and never saved to disk unprotected.
4. Any screenshot used in a report or presentation must use a demo database with made-up names, not real statements.

---

## Timeline at a glance

| Dates (2026) | Phase | Gate |
|---|---|---|
| 12 – 18 Oct | Setup, rule fixes, test clean-up | |
| 19 Oct – 1 Nov | Categoriser, flow types, storage, review queue | **Gate 1 (1 Nov):** ≥ 90% accounted for on real data |
| 2 – 15 Nov | Overview, Spending and Upload screens | **Gate 2 (15 Nov):** household reads its own October data unaided |
| 16 – 29 Nov | Goals, Family & Friends envelope, private budgets | **Gate 3 (29 Nov):** all must-have features working |
| 30 Nov – 6 Dec | Monthly summary, Kiswahili, reminders | |
| 7 – 13 Dec | Testing with the 5 participants, fixes | |
| 14 – 17 Dec | Buffer week | |
| **18 Dec** | **v1.0 release** | |

See `DETAILED_TECHNICAL_PLAN.md` for the step-by-step build.
