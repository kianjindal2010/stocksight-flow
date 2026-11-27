"""Transparent research scores and ratio fallbacks for the Pro stock report."""

from math import isfinite, sqrt
from statistics import mean, stdev


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (TypeError, ValueError):
        return None


def stock_ratios(intel, supplemental=()):
    quote = intel.get("quote") or {}
    fundamentals = intel.get("fundamentals") or {}
    rows = {}

    def put(key, value, source):
        value = number(value)
        if value is not None and key not in rows:
            rows[key] = {"value": value, "source": source}

    for key, value in (quote.get("ratios") or {}).items():
        put(key, value, "Yahoo Finance")
    put("dividend_yield_pct", quote.get("dividend_yield_pct"), "Yahoo Finance")
    for key, field, scale in (
        ("trailing_pe", "TrailingPE", 1), ("forward_pe", "ForwardPE", 1),
        ("price_book", "PriceToBookRatio", 1), ("price_sales", "PriceToSalesRatioTTM", 1),
        ("peg", "PEGRatio", 1), ("ev_ebitda", "EVToEBITDA", 1), ("ev_revenue", "EVToRevenue", 1),
        ("operating_margin", "OperatingMarginTTM", 100), ("profit_margin", "ProfitMargin", 100),
        ("roe", "ReturnOnEquityTTM", 100), ("roa", "ReturnOnAssetsTTM", 100),
        ("revenue_growth", "QuarterlyRevenueGrowthYOY", 100),
        ("earnings_growth", "QuarterlyEarningsGrowthYOY", 100),
    ):
        value = number(fundamentals.get(field))
        if value is not None:
            put(key, value * scale, "Alpha Vantage")
    for metrics, source in (
        ((intel.get("company_facts") or {}).get("metrics") or [], "Calculated from SEC annual filings"),
        (supplemental, "Calculated from Yahoo annual statements"),
    ):
        points = {
            metric["label"]: {
                point["end"]: (number(point.get("value")), metric.get("unit"))
                for point in metric.get("points", []) if point.get("end")
            }
            for metric in metrics if metric.get("label")
        }

        def divide(key, numerator, denominator, scale=1, positive=False):
            left, right = points.get(numerator, {}), points.get(denominator, {})
            for day in sorted(left.keys() & right.keys(), reverse=True):
                x, a = left[day]
                y, b = right[day]
                if a == b and x is not None and y is not None and (y > 0 if positive else y != 0):
                    put(key, x / y * scale, source)
                    return

        divide("profit_margin", "Net income", "Revenue", 100, True)
        divide("operating_margin", "Operating income", "Revenue", 100, True)
        divide("gross_margin", "Gross profit", "Revenue", 100, True)
        divide("current_ratio", "Current assets", "Current liabilities", positive=True)
        divide("debt_equity", "Total debt", "Equity", positive=True)
        divide("roa", "Net income", "Total assets", 100, True)
        divide("roe", "Net income", "Equity", 100, True)
        if quote.get("currency"):
            for key, label in (("price_sales", "Revenue"), ("price_book", "Equity")):
                annual_rows = points.get(label, {})
                if not annual_rows:
                    continue
                base, unit = annual_rows[max(annual_rows)]
                cap = number(quote.get("market_cap"))
                if unit == quote["currency"] and base is not None and base > 0 and cap is not None and cap > 0:
                    put(key, cap / base, "Market cap divided by latest annual " + label.lower())
            eps = points.get("Diluted EPS", {})
            if eps:
                value, unit = eps[max(eps)]
                price = number(quote.get("price"))
                if unit in {quote["currency"] + "/shares", quote["currency"] + " per share"} and value is not None and value > 0 and price is not None and price > 0:
                    put("annual_pe", price / value, "Price divided by latest annual diluted EPS")
        for key, label in (("revenue_growth", "Revenue"), ("earnings_growth", "Net income")):
            annual = sorted(points.get(label, {}).items())[-2:]
            if len(annual) == 2:
                (_, (previous, unit)), (_, (latest, latest_unit)) = annual
                if unit == latest_unit and previous is not None and previous > 0 and latest is not None:
                    put(key, (latest / previous - 1) * 100, source)
    return rows


def score_stock(intel, ratios, sentiment):
    factors = []

    def factor(label, weight, observations):
        available = [min(100, max(0, value)) for value in observations if value is not None]
        factors.append({"label": label, "weight": weight, "score": round(mean(available), 1) if available else None,
                        "coverage": len(available) / len(observations)})

    def scaled(key, midpoint, slope):
        value = number((ratios.get(key) or {}).get("value"))
        return None if value is None else 50 + (value - midpoint) * slope

    def multiple(key, midpoint, slope):
        value = number((ratios.get(key) or {}).get("value"))
        return 50 + (midpoint - value) * slope if value is not None and value > 0 else None

    factor("Profitability & growth", 25, [scaled("profit_margin", 10, 2), scaled("operating_margin", 15, 1.4),
           scaled("roe", 12, 1.5), scaled("revenue_growth", 5, 2), scaled("earnings_growth", 5, 1.25)])
    trailing = multiple("trailing_pe", 22, 2)
    factor("Valuation", 15, [trailing if trailing is not None else multiple("annual_pe", 22, 2), multiple("forward_pe", 20, 2),
           multiple("ev_ebitda", 14, 3), multiple("peg", 1.5, 25)])
    factor("Balance sheet", 10, [scaled("current_ratio", 1.4, 36), scaled("quick_ratio", 1, 35), scaled("debt_equity", .75, -30)])

    closes = [value for raw in (intel.get("history") or {}).get("close", [])
              if (value := number(raw)) is not None and value > 0]

    def trend(sessions):
        return None if len(closes) <= sessions else 50 + (closes[-1] / closes[-sessions-1] - 1) * 180

    returns = [end / start - 1 for start, end in zip(closes[-64:-1], closes[-63:])] if len(closes) >= 64 else []
    volatility = stdev(returns) * sqrt(252) if len(returns) > 1 else None
    peak = max(closes[-63:]) if len(closes) >= 22 else None
    drawdown = closes[-1] / peak - 1 if peak else None
    day = number((intel.get("benchmark") or {}).get("change_pct"))
    factor("Price momentum", 20, [trend(21), trend(63), 50 + day * 5 if day is not None else None])
    factor("Volatility & drawdown", 10, [
        50 + (0.30 - volatility) * 100 if volatility is not None else None,
        75 + drawdown * 180 if drawdown is not None else None,
    ])
    for label, group, weight in (("Company headlines", "company", 10), ("Market headlines", "market", 5), ("SEC filing headlines", "sec", 5)):
        scores = [row["score"] for row in sentiment.get("headlines", []) if row["group"] == group]
        factor(label, weight, [50 + mean(scores) / 2 if scores else None])

    active = [row for row in factors if row["score"] is not None]
    coverage = round(sum(row["weight"] * row["coverage"] for row in active))
    weight = sum(row["weight"] * row["coverage"] for row in active)
    score = round(sum(row["score"] * row["weight"] * row["coverage"] for row in active) / weight) if weight else None
    signal = "Insufficient data"
    if score is not None and coverage >= 55 and len(closes) >= 64:
        signal = "Buy" if score >= 65 else "Sell" if score <= 35 else "Hold"
    return {"score": score, "signal": signal, "coverage": coverage, "factors": factors,
            "sentiment": sentiment, "method": "Fixed research thresholds, not sector-relative. Missing inputs reduce coverage; scores under 55% coverage receive no signal."}
