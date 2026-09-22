from __future__ import annotations

from learner_fastapi_firebase.app.desktop_session import DesktopSessionStore


def test_desktop_session_round_trip_and_clear(tmp_path):
    path = tmp_path / "StockSight Learner" / "session.dat"
    store = DesktopSessionStore(path=path, protector=lambda value: value[::-1], unprotector=lambda value: value[::-1])

    store.save("appwrite-session-token")

    assert path.exists()
    assert store.load() == "appwrite-session-token"

    store.clear()

    assert store.load() == ""


def test_desktop_session_handles_a_bad_saved_value(tmp_path):
    path = tmp_path / "session.dat"
    path.write_bytes(b"not-base64")
    store = DesktopSessionStore(path=path, protector=lambda value: value, unprotector=lambda value: value)

    assert store.load() == ""
