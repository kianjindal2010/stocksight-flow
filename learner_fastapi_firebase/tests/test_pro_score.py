from learner_fastapi_firebase.app.services.pro_score import score_stock, stock_ratios


def test_ratios_can_be_calculated_when_quote_has_no_fundamentals():
    def metric(label, first, second, unit="USD"):
        return {"label": label, "unit": unit, "points": [
            {"end": "2024-12-31", "value": first}, {"end": "2025-12-31", "value": second},
        ]}

    intel = {"quote": {"price": 100, "currency": "USD", "market_cap": 800},
             "company_facts": {"metrics": [
                 metric("Revenue", 80, 100), metric("Net income", 9, 20),
                 metric("Diluted EPS", 1, 2, "USD/shares"),
             ]}}
    ratios = stock_ratios(intel)
    assert ratios["profit_margin"]["value"] == 20
    assert ratios["revenue_growth"]["value"] == 25
    assert ratios["price_sales"]["value"] == 8
    assert ratios["annual_pe"]["value"] == 50
    assert "trailing_pe" not in ratios


def test_headline_sentiment_moves_score_but_cannot_replace_financial_evidence():
    sentiment = {"headlines": [{"group": group, "score": 90}
                               for group in ("company", "market", "sec")]}
    assert score_stock({}, {}, sentiment)["signal"] == "Insufficient data"
    intel = {"history": {"close": [100 + day / 2 for day in range(80)]},
             "benchmark": {"change_pct": 1}}
    ratios = {key: {"value": value} for key, value in {
        "profit_margin": 20, "operating_margin": 25, "roe": 20, "revenue_growth": 30,
        "earnings_growth": 20, "trailing_pe": 15, "forward_pe": 15, "ev_ebitda": 10,
        "peg": 1, "current_ratio": 2, "quick_ratio": 1.5, "debt_equity": .3,
    }.items()}
    bullish = score_stock(intel, ratios, sentiment)
    negative = {"headlines": [{"group": row["group"], "score": -90} for row in sentiment["headlines"]]}
    bearish = score_stock(intel, ratios, negative)
    assert bullish["score"] > bearish["score"]
    assert bullish["coverage"] == 100
    assert bullish["signal"] == "Buy"
    missing = score_stock(intel, ratios, {"headlines": []})
    assert missing["coverage"] == 80
    assert missing["factors"][-1]["score"] is None
