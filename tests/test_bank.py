"""Quick manual test for the bank PDF parser."""
import glob
from app.parsers.bank import run, extract, extract_totals

files = sorted(glob.glob("/Users/jeniphermawia/Downloads/budget app/data/Statement for *.pdf"))

for f in files:
    name = f.split("/")[-1]
    txns = run(f)

    out_total = sum(t["amount"] for t in txns if t["direction"] == "out")
    in_total  = sum(t["amount"] for t in txns if t["direction"] == "in")

    # the bank's own stated totals, for comparison
    stated = extract_totals(extract(f))

    print(name)
    print(f"  transactions parsed : {len(txns)}")
    print(f"  money OUT (parsed)  : {out_total:,.2f}")
    print(f"  money IN  (parsed)  : {in_total:,.2f}")
    if stated:
        print(f"  money OUT (stated)  : {stated['withdrawals']:,.2f}")
        print(f"  money IN  (stated)  : {stated['deposits']:,.2f}")
        match = (abs(out_total - stated["withdrawals"]) < 0.01
                 and abs(in_total - stated["deposits"]) < 0.01)
        print(f"  reconciles?         : {'YES' if match else 'NO'}")
    print()

# show a few sample transactions from November
print("--- Sample: first 5 November transactions ---")
for t in run("/Users/jeniphermawia/Downloads/budget app/data/Statement for 30-November-2025.pdf")[:5]:
    print(f"  {t['date']} | {t['direction']:3} | {t['amount']:>10,.2f} | "
          f"bal={t['balance']:>11,.2f} | {t['description'][:45]}")