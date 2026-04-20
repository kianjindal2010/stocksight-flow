# StockSight Learner (FastAPI + Firebase)

Standalone learner-first app in `learner_fastapi_firebase/`.

## What this implementation is

- FastAPI backend only (no Django ORM, no SQLite/Postgres, no `cs50` SQL)
- Firebase Auth-first (`email/password` + Google Sign-In)
- Firestore-backed repository abstraction
- Existing styling preserved by reusing `styles.css` and app layout patterns
- Learner-focused features only (pro/admin/quant-heavy layers excluded in this folder)

## Quick start

1. Create a virtual environment.
2. Install deps:
   - `pip install -r learner_fastapi_firebase/requirements.txt`
3. Copy env:
   - `copy learner_fastapi_firebase\\.env.example learner_fastapi_firebase\\.env`
4. Fill Firebase + Resend values.
5. Add NVIDIA AI values (placeholder keys are already included):
   - `NVIDIA_API_KEY`
   - `NVIDIA_BASE_URL`
   - `NVIDIA_MODEL`
6. Run:
   - `uvicorn learner_fastapi_firebase.app.main:app --reload --host 127.0.0.1 --port 8010`

## Auth/session flow

- `POST /api/auth/signup`
- `POST /api/auth/login`
- `POST /api/auth/google`
- `POST /api/auth/logout`
- `GET /api/auth/session`

Session is verified from Bearer token or `ss_id_token` cookie in middleware.

## API surface (implemented)

- Account/workspace:
  - `GET/PUT /api/account/profile`
  - `GET/PUT /api/account/preferences`
  - `PUT /api/account/notifications`
  - `GET/PUT /api/account/saved-filters`
- Markets/search/quotes:
  - `GET /api/markets`
  - `POST /api/market/select`
  - `GET /api/search`
  - `GET /api/quote/{symbol}`
- Portfolio/trades/journal:
  - `GET /api/portfolio`
  - `GET /api/portfolio/performance`
  - `POST /api/trades/buy`
  - `POST /api/trades/sell`
  - `GET /api/trades/history`
  - `PUT /api/trades/journal/{trade_id}`
- Watchlists/alerts/news:
  - `GET/POST/PUT/DELETE /api/watchlists...`
  - `GET /api/watchlists/share/{watchlist_id}`
  - `GET/POST/DELETE /api/alerts...`
  - `GET /api/news/market`
  - `GET /api/news/stock/{symbol}`
  - `GET /api/news/sector`
  - `GET /api/news/macro`
  - `GET /api/calendar/events`
- Learner:
  - `GET /api/learning/dashboard`
  - `GET /api/learning/curriculum`
  - `POST /api/learning/checklist`
  - `GET /api/learning/weekly-summary`
  - `GET /api/learning/health-score`
  - `GET /api/learning/explain-portfolio`
  - `GET /api/learning/portfolio-move-why`
  - `GET /api/learning/mistakes`
  - `GET /api/learning/coach`
  - `GET /api/learning/chat/history`
  - `POST /api/learning/chat`
  - `DELETE /api/learning/chat/history`
  - `GET /api/learning/goals`, `PUT /api/learning/goals`
  - `GET /api/learning/center`
  - `GET /api/learning/quizzes`
  - `GET /api/learning/challenges`
  - `GET /api/learning/streaks`
- Tools:
  - `GET/POST /api/tools/sip-calculator`
  - `GET/POST /api/tools/scenario-simulator`
  - `GET /api/tools/risk-lite`
  - `GET /api/tools/forecast-lite`
  - `GET /api/tools/screener`
  - `GET /api/tools/market-mood`
- Help/support:
  - `GET /api/help/onboarding`
  - `GET /api/help/glossary`
  - `GET /api/help/tooltips`
  - `GET /api/help/support`

## Firestore model (logical)

- `users/{uid}` for profile/preferences/workspace settings
- Logical modules stored through repository for:
  - watchlists, alerts, notifications
  - portfolio/positions
  - trades/journal
  - learning progress/goals/streaks/challenges

## Notes

- Alert emails are sent through Resend.
- Firebase verification/reset email flows are wired through Identity Toolkit endpoints.
- Legacy app outside this folder is untouched.
