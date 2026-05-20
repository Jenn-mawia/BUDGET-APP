from app.parsers.mpesa import parse

# change this to the real path of your M-PESA statement
transactions = parse("/Users/jeniphermawia/Downloads/budget app/MPESA_Statement_2026-05-15_to_2025-05-15_2547xxxxxx461.xlsx")

print(f"Transactions parsed: {len(transactions)}")

ins  = sum(t["amount"] for t in transactions if t["direction"] == "in")
outs = sum(t["amount"] for t in transactions if t["direction"] == "out")
print(f"Money IN total : {ins:,.2f}")
print(f"Money OUT total: {outs:,.2f}")

print("\nFirst 3 transactions:")
for t in transactions[:3]:
    print(f"  {t['date']} | {t['direction']} | {t['amount']:,.2f} | {t['description'][:40]}")