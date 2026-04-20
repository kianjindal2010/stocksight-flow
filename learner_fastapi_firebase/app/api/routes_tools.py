from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ..dependencies import current_uid, get_repository
from ..schemas.learning import ScenarioRequest, SipRequest


router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("/sip-calculator")
def sip_calculator(
    monthly_investment: float = Query(..., gt=0),
    years: int = Query(..., gt=0),
    annual_return_pct: float = Query(12.0),
    inflation_pct: float = Query(5.0),
):
    monthly_rate = annual_return_pct / 100 / 12
    periods = years * 12
    future_value = monthly_investment * (((1 + monthly_rate) ** periods - 1) / monthly_rate) * (1 + monthly_rate)
    real_value = future_value / ((1 + inflation_pct / 100) ** years)
    return {
        "monthly_investment": monthly_investment,
        "years": years,
        "future_value": round(future_value, 2),
        "inflation_adjusted_value": round(real_value, 2),
    }


@router.post("/sip-calculator")
def sip_calculator_post(payload: SipRequest):
    return sip_calculator(
        monthly_investment=payload.monthly_investment,
        years=payload.years,
        annual_return_pct=payload.annual_return_pct,
        inflation_pct=payload.inflation_pct,
    )


@router.get("/scenario-simulator")
def scenario_simulator(
    request: Request,
    market_move_pct: float = Query(0.0),
    add_cash: float = Query(0.0),
    uid: str = Depends(current_uid),
    repo=Depends(get_repository),
):
    market = repo.get_selected_market(uid)
    p = repo.get_portfolio(uid, market)
    new_market_value = p["market_value"] * (1 + market_move_pct / 100)
    new_cash = p["cash"] + add_cash
    scenario_total = new_cash + new_market_value
    delta_pct = ((scenario_total - p["total_value"]) / p["total_value"] * 100) if p["total_value"] else 0.0
    result = {
        "current_value": p["total_value"],
        "scenario_value": round(scenario_total, 2),
        "delta_pct": round(delta_pct, 2),
        "market_move_pct": market_move_pct,
        "added_cash": add_cash,
    }
    result["ai_tip"] = request.app.state.ai_advisor.tool_tip(
        uid=uid,
        market=market,
        topic="scenario",
        payload=result,
    )
    return result


@router.post("/scenario-simulator")
def scenario_simulator_post(payload: ScenarioRequest, request: Request, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    return scenario_simulator(
        request,
        market_move_pct=payload.market_move_pct,
        add_cash=payload.add_cash,
        uid=uid,
        repo=repo,
    )


@router.get("/risk-lite")
def risk_lite(request: Request, symbol: str = Query("AAPL"), uid: str = Depends(current_uid), repo=Depends(get_repository)):
    market = repo.get_selected_market(uid)
    risk = request.app.state.market_data.risk_lite(symbol, market)
    risk["ai_tip"] = request.app.state.ai_advisor.tool_tip(uid=uid, market=market, topic="risk", payload=risk)
    return risk


@router.get("/forecast-lite")
def forecast_lite(request: Request, symbol: str = Query("AAPL"), uid: str = Depends(current_uid), repo=Depends(get_repository)):
    market = repo.get_selected_market(uid)
    forecast = request.app.state.market_data.forecast_lite(symbol, market)
    forecast["ai_explainer"] = request.app.state.ai_advisor.forecast_explainer(
        uid=uid,
        market=market,
        symbol=symbol,
        payload=forecast,
    )
    return forecast


@router.get("/screener")
def screener(
    request: Request,
    preset: str = Query("top_gainers"),
    uid: str = Depends(current_uid),
    repo=Depends(get_repository),
):
    market = repo.get_selected_market(uid)
    rows = request.app.state.market_data.screener(market, preset=preset, limit=25)
    out = {"market": market, "preset": preset, "results": rows}
    out["ai_tip"] = request.app.state.ai_advisor.tool_tip(
        uid=uid,
        market=market,
        topic=f"screener-{preset}",
        payload={"total_results": len(rows), "top_rows": rows[:5]},
    )
    return out


@router.get("/market-mood")
def market_mood(request: Request, uid: str = Depends(current_uid), repo=Depends(get_repository)):
    market = repo.get_selected_market(uid)
    mood = request.app.state.market_data.market_mood(market)
    mood["ai_tip"] = request.app.state.ai_advisor.tool_tip(
        uid=uid,
        market=market,
        topic="market-mood",
        payload=mood,
    )
    return mood
