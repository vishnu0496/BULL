# src/constants.py
from datetime import datetime

NSE_HOLIDAYS_2025 = {
  "2025-08-15", "2025-08-27", "2025-10-02",
  "2025-10-20", "2025-10-23", "2025-11-05", 
  "2025-12-25"
}

NSE_HOLIDAYS_2026 = {
  "2026-01-26", "2026-02-19", "2026-03-30",
  "2026-04-02", "2026-04-06", "2026-04-14",
  "2026-04-30", "2026-05-01", "2026-08-15",
  "2026-10-02", "2026-11-09", "2026-12-25"
}

def is_nse_holiday(date_obj) -> bool:
    """Check if a date falls on a weekend or an NSE market holiday."""
    # Weekend check: Monday is 0, Sunday is 6
    if date_obj.weekday() >= 5:
        return True
    
    date_str = date_obj.strftime("%Y-%m-%d")
    return (date_str in NSE_HOLIDAYS_2025) or (date_str in NSE_HOLIDAYS_2026)
