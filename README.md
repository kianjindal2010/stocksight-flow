# StockSight Learner (FastAPI + Firebase)

This repository now contains only the learner-focused Firebase/FastAPI stack in:

- `learner_fastapi_firebase/`

## Run

1. Install dependencies:
   - `pip install -r requirements.txt`
2. Configure env:
   - root `.env` and/or `learner_fastapi_firebase/.env`
3. Start:
   - `uvicorn learner_fastapi_firebase.app.main:app --reload --host 127.0.0.1 --port 1000`

## Notes

- Firebase Auth is wired for email/password and Google sign-in.
- Firestore is used when credentials are configured.
- If Firestore credentials are missing, the app falls back to in-memory repository so local development still works.

