"""Tests for the bank PDF parser."""
from app.parsers.bank import run, transform, extract, extract_totals, _num


# --- Unit tests: _num --------------------------------------------------

def test_num_strips_commas():
    assert _num("1,234.56") == 1234.56


# --- Unit tests: transform ---------------------------------------------

def fake_bank():
    """Minimal PDF text: header, B/F, two withdrawals, one deposit.

    Mirrors the real interleaving: narrative wraps onto the lines around each amount line.
    """
    return [
        "Tran Date Value Date Ref No Withdrawals Deposits Balance Transaction Narrative",
        "01-11-25 20,513.40Cr B/F",
        "254729924393/MPESA Payment",
        "01-11-25 01-11-25 3,500.00 17,013.40Cr",
        "to 254729924393",
        "Salary credit",
        "05-11-25 05-11-25 10,000.00 27,013.40Cr",
        "from employer",
        "Shop payment",
        "06-11-25 06-11-25 1,000.00 26,013.40Cr",
        "to shop",
        "Total 4,500.00 10,000.00",
    ]


def test_transform_parses_txns():
    # 3 real transactions; B/F and Total are not transactions.
    txns = transform(fake_bank(), account="test")
    assert len(txns) == 3


def test_transform_direction_frm_bal():
    txns = transform(fake_bank(), account="test")
    assert txns[0]["direction"] == "out"  # 20,513 -> 17,013 (down)
    assert txns[1]["direction"] == "in"   # 17,013 -> 27,013 (up)
    assert txns[2]["direction"] == "out"  # 27,013 -> 26,013 (down)


def test_transform_amounts_positive():
    txns = transform(fake_bank(), account="test")
    assert all(t["amount"] > 0 for t in txns)


def test_transform_captures_description():
    txns = transform(fake_bank(), account="test")
    assert "MPESA Payment" in txns[0]["description"]


def test_extract_totals_reads_total_row():
    totals = extract_totals(fake_bank())
    assert totals == {"withdrawals": 4500.0, "deposits": 10000.0}


# --- Reconciliation test (needs real files) ----------------------------

def test_bank_reconciles_against_stated_totals(bank_files):
    """Each file's parsed totals must match its printed Total row."""
    for f in bank_files:
        txns = run(f)
        stated = extract_totals(extract(f))
        assert stated is not None, f"no Total row found in {f.name}"

        out_total = sum(t["amount"] for t in txns if t["direction"] == "out")
        in_total = sum(t["amount"] for t in txns if t["direction"] == "in")

        assert round(out_total, 2) == stated["withdrawals"], f.name
        assert round(in_total, 2) == stated["deposits"], f.name