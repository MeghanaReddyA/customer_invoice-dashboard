# utils.py
import pandas as pd

def compute_aging_bucket(due_date, today_date, outstanding):
    """
    Returns one of: 'Paid', 'Not Due', '1-30 days', '31-60 days', '61-90 days', '90+ days'
    Rules:
      - outstanding <= 0  -> 'Paid'
      - due_date in the future (relative to today_date) -> 'Not Due'
      - else bucket by days overdue
    """
    due_d = pd.to_datetime(due_date).date()
    today_d = pd.to_datetime(today_date).date()

    if outstanding <= 0:
        return "Paid"

    days_overdue = (today_d - due_d).days
    if days_overdue < 0:
        return "Not Due"
    elif days_overdue <= 30:
        return "1-30 days"
    elif days_overdue <= 60:
        return "31-60 days"
    elif days_overdue <= 90:
        return "61-90 days"
    else:
        return "90+ days"