import math

def estimate_put_hedge_cost(ticker, current_price, atr_14):
    """
    Estimates the hedging cost for a long stock position using an At-The-Money (ATM) Put Option
    expiring in 30 days.

    Args:
        ticker (str): The stock ticker symbol.
        current_price (float): The current stock price.
        atr_14 (float): The 14-day Average True Range.

    Returns:
        dict: A dictionary containing:
            - 'hedge_cost_per_share' (float): Estimated premium cost of 1-month ATM Put.
            - 'strike_price' (float): Strike price rounded to nearest standard tick (e.g., 0.05).
    """
    if current_price <= 0 or atr_14 <= 0:
        return 0.0, round(current_price, 2)

    # Assume implied volatility (IV) is proportional to `(atr_14 / current_price) * math.sqrt(252)`
    implied_volatility = (atr_14 / current_price) * math.sqrt(252)

    # Estimate the premium cost of a 1-month ATM Put option to protect the position
    # Cost = current_price * 0.4 * IV * sqrt(30/365)
    cost = current_price * 0.4 * implied_volatility * math.sqrt(30 / 365)

    # Strike price: current_price rounded to nearest standard tick
    # For Indian stocks, standard tick is typically 0.05
    strike_price = round(round(current_price / 0.05) * 0.05, 2)

    return cost, strike_price
