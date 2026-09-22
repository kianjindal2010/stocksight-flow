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


def test_login_page_contains_signin_and_signup_controls(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert 'data-initial-mode="login"' in response.text
    assert 'id="signinForm"' in response.text
    assert 'id="signupForm"' in response.text
    assert "/api/auth/login" in response.text
    assert "/api/auth/signup" in response.text
    assert "signInWithRedirect" in response.text
    assert "onAuthStateChanged" in response.text
    assert "signInWithPopup" not in response.text
    assert 'href="/register"' not in response.text


def test_external_google_auth_handoff(client):
    started = client.post("/api/auth/external/start")
    assert started.status_code == 200
    state = started.json()["state"]

    external_page = client.get(f"/auth/google/external?state={state}")
    assert external_page.status_code == 200
    assert "signInWithPopup" in external_page.text

    completed = client.post(
        "/api/auth/external/complete",
        json={"state": state, "id_token": "google-token"},
    )
    assert completed.status_code == 200
    assert client.get(f"/api/auth/external/status?state={state}").json()["status"] == "ready"

    consumed = client.post("/api/auth/external/consume", json={"state": state})
    assert consumed.status_code == 200
    assert consumed.json()["uid"]


def test_login_signup_mode_marks_create_account(client):
    response = client.get("/login?mode=signup")
    assert response.status_code == 200
    assert 'data-initial-mode="signup"' in response.text
    assert 'data-auth-panel="signup"' in response.text


def test_register_page_redirects_to_login_signup_mode(client):
    response = client.get("/register", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?mode=signup"


def test_protected_form_action_redirects_to_login(client):
    response = client.post("/watchlist/add", data={"symbol": "AAPL"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_session_authenticated(client, auth_headers):
    response = client.get("/api/auth/session", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["authenticated"] is True


def test_logout(client):
    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
