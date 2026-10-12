"""
Maps every category to a flow type, so totals only count real spending.

    spend         -- counted as spending
    income        -- money earned
    own_transfer  -- your own money moving between your accounts (neutral)
    savings       -- money put aside
    loan          -- Fuliza advances and repayments (shown as cost of borrowing)
"""

FLOW_TYPES = {
    # not spending
    "Fuliza": "loan",
    "Loan Repayment": "loan",
    "Savings": "savings",
    "Chama": "savings",
    "Bank Transfer": "own_transfer",
    "Salary": "income",
    "Client Income": "income",
    "Money Received": "income",
    
    # spending
    "Charges & Fees": "spend",
    "Rent": "spend",
    "Power": "spend",
    "Water": "spend",
    "Internet & TV Subscriptions": "spend",
    "Airtime": "spend",
    "Shopping": "spend",
    "Groceries": "spend",
    "Restaurant": "spend",
    "Butchery": "spend",
    "Beauty": "spend",
    "Health": "spend",
    "Online Shopping": "spend",
    "Transport": "spend",
    "Travel": "spend",
    "Family transfer": "spend",
    "People Transfer": "spend",
    "Withdrawal": "spend",
    "Education": "spend",
    "Online payments": "spend",
    "Home and Maintenance": "spend",
    "Fitness / Recreation": "spend",
    "Books / libraries": "spend",
    "Uncategorized": "spend",   # unknown outflow is still spending — it just isn't accounted for
}


def flow_type(category: str, direction: str) -> str:
    """
    Returns the flow type for a transaction.
    Money coming IN keeps a non-spending type (a Fuliza advance stays 'loan',
    a chama payout stays 'savings'); any other money coming in counts as income.
    """
    kind = FLOW_TYPES.get(category, "spend")
    if direction == "in" and kind == "spend":
        return "income"
    return kind
