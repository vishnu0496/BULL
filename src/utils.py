def format_inr(value) -> str:
    """Format a numerical value as Indian Rupees with ASCII-safe text."""
    if value is None:
        return "INR 0.00"
    try:
        return f"INR {float(value):,.2f}"
    except (ValueError, TypeError):
        return f"INR {value}"


def format_percentage(value) -> str:
    """Format a numerical decimal or percentage as a percent string."""
    if value is None:
        return "0.00%"
    try:
        return f"{float(value):+.2f}%" if value != 0 else "0.00%"
    except (ValueError, TypeError):
        return f"{value}%"


def get_color_class(val) -> str:
    """Return styling color for positive and negative values."""
    if val is None:
        return "grey"
    try:
        if val > 0:
            return "green"
        if val < 0:
            return "red"
    except (ValueError, TypeError):
        pass
    return "grey"


def get_pnl_indicator(val) -> str:
    """Return ASCII-safe direction text."""
    if val is None:
        return ""
    try:
        if val > 0:
            return "UP"
        if val < 0:
            return "DOWN"
    except (ValueError, TypeError):
        pass
    return "FLAT"
