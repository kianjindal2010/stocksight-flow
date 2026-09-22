from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import requests

from ..config import Settings
from .firestore_repo import FirestoreRepository


class AppwriteRepository(FirestoreRepository):
    """Stores each learner's complete state in a private Appwrite row."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(firestore_client=None)
        self.settings = settings
        self._sessions: dict[str, str] = {}

    def set_session(self, uid: str, session: str) -> None:
        if uid and session:
            self._sessions[uid] = session

    def get_session(self, uid: str) -> str:
        """Return the in-memory Appwrite session for a signed-in desktop user."""
        return self._sessions.get(uid, "")

    def _headers(self, uid: str) -> dict[str, str]:
        session = self._sessions.get(uid, "")
        if not session:
            raise RuntimeError("Your Appwrite session has expired. Please sign in again.")
        return {
            "X-Appwrite-Project": self.settings.appwrite_project_id,
            "X-Appwrite-Session": session,
            "Cookie": f"a_session_{self.settings.appwrite_project_id}={session}",
            "Content-Type": "application/json",
        }

    def _row_url(self, uid: str) -> str:
        return (
            f"{self.settings.appwrite_endpoint}/tablesdb/{self.settings.appwrite_database_id}"
            f"/tables/{self.settings.appwrite_state_table_id}/rows/{uid}"
        )

    def _load_state(self, uid: str) -> dict[str, Any]:
        cached = self._get_cached_state(uid)
        if cached is not None:
            return self._normalize_state(uid, cached)
        response = requests.get(self._row_url(uid), headers=self._headers(uid), timeout=15)
        if response.status_code == 404:
            return self._uid_defaults(uid)
        if response.status_code >= 400:
            raise RuntimeError("Could not load your cloud data from Appwrite.")
        row = response.json()
        raw = row.get("payload") or (row.get("data") or {}).get("payload") or "{}"
        try:
            state = json.loads(raw)
        except (TypeError, ValueError):
            state = self._uid_defaults(uid)
        if not isinstance(state, dict):
            state = self._uid_defaults(uid)
        state = self._normalize_state(uid, state)
        self._set_cached_state(uid, state)
        return state

    def _save_state(self, uid: str, state: dict[str, Any]) -> None:
        payload = {"data": {"payload": json.dumps(state, separators=(",", ":"))}}
        response = requests.put(self._row_url(uid), headers=self._headers(uid), json=payload, timeout=15)
        if response.status_code == 404:
            response = requests.post(
                self._row_url(uid).rsplit("/", 1)[0],
                headers=self._headers(uid),
                json={"rowId": uid, **payload},
                timeout=15,
            )
        if response.status_code >= 400:
            raise RuntimeError("Could not save your cloud data to Appwrite.")
        self._set_cached_state(uid, state)
