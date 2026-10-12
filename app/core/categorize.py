""" Rule-based categoriser. 

The rules are read top to bottom from categories.yaml; the first category with a matching keyword wins.
Learned rules (saved from the review queue) are checked before the YAML rules."""

from __future__ import annotations
from pathlib import Path
import yaml
from app.core.flows import flow_type

RULES_PATH = Path(__file__).parent / "categories.yaml"
UNCATEGORIZED = "Uncategorized"

def load_rules(path: str | Path = RULES_PATH) -> list[tuple[str, list[str]]]:
    """
    Loads category rules from YAML file, keeping file order.
    Returns:
        A list of (category, [lower-case keywords]) tuples. Blank keywords are dropped.
    """
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    return [
        (category, [str(k).lower().strip() for k in (keywords or []) if k is not None and str(k).strip()])
        for category, keywords in raw.items()
    ]

def categorize(txn: dict, rules: list[tuple[str, list[str]]], learned: list[tuple[str, str]] | None = None):
    """
    Returns the category for one transaction.
    Args:
        txn: a normalized transaction dict (only 'description' is needed).
        rules: output of load_rules().
        learned: optional (keyword, category) pairs saved from the review queue; checked first.
    """
    text = txn['description'].lower()
    for keyword, category in learned or []:
        if keyword in text:
            return category
    for category, keywords in rules: 
        if any(k in text for k in keywords):
            return category
    return UNCATEGORIZED

def categorize_all(txns:list[dict], rules=None, learned = None) -> list[dict]:
    """Adds a 'category' key to every transaction and returns the list."""
    rules = rules if rules is not None else load_rules()
    for t in txns:
        t["category"] = categorize(t, rules, learned)
        t["flow_type"] = flow_type(t["category"], t['direction'] )
    return txns

