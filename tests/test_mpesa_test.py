
import datetime as dt

from app.parsers.mpesa import parse_mpesa, transform, _to_amount


## Tests _to_amount
def test_to_amount_negative_float():
    # withdrawals arrive negative but we need positive amounts for our calculations
    assert _to_amount(-123.45) == 123.45

def test_to_amount_string_with_commas():
    assert _to_amount("1,234.56") == 1234.56

def test_to_amount_blank():
    assert _to_amount(None) == 0.0


## Tests transform
def fake_mpesa_data():
    """A minimal M-PESA detailed-statement: header + a few rows. Mirrors the real layout: 0=receipt, 1=time, 3+5=details,
    9=paid in, 10=withdrawn, 12=balance"""
    header = ["Receipt No."] + [None]*12
    t = dt.datetime(2026, 5, 15, 14, 30)
    payment = ["ABC1", t, None, "Merchant Payment", None, "to 12345",None, None, None, None, -200.0, None, None, 1000.0]
    deposit = ["DEF2", t, None, "Salary", None, "from Employer",None, None, None, 3000.0, None, None, 5000.0]
    overdraft = ["GHI3", t, None, "Overdraft Advance", None, "Fuliza",None, None, None, 1000.0, None, None, 4000.0]

    return [header, payment, deposit, overdraft]


def test_transform_parse_transactions():
    '''Tests that transform correctly parses transactions from the raw M-PESA data, including handling of amounts and descriptions.'''
    txns = transform(fake_mpesa_data(), account="test-account")
    assert len(txns) == 3

def test_transform_amount_positive():
    '''Tests that the amounts in the transformed transactions are positive, even if they were negative in the raw data (e.g. for withdrawals).'''
    txns = transform(fake_mpesa_data(), account="test-account")
    assert all(t["amount"]>0 for t in txns)

def test_transform_direction():
    '''Tests that the direction of each transaction is correctly identified as "in" for deposits and "out" for withdrawals.'''
    txns = transform(fake_mpesa_data(), account="test-account")
    assert txns[0]["direction"] == "out"  # withdrawal
    assert txns[1]["direction"] == "in"   # paid-in

def test_transform_description():
    txns = transform(fake_mpesa_data(), account="test-account")
    assert txns[0]["description"] == "Merchant Payment to 12345"
    assert txns[1]["description"] == "Salary from Employer"


def test_transform_flag_overdraft():
    txns = transform(fake_mpesa_data(), account="test-account")
    flagged = [ t for t in txns if t["is_loan_advance"]]
    assert(len(flagged) == 1)
    assert flagged[0]["description"] == "Overdraft Advance Fuliza"


def test_transform_join_descriptions():
    txns = transform(fake_mpesa_data(), account="test-account")
    assert txns[0]["description"] == "Merchant Payment to 12345"
    assert txns[1]["description"] == "Salary from Employer"
    assert txns[2]["description"] == "Overdraft Advance Fuliza"


## RECONCILIATION TEST (NEED REAL DATA)
def test_mpesa_reconciles(mpesa_files):
    txns = parse_mpesa(mpesa_files[0])
    ins = sum(t["amount"] for t in txns if t["direction"] == "in")
    outs = sum(t["amount"] for t in txns if t["direction"] == "out")
    assert round(ins, 2) == round(outs, 2)