from fastapi import APIRouter

from .routes_account import router as account_router
from .routes_alerts import router as alerts_router
from .routes_auth import router as auth_router
from .routes_help import router as help_router
from .routes_learning import router as learning_router
from .routes_market import router as market_router
from .routes_news import router as news_router
from .routes_portfolio import router as portfolio_router
from .routes_tools import router as tools_router
from .routes_watchlists import router as watchlist_router


def build_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(auth_router)
    router.include_router(account_router)
    router.include_router(market_router)
    router.include_router(portfolio_router)
    router.include_router(watchlist_router)
    router.include_router(alerts_router)
    router.include_router(news_router)
    router.include_router(help_router)
    router.include_router(learning_router)
    router.include_router(tools_router)
    return router
