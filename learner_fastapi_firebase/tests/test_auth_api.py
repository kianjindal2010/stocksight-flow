from __future__ import annotations


def test_signup_success(client, monkeypatch):
    import learner_fastapi_firebase.app.api.routes_auth as auth_routes

    monkeypatch.setattr(
        auth_routes,
        "identity_signup",
        lambda *args, **kwargs: {
            "localId": "new-user",
            "idToken": "id-token",
            "refreshToken": "refresh-token",
            "expiresIn": "3600",
        },
    )
    monkeypatch.setattr(auth_routes, "send_verification_email", lambda *args, **kwargs: {})

    response = client.post(
        "/api/auth/signup",
        json={"email": "new@example.com", "password": "secret123", "display_name": "New User"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["uid"]
    assert payload["email"] == "new@example.com"


def test_login_success(client, monkeypatch):
    import learner_fastapi_firebase.app.api.routes_auth as auth_routes

    monkeypatch.setattr(
        auth_routes,
        "identity_signin",
        lambda *args, **kwargs: {
            "localId": "existing-user",
            "idToken": "id-token",
            "refreshToken": "refresh-token",
            "expiresIn": "3600",
        },
    )
    response = client.post("/api/auth/login", json={"email": "x@example.com", "password": "secret123"})
    assert response.status_code == 200
    assert response.json()["uid"]


def test_google_login_success(client, monkeypatch):
    import learner_fastapi_firebase.app.api.routes_auth as auth_routes

    monkeypatch.setattr(
        auth_routes,
        "verify_id_token",
        lambda token: {"uid": "google-user", "email": "g@example.com", "name": "Google User"},
    )
    response = client.post("/api/auth/google", json={"id_token": "google-token"})
    assert response.status_code == 200
    assert response.json()["uid"]


def test_session_authenticated(client, auth_headers):
    response = client.get("/api/auth/session", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["authenticated"] is True


def test_logout(client):
    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
