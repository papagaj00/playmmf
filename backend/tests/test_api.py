import os

os.environ["ADMIN_KEY"] = "test-admin-key"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database, main

# Point the whole app at a fresh in-memory SQLite DB for the test session,
# so tests never touch tournament.db and never see leftover state.
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
database.Base.metadata.create_all(bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


main.app.dependency_overrides[database.get_db] = override_get_db
client = TestClient(main.app)
ADMIN_HEADERS = {"X-Admin-Key": "test-admin-key"}


def register(username: str, domain: str = "gbn.cz"):
    return client.post(
        "/auth/register",
        json={
            "email": f"{username}@{domain}",
            "username": username,
            "password": "spravneheslo",
        },
    )


def test_health():
    r = client.get("/health")
    assert r.status_code == 200


def test_create_user_grants_starting_balance():
    r = register("alice")
    assert r.status_code == 200
    assert r.json()["user"]["balance"] == 100.0


def test_create_user_is_idempotent():
    r1 = register("bob")
    r2 = register("bob")
    assert r1.status_code == 200
    assert r2.status_code == 400


def test_registration_domains_passwords_and_login():
    assert register("gym-user", "gymbn.cz").status_code == 200
    invalid_domain = client.post(
        "/auth/register",
        json={"email": "outside@example.com", "username": "outside", "password": "spravneheslo"},
    )
    assert invalid_domain.status_code == 400
    short_password = client.post(
        "/auth/register",
        json={"email": "short@gbn.cz", "username": "short", "password": "short"},
    )
    assert short_password.status_code == 422

    client.post("/auth/logout")
    wrong_password = client.post(
        "/auth/login", json={"email": "gym-user@gymbn.cz", "password": "spatneheslo"}
    )
    assert wrong_password.status_code == 401
    login = client.post(
        "/auth/login", json={"email": "gym-user@gymbn.cz", "password": "spravneheslo"}
    )
    assert login.status_code == 200
    assert login.json()["user"]["username"] == "gym-user"


def test_logout_revokes_session_and_personal_access_isolation():
    register("auth-user")
    assert client.get("/auth/me").status_code == 200
    assert client.get("/users/other-user").status_code == 403
    client.post("/auth/logout")
    assert client.get("/auth/me").status_code == 401


def test_market_creation_requires_admin_key():
    r = client.post(
        "/markets",
        json={
            "title": "Final: A vs B",
            "b": 20,
            "outcome_names": ["A wins", "B wins"],
        },
    )
    assert r.status_code == 403


def test_full_trading_flow():
    # Create a market
    r = client.post(
        "/markets",
        json={
            "title": "Semifinal: Lions vs Tigers",
            "description": "Winner advances to the final",
            "b": 20,
            "outcome_names": ["Lions win", "Tigers win"],
        },
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200
    market = r.json()
    assert market["status"] == "open"
    assert len(market["outcomes"]) == 2
    for outcome in market["outcomes"]:
        assert outcome["price"] == pytest.approx(0.5, abs=1e-9)

    market_id = market["id"]
    lions_outcome_id = market["outcomes"][0]["id"]

    # New trader
    register("carol")

    # Quote before trading
    r = client.post(
        f"/markets/{market_id}/quote",
        json={"outcome_id": lions_outcome_id, "shares": 10},
    )
    assert r.status_code == 200
    quote = r.json()
    assert quote["cost"] > 0
    assert quote["price_after"] > quote["price_before"]

    # Execute the trade
    r = client.post(
        f"/markets/{market_id}/trade",
        json={"username": "carol", "outcome_id": lions_outcome_id, "shares": 10},
    )
    assert r.status_code == 200
    trade = r.json()
    assert trade["new_balance"] == pytest.approx(100.0 - trade["amount"])

    # Position shows up
    r = client.get("/users/carol/positions")
    assert r.status_code == 200
    positions = r.json()
    assert len(positions) == 1
    assert positions[0]["shares"] == 10

    # Resolve the market in Lions' favor
    r = client.post(
        f"/markets/{market_id}/resolve",
        json={"winning_outcome_id": lions_outcome_id},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"

    # Carol should have received 10 points payout (10 winning shares x 1)
    r = client.get("/users/carol")
    balance_after_resolution = r.json()["balance"]
    assert balance_after_resolution == pytest.approx(
        100.0 - trade["amount"] + 10
    )

    # The payout is now cash; the resolved market is no longer an open position.
    assert client.get("/users/carol/positions").json() == []
    carol_row = next(
        row for row in client.get("/leaderboard").json()
        if row["username"] == "carol"
    )
    assert carol_row["portfolio_value"] == 0


def test_cannot_sell_more_shares_than_held():
    register("dave")
    r = client.post(
        "/markets",
        json={"title": "3rd place match", "b": 15, "outcome_names": ["X wins", "Y wins"]},
        headers=ADMIN_HEADERS,
    )
    market_id = r.json()["id"]
    outcome_id = r.json()["outcomes"][0]["id"]

    r = client.post(
        f"/markets/{market_id}/trade",
        json={"username": "dave", "outcome_id": outcome_id, "shares": -5},
    )
    assert r.status_code == 400


def test_rejects_zero_and_fractional_trades():
    register("fractional")
    r = client.post(
        "/markets",
        json={"title": "Minimum trade", "b": 15, "outcome_names": ["X", "Y"]},
        headers=ADMIN_HEADERS,
    )
    market_id = r.json()["id"]
    outcome_id = r.json()["outcomes"][0]["id"]

    for endpoint in ("quote", "trade"):
        r = client.post(
            f"/markets/{market_id}/{endpoint}",
            json={
                "outcome_id": outcome_id,
                "shares": 0 if endpoint == "quote" else 0.5,
                **({"username": "fractional"} if endpoint == "trade" else {}),
            },
        )
        assert r.status_code == 400


def test_one_point_wager_quote_and_execution():
    register("bettor")
    r = client.post(
        "/markets",
        json={"title": "Wager market", "b": 20, "outcome_names": ["X", "Y"]},
        headers=ADMIN_HEADERS,
    )
    market_id = r.json()["id"]
    outcome_id = r.json()["outcomes"][0]["id"]

    quote = client.post(
        f"/markets/{market_id}/wager/quote",
        json={"outcome_id": outcome_id, "amount": 1},
    )
    assert quote.status_code == 200
    quote_data = quote.json()
    assert quote_data["amount"] == 1
    assert quote_data["gross_payout"] == pytest.approx(quote_data["shares"])
    assert quote_data["multiplier"] == pytest.approx(quote_data["shares"])

    wager = client.post(
        f"/markets/{market_id}/wager",
        json={"username": "bettor", "outcome_id": outcome_id, "amount": 1},
    )
    assert wager.status_code == 200
    assert wager.json()["new_balance"] == pytest.approx(99)
    assert wager.json()["shares"] == pytest.approx(quote_data["shares"])

    rejected = client.post(
        f"/markets/{market_id}/wager/quote",
        json={"outcome_id": outcome_id, "amount": 5},
    )
    assert rejected.status_code == 400


def test_wager_rejects_insufficient_funds():
    register("poor-bettor")
    r = client.post(
        "/markets",
        json={"title": "Funds market", "b": 20, "outcome_names": ["X", "Y"]},
        headers=ADMIN_HEADERS,
    )
    response = client.post(
        f"/markets/{r.json()['id']}/wager",
        json={"username": "poor-bettor", "outcome_id": r.json()["outcomes"][0]["id"], "amount": 101},
    )
    assert response.status_code == 400


def test_buying_does_not_create_immediate_liquidation_profit():
    register("liquidation")
    r = client.post(
        "/markets",
        json={"title": "Liquidation value", "b": 20, "outcome_names": ["X", "Y"]},
        headers=ADMIN_HEADERS,
    )
    market_id = r.json()["id"]
    outcome_id = r.json()["outcomes"][0]["id"]

    trade = client.post(
        f"/markets/{market_id}/trade",
        json={"username": "liquidation", "outcome_id": outcome_id, "shares": 10},
    )
    assert trade.status_code == 200

    user = client.get("/users/liquidation").json()
    positions = client.get("/users/liquidation/positions").json()
    leaderboard = next(
        row for row in client.get("/leaderboard").json()
        if row["username"] == "liquidation"
    )
    assert user["balance"] + positions[0]["liquidation_value"] == pytest.approx(100.0)
    assert leaderboard["total_value"] == pytest.approx(100.0)


def test_cannot_trade_on_resolved_market():
    register("erin")
    r = client.post(
        "/markets",
        json={"title": "Consolation match", "b": 15, "outcome_names": ["X wins", "Y wins"]},
        headers=ADMIN_HEADERS,
    )
    market_id = r.json()["id"]
    outcome_id = r.json()["outcomes"][0]["id"]
    client.post(
        f"/markets/{market_id}/resolve",
        json={"winning_outcome_id": outcome_id},
        headers=ADMIN_HEADERS,
    )
    r = client.post(
        f"/markets/{market_id}/trade",
        json={"username": "erin", "outcome_id": outcome_id, "shares": 5},
    )
    assert r.status_code == 400


def test_admin_key_verification():
    assert client.get("/admin/verify").status_code == 403
    assert client.get("/admin/verify", headers={"X-Admin-Key": "wrong"}).status_code == 403
    response = client.get("/admin/verify", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    assert response.json() == {"valid": True}


def test_transaction_history_describes_resolved_wager():
    register("history-user")
    market = client.post(
        "/markets",
        json={"title": "History match", "b": 100, "outcome_names": ["Home", "Away"]},
        headers=ADMIN_HEADERS,
    ).json()
    outcome_id = market["outcomes"][0]["id"]
    market_id = market["id"]

    wager = client.post(
        f"/markets/{market_id}/wager",
        json={"username": "history-user", "outcome_id": outcome_id, "amount": 1},
    )
    assert wager.status_code == 200

    pending = client.get("/users/history-user/transactions").json()
    trade = next(item for item in pending if item["type"] == "trade")
    assert trade["market_title"] == "History match"
    assert trade["outcome_name"] == "Home"
    assert trade["resolved"] is False
    assert trade["won"] is None

    client.post(
        f"/markets/{market_id}/resolve",
        json={"winning_outcome_id": outcome_id},
        headers=ADMIN_HEADERS,
    )
    resolved = client.get("/users/history-user/transactions").json()
    trade = next(item for item in resolved if item["type"] == "trade")
    assert trade["resolved"] is True
    assert trade["won"] is True
    assert trade["winnings"] == pytest.approx(trade["shares"])


def test_leaderboard_reflects_balances_and_open_positions():
    r = client.get("/leaderboard")
    assert r.status_code == 200
    names = [row["username"] for row in r.json()]
    assert "alice" in names


def test_factory_reset_requires_admin_key_and_deletes_all_data():
    register("reset-user")
    client.post(
        "/markets",
        json={"title": "Reset me", "b": 20, "outcome_names": ["A", "B"]},
        headers=ADMIN_HEADERS,
    )

    assert client.post("/admin/factory-reset").status_code == 403
    response = client.post("/admin/factory-reset", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    assert client.get("/leaderboard").json() == []
    assert client.get("/markets").json() == []
    assert client.get("/users/reset-user").status_code == 401
