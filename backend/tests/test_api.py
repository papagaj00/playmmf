import json
import os
import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType

os.environ["ADMIN_EMAIL"] = "admin@gbn.cz"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, database, main, models

# Point the whole app at a fresh in-memory SQLite DB for the test session,
# so tests never touch tournament.db and never see leftover state.
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
database.Base.metadata.create_all(bind=test_engine)
TEAM_NAMES = [
    "Gladiators 4B (A)", "Gladiators 4B (B)", "8A8", "FC Gooners 4A",
    "FC Bumass 7A8", "3A", "FC Alpacas 2A", "FC Tortas 2B", "6B8",
    "AC Bez Práce 6A8", "FC Bohové 1B", "FC Bang Bros 1A",
    "FC Fibula 5A8", "FC Six Seven 5B8",
]
with TestSessionLocal() as seed_session:
    seed_session.add_all(
        models.Team(name=name, sort_order=index)
        for index, name in enumerate(TEAM_NAMES, start=1)
    )
    seed_session.commit()


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


main.app.dependency_overrides[database.get_db] = override_get_db
client = TestClient(main.app)
admin_registration = client.post(
    "/auth/register",
    json={
        "email": "admin@gbn.cz",
        "username": "test-admin",
        "password": "spravneheslo",
    },
)
ADMIN_HEADERS = {"Authorization": f"Bearer {admin_registration.json()['token']}"}


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


def test_resolve_market_by_result_uses_outcome_id_order(monkeypatch):
    first = models.Outcome(id=1, name="Team A")
    second = models.Outcome(id=2, name="Team B")
    market = models.Market(outcomes=[second, first])
    resolved = {}

    def capture_resolution(db, current_market, winning_outcome_id, draw, result):
        resolved.update(
            market=current_market,
            winning_outcome_id=winning_outcome_id,
            draw=draw,
            result=result,
        )
        return current_market

    monkeypatch.setattr(crud, "resolve_market", capture_resolution)
    crud.resolve_market_by_result(None, market, "3:1")

    assert resolved == {
        "market": market,
        "winning_outcome_id": 1,
        "draw": False,
        "result": "3:1",
    }


def test_create_user_grants_starting_balance():
    r = register("alice")
    assert r.status_code == 200
    assert r.json()["user"]["balance"] == 10000.0


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


def test_market_creation_requires_authenticated_admin():
    r = client.post(
        "/markets",
        json={
            "title": "Final: A vs B",
            "b": 20,
            "outcome_names": ["A wins", "B wins"],
        },
    )
    assert r.status_code == 401


def test_team_catalog_preserves_requested_order_and_names():
    response = client.get("/teams", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    assert [team["name"] for team in response.json()] == TEAM_NAMES


def test_team_roster_admin_crud_and_goal_consistency():
    teams = client.get("/teams", headers=ADMIN_HEADERS).json()
    team_a, team_b = teams[0], teams[1]

    created = client.post(
        f"/admin/teams/{team_a['id']}/players",
        json={"name": "Test střelec", "goals": 4},
        headers=ADMIN_HEADERS,
    )
    assert created.status_code == 200
    player = created.json()

    player_market = client.post(
        "/markets",
        json={
            "title": "Roster test match",
            "b": 5000,
            "team_ids": [team_a["id"], team_b["id"]],
            "outcome_names": [team_a["name"], team_b["name"]],
        },
        headers=ADMIN_HEADERS,
    ).json()
    resolved = client.post(
        f"/markets/{player_market['id']}/resolve",
        json={"result": "5:2"},
        headers=ADMIN_HEADERS,
    )
    assert resolved.status_code == 200

    roster = next(
        item for item in client.get("/teams/rosters", headers=ADMIN_HEADERS).json()
        if item["id"] == team_a["id"]
    )
    assert roster["team_goals"] == 2
    assert roster["roster_goals"] == 4
    assert roster["goals_status"] == "mismatch"

    updated = client.patch(
        f"/admin/teams/{team_a['id']}/players/{player['id']}",
        json={"name": "Test střelec", "goals": 2},
        headers=ADMIN_HEADERS,
    )
    assert updated.status_code == 200
    consistent = next(
        item for item in client.get("/teams/rosters", headers=ADMIN_HEADERS).json()
        if item["id"] == team_a["id"]
    )
    assert consistent["goals_status"] == "consistent"

    deleted = client.delete(
        f"/admin/teams/{team_a['id']}/players/{player['id']}",
        headers=ADMIN_HEADERS,
    )
    assert deleted.status_code == 204


def test_admin_can_use_read_and_management_routes_during_maintenance():
    enabled = client.post(
        "/admin/maintenance",
        json={"maintenance": True},
        headers=ADMIN_HEADERS,
    )
    assert enabled.status_code == 200

    assert client.get("/markets", headers=ADMIN_HEADERS).status_code == 200
    assert client.get("/teams/rosters", headers=ADMIN_HEADERS).status_code == 200
    assert client.post(
        "/markets",
        json={"title": "Maintenance admin match", "b": 10, "outcome_names": ["A", "B"]},
        headers=ADMIN_HEADERS,
    ).status_code == 200

    register("maintenance-player")
    assert client.get("/markets").status_code == 503

    disabled = client.post(
        "/admin/maintenance",
        json={"maintenance": False},
        headers=ADMIN_HEADERS,
    )
    assert disabled.status_code == 200
    client.post("/auth/logout")


def test_balance_adjustments_are_stored_as_whole_points():
    registration = register("whole-points")
    assert registration.status_code == 200
    user_id = registration.json()["user"]["id"]
    adjusted = client.post(
        "/admin/balance-adjustment",
        json={"points": 0.4, "user_id": user_id},
        headers=ADMIN_HEADERS,
    )
    assert adjusted.status_code == 200
    assert client.get("/users/whole-points").json()["balance"] == 10000
    client.post("/auth/logout")


def test_info_messages_are_visible_to_players_and_writable_only_by_admin():
    client.post("/auth/logout")
    unauthorized = client.post("/admin/info/messages", json={"text": "Admin update"})
    assert unauthorized.status_code == 401

    register("info-player")
    forbidden = client.post(
        "/admin/info/messages",
        json={"text": "Player update"},
    )
    assert forbidden.status_code == 403

    created = client.post(
        "/admin/info/messages",
        json={"text": "  Admin update  "},
        headers=ADMIN_HEADERS,
    )
    assert created.status_code == 200
    assert created.json()["text"] == "Admin update"
    assert "created_at" in created.json()

    messages = client.get("/info/messages", headers=ADMIN_HEADERS)
    assert messages.status_code == 200
    assert messages.json()[0]["text"] == "Admin update"
    client.post("/auth/logout")


def test_info_message_notifies_active_push_subscriptions(monkeypatch):
    monkeypatch.setenv("PUSH_VAPID_PRIVATE_KEY", "test-private-key")
    monkeypatch.setenv("PUSH_VAPID_SUBJECT", "mailto:test@example.com")
    attempted_endpoints = []
    delivered_payloads = []

    class FakeWebPushException(Exception):
        pass

    def fake_webpush(subscription_info, data, **_kwargs):
        endpoint = subscription_info["endpoint"]
        attempted_endpoints.append(endpoint)
        if endpoint.endswith("delivery-failure"):
            raise RuntimeError("push service unavailable")
        delivered_payloads.append(json.loads(data))

    push_module = ModuleType("pywebpush")
    push_module.WebPushException = FakeWebPushException
    push_module.webpush = fake_webpush
    monkeypatch.setitem(sys.modules, "pywebpush", push_module)

    def subscribe(username, endpoint):
        registration = register(username).json()
        headers = {"Authorization": f"Bearer {registration['token']}"}
        subscription = {
            "endpoint": f"https://push.example/{endpoint}",
            "p256dh": "public-key",
            "auth": "auth-secret",
        }
        response = client.post("/push/subscribe", json=subscription, headers=headers)
        assert response.status_code == 200
        return headers, subscription

    subscribe("info-push-active", "active")
    subscribe("info-push-failing", "delivery-failure")
    inactive_headers, inactive_subscription = subscribe("info-push-inactive", "inactive")
    disabled = client.request(
        "DELETE", "/push/subscribe", json=inactive_subscription, headers=inactive_headers
    )
    assert disabled.status_code == 200

    created = client.post(
        "/admin/info/messages",
        json={"text": "Změna rozpisu zápasů"},
        headers=ADMIN_HEADERS,
    )

    assert created.status_code == 200
    assert created.json()["text"] == "Změna rozpisu zápasů"
    assert set(attempted_endpoints) == {
        "https://push.example/active",
        "https://push.example/delivery-failure",
    }
    assert delivered_payloads == [{
        "title": "Nová informace",
        "body": "Změna rozpisu zápasů",
        "info_message_id": created.json()["id"],
    }]
    listed = client.get("/info/messages", headers=ADMIN_HEADERS)
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == created.json()["id"]
    with TestSessionLocal() as db:
        db.query(models.PushSubscription).filter(
            models.PushSubscription.endpoint.in_(
                [
                    "https://push.example/active",
                    "https://push.example/delivery-failure",
                    "https://push.example/inactive",
                ]
            )
        ).delete(synchronize_session=False)
        db.commit()


def test_push_subscription_is_owned_by_authenticated_user():
    register("push-player")
    subscription = {
        "endpoint": "https://push.example/subscription-1",
        "p256dh": "public-key",
        "auth": "auth-secret",
    }
    created = client.post("/push/subscribe", json=subscription)
    assert created.status_code == 200
    assert created.json()["enabled"] is False
    with TestSessionLocal() as db:
        first_id = db.query(models.PushSubscription).filter_by(endpoint=subscription["endpoint"]).one().id
        assert db.query(models.PushSubscription).count() == 1

    removed = client.request("DELETE", "/push/subscribe", json=subscription)
    assert removed.status_code == 200
    assert removed.json()["enabled"] is False
    with TestSessionLocal() as db:
        row = db.query(models.PushSubscription).filter_by(id=first_id).one()
        assert row.active is False
        assert db.query(models.PushSubscription).count() == 1

    reenabled = client.post("/push/subscribe", json=subscription)
    assert reenabled.status_code == 200
    with TestSessionLocal() as db:
        row = db.query(models.PushSubscription).filter_by(id=first_id).one()
        assert row.active is True
        assert db.query(models.PushSubscription).count() == 1
    client.post("/auth/logout")


def test_market_can_be_created_from_team_ids():
    teams = client.get("/teams", headers=ADMIN_HEADERS).json()
    response = client.post(
        "/markets",
        json={
            "title": "Team catalog match",
            "b": 5000,
            "team_ids": [teams[0]["id"], teams[1]["id"]],
            "outcome_names": [teams[0]["name"], teams[1]["name"]],
        },
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Gladiators 4B (A) vs Gladiators 4B (B)"
    assert [outcome["name"] for outcome in response.json()["outcomes"]] == TEAM_NAMES[:2]


def test_market_custom_opening_probabilities_seed_prices():
    response = client.post(
        "/markets",
        json={
            "title": "Opening odds market",
            "b": 5000,
            "outcome_names": ["A", "B"],
            "initial_probabilities": [70, 30],
        },
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 200
    prices = [outcome["price"] for outcome in response.json()["outcomes"]]
    assert prices == pytest.approx([0.7, 0.3])

    invalid = client.post(
        "/markets",
        json={
            "title": "Invalid odds market",
            "b": 5000,
            "outcome_names": ["A", "B"],
            "initial_probabilities": [70, 20],
        },
        headers=ADMIN_HEADERS,
    )
    assert invalid.status_code == 400


def test_market_schedule_is_persisted():
    scheduled_at = "2026-10-05T18:30:00+00:00"
    response = client.post(
        "/markets",
        json={
            "title": "Scheduled match",
            "b": 5000,
            "scheduled_at": scheduled_at,
            "outcome_names": ["A", "B"],
        },
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 200
    market_id = response.json()["id"]
    assert response.json()["scheduled_at"].startswith("2026-10-05T18:30:00")
    assert client.get(f"/markets/{market_id}").json()["scheduled_at"].startswith(
        "2026-10-05T18:30:00"
    )


def test_scheduled_market_closes_one_minute_before_start():
    scheduled_at = datetime.now(timezone.utc) + timedelta(seconds=30)
    response = client.post(
        "/markets",
        json={
            "title": "Auto close market",
            "b": 5000,
            "scheduled_at": scheduled_at.isoformat(),
            "outcome_names": ["A", "B"],
        },
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 200
    market_id = response.json()["id"]

    listed_market = next(
        market for market in client.get("/markets").json() if market["id"] == market_id
    )
    assert listed_market["status"] == "closed"

    register("auto-close-player")
    wager = client.post(
        f"/markets/{market_id}/wager",
        json={"outcome_id": listed_market["outcomes"][0]["id"], "amount": 100},
    )
    assert wager.status_code == 400
    assert "není otevřený" in wager.json()["detail"]


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

    # Quote and execute a pool wager
    r = client.post(
        f"/markets/{market_id}/wager/quote",
        json={"outcome_id": lions_outcome_id, "amount": 100},
    )
    assert r.status_code == 200
    quote = r.json()
    assert quote["locked_payout"] == pytest.approx(200)

    r = client.post(
        f"/markets/{market_id}/wager",
        json={"username": "carol", "outcome_id": lions_outcome_id, "amount": 100},
    )
    assert r.status_code == 200
    wager = r.json()
    assert wager["new_balance"] == pytest.approx(9900)

    # Position shows up
    r = client.get("/users/carol/positions")
    assert r.status_code == 200
    positions = r.json()
    assert len(positions) == 1
    assert positions[0]["stake_amount"] == 100
    assert positions[0]["locked_payout"] == pytest.approx(200)

    # Resolve the market in Lions' favor
    r = client.post(
        f"/markets/{market_id}/resolve",
        json={"result": "1:0"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"

    # Carol should have received the locked 200-point payout.
    r = client.get("/users/carol")
    balance_after_resolution = r.json()["balance"]
    assert balance_after_resolution == pytest.approx(
        10000.0 - 100 + 200
    )

    # The payout is now cash; the resolved market is no longer an open position.
    assert client.get("/users/carol/positions").json() == []
    carol_row = next(
        row for row in client.get("/leaderboard").json()
        if row["username"] == "carol"
    )
    assert set(carol_row) == {"username", "balance", "wagered_value", "total_value"}
    assert carol_row["wagered_value"] == 0
    assert carol_row["total_value"] == carol_row["balance"]


def test_legacy_trade_endpoint_is_disabled():
    register("dave")
    r = client.post(
        "/markets",
        json={"title": "3rd place match", "b": 15, "outcome_names": ["X wins", "Y wins"]},
        headers=ADMIN_HEADERS,
    )
    market_id = r.json()["id"]
    r = client.post(
        f"/markets/{r.json()['id']}/trade",
        json={"username": "dave", "outcome_id": 1, "shares": -5},
    )
    assert r.status_code == 410


def test_legacy_quote_endpoint_is_disabled():
    register("fractional")
    r = client.post(
        "/markets",
        json={"title": "Minimum trade", "b": 15, "outcome_names": ["X", "Y"]},
        headers=ADMIN_HEADERS,
    )
    r = client.post(
        f"/markets/{r.json()['id']}/quote",
        json={"outcome_id": 1, "shares": 0},
    )
    assert r.status_code == 410


def test_variable_wager_quote_and_execution():
    register("bettor")
    r = client.post(
        "/markets",
        json={"title": "Wager market", "b": 5000, "outcome_names": ["X", "Y"]},
        headers=ADMIN_HEADERS,
    )
    market_id = r.json()["id"]
    outcome_id = r.json()["outcomes"][0]["id"]

    quote = client.post(
        f"/markets/{market_id}/wager/quote",
        json={"outcome_id": outcome_id, "amount": 100},
    )
    assert quote.status_code == 200
    quote_data = quote.json()
    assert quote_data["amount"] == 100
    assert quote_data["gross_payout"] == pytest.approx(quote_data["locked_payout"])
    assert quote_data["multiplier"] == pytest.approx(quote_data["locked_payout"] / 100)

    wager = client.post(
        f"/markets/{market_id}/wager",
        json={"username": "bettor", "outcome_id": outcome_id, "amount": 100},
    )
    assert wager.status_code == 200
    assert wager.json()["new_balance"] == pytest.approx(9900)
    assert wager.json()["stake_amount"] == pytest.approx(100)

    rejected = client.post(
        f"/markets/{market_id}/wager/quote",
        json={"outcome_id": outcome_id, "amount": 50},
    )
    assert rejected.status_code == 400


def test_pool_wager_locks_payout_and_blocks_cross_outcome_hedging():
    register("pool-player")
    market = client.post(
        "/markets",
        json={"title": "Pool market", "b": 5000, "outcome_names": ["A", "B"]},
        headers=ADMIN_HEADERS,
    ).json()
    outcome_a, outcome_b = market["outcomes"]

    first = client.post(
        f"/markets/{market['id']}/wager",
        json={"username": "pool-player", "outcome_id": outcome_a["id"], "amount": 100},
    )
    assert first.status_code == 200
    assert first.json()["locked_payout"] == pytest.approx(200)

    other = register("pool-other")
    second = client.post(
        f"/markets/{market['id']}/wager",
        json={"username": "pool-other", "outcome_id": outcome_b["id"], "amount": 900},
    )
    assert second.status_code == 200

    client.post(
        "/auth/login",
        json={"email": "pool-player@gbn.cz", "password": "spravneheslo"},
    )
    blocked = client.post(
        f"/markets/{market['id']}/wager",
        json={"username": "pool-player", "outcome_id": outcome_b["id"], "amount": 100},
    )
    assert blocked.status_code == 400

    client.post(
        f"/markets/{market['id']}/resolve",
        json={"result": "1:0"},
        headers=ADMIN_HEADERS,
    )
    history = client.get("/users/pool-player/transactions").json()
    wager = next(item for item in history if item["type"] == "trade")
    assert wager["winnings"] == pytest.approx(200)


def test_resolved_market_prices_reconstruct_pool_odds_from_stakes():
    register("historical-pool-user")
    market = client.post(
        "/markets",
        json={"title": "Historical pool display", "b": 5000, "outcome_names": ["A", "B"]},
        headers=ADMIN_HEADERS,
    ).json()
    outcome_a, outcome_b = market["outcomes"]
    wager = client.post(
        f"/markets/{market['id']}/wager",
        json={"username": "historical-pool-user", "outcome_id": outcome_a["id"], "amount": 1000},
    )
    assert wager.status_code == 200
    assert client.post(
        f"/markets/{market['id']}/resolve",
        json={"result": "1:0"},
        headers=ADMIN_HEADERS,
    ).status_code == 200

    resolved = client.get(f"/markets/{market['id']}").json()
    prices = {outcome["id"]: outcome["price"] for outcome in resolved["outcomes"]}
    assert prices[outcome_a["id"]] == pytest.approx(6000 / 11000)
    assert prices[outcome_b["id"]] == pytest.approx(5000 / 11000)


def test_wager_uses_exact_lmsr_cost_inverse():
    register("exact-bettor")
    market = client.post(
        "/markets",
        json={"title": "Exact wager", "b": 5000, "outcome_names": ["A", "B"]},
        headers=ADMIN_HEADERS,
    ).json()
    quote = client.post(
        f"/markets/{market['id']}/wager/quote",
        json={"outcome_id": market["outcomes"][0]["id"], "amount": 10000},
    )
    assert quote.status_code == 200
    assert quote.json()["locked_payout"] == pytest.approx(20000)


def test_wager_accepts_trade_at_odds_cap():
    register("cap-bettor")
    market = client.post(
        "/markets",
        json={"title": "Odds cap", "b": 5000, "outcome_names": ["A", "B"]},
        headers=ADMIN_HEADERS,
    ).json()
    response = client.post(
        f"/markets/{market['id']}/wager/quote",
        json={"outcome_id": market["outcomes"][0]["id"], "amount": 10000},
    )
    assert response.status_code == 200
    response = client.post(
        f"/markets/{market['id']}/wager",
        json={
            "username": "cap-bettor",
            "outcome_id": market["outcomes"][0]["id"],
            "amount": 10000,
        },
    )
    assert response.status_code == 200
    response = client.post(
        f"/markets/{market['id']}/wager/quote",
        json={"outcome_id": market["outcomes"][0]["id"], "amount": 10000},
    )
    assert response.status_code == 200
    assert response.json()["multiplier"] <= 101.0


def test_saturated_wagers_have_bounded_market_impact():
    register("impact-favorite")
    register("impact-underdog")
    market = client.post(
        "/markets",
        json={"title": "Impact control", "b": 5000, "outcome_names": ["A", "B"]},
        headers=ADMIN_HEADERS,
    ).json()
    outcome_a, outcome_b = market["outcomes"]
    funded = client.post(
        "/admin/balance-adjustment",
        json={"points": 90000},
        headers=ADMIN_HEADERS,
    )
    assert funded.status_code == 200
    assert client.post(
        "/auth/login",
        json={"email": "impact-favorite@gbn.cz", "password": "spravneheslo"},
    ).status_code == 200

    favorite = client.post(
        f"/markets/{market['id']}/wager",
        json={"username": "impact-favorite", "outcome_id": outcome_a["id"], "amount": 100000},
    )
    assert favorite.status_code == 200

    before = client.get(f"/markets/{market['id']}").json()
    before_underdog_price = next(
        outcome["price"] for outcome in before["outcomes"] if outcome["id"] == outcome_b["id"]
    )
    assert client.post(
        "/auth/login",
        json={"email": "impact-underdog@gbn.cz", "password": "spravneheslo"},
    ).status_code == 200

    underdog = client.post(
        f"/markets/{market['id']}/wager",
        json={"username": "impact-underdog", "outcome_id": outcome_b["id"], "amount": 10000},
    )
    assert underdog.status_code == 200, underdog.text

    after = client.get(f"/markets/{market['id']}").json()
    after_underdog_price = next(
        outcome["price"] for outcome in after["outcomes"] if outcome["id"] == outcome_b["id"]
    )
    assert after_underdog_price > before_underdog_price
    assert after_underdog_price <= 0.5 + 1e-9


def test_wager_rejects_insufficient_funds():
    register("poor-bettor")
    r = client.post(
        "/markets",
        json={"title": "Funds market", "b": 20, "outcome_names": ["X", "Y"]},
        headers=ADMIN_HEADERS,
    )
    response = client.post(
        f"/markets/{r.json()['id']}/wager",
        json={"username": "poor-bettor", "outcome_id": r.json()["outcomes"][0]["id"], "amount": 10001},
    )
    assert response.status_code == 400


def test_pool_wager_updates_cash_without_liquidation_value():
    register("liquidation")
    r = client.post(
        "/markets",
        json={"title": "Liquidation value", "b": 20, "outcome_names": ["X", "Y"]},
        headers=ADMIN_HEADERS,
    )
    market_id = r.json()["id"]
    outcome_id = r.json()["outcomes"][0]["id"]

    wager = client.post(
        f"/markets/{market_id}/wager",
        json={"username": "liquidation", "outcome_id": outcome_id, "amount": 100},
    )
    assert wager.status_code == 200

    user = client.get("/users/liquidation").json()
    positions = client.get("/users/liquidation/positions").json()
    leaderboard = next(
        row for row in client.get("/leaderboard").json()
        if row["username"] == "liquidation"
    )
    assert user["balance"] == 9900
    assert "liquidation_value" not in positions[0]
    assert leaderboard["balance"] == pytest.approx(user["balance"])


def test_cannot_wager_on_resolved_market():
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
        json={"result": "1:0"},
        headers=ADMIN_HEADERS,
    )
    r = client.post(
        f"/markets/{market_id}/wager",
        json={"username": "erin", "outcome_id": outcome_id, "amount": 100},
    )
    assert r.status_code == 400


def test_admin_email_verification():
    assert client.get("/admin/verify").status_code == 403
    assert client.get("/admin/verify", headers={"Authorization": "Bearer wrong"}).status_code == 401
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
        json={"username": "history-user", "outcome_id": outcome_id, "amount": 100},
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
        json={"result": "1:0"},
        headers=ADMIN_HEADERS,
    )
    resolved = client.get("/users/history-user/transactions").json()
    trade = next(item for item in resolved if item["type"] == "trade")
    assert trade["resolved"] is True
    assert trade["won"] is True
    assert trade["winnings"] == pytest.approx(200)


def test_draw_refunds_pool_wagers_without_win_or_loss():
    register("draw-user")
    market = client.post(
        "/markets",
        json={"title": "Draw match", "b": 5000, "outcome_names": ["A", "B"]},
        headers=ADMIN_HEADERS,
    ).json()
    outcome_id = market["outcomes"][0]["id"]
    wager = client.post(
        f"/markets/{market['id']}/wager",
        json={"username": "draw-user", "outcome_id": outcome_id, "amount": 100},
    )
    assert wager.status_code == 200
    assert wager.json()["locked_payout"] == pytest.approx(200)

    resolved = client.post(
        f"/markets/{market['id']}/resolve",
        json={"result": "1:1"},
        headers=ADMIN_HEADERS,
    )
    assert resolved.status_code == 200
    assert resolved.json()["resolved_as_draw"] is True
    assert client.get("/users/draw-user").json()["balance"] == 10000

    history = client.get("/users/draw-user/transactions").json()
    trade = next(item for item in history if item["type"] == "trade")
    assert trade["draw"] is True
    assert trade["won"] is None
    assert trade["winnings"] is None


def test_leaderboard_reflects_balances_and_open_positions():
    r = client.get("/leaderboard")
    assert r.status_code == 200
    names = [row["username"] for row in r.json()]
    assert "alice" in names


def test_admin_balance_adjustment_ban_and_market_deletion():
    register("admin-controls")
    market = client.post(
        "/markets",
        json={"title": "Delete me", "b": 20, "outcome_names": ["A", "B"]},
        headers=ADMIN_HEADERS,
    ).json()

    adjustment = client.post(
        "/admin/balance-adjustment", json={"points": 5}, headers=ADMIN_HEADERS
    )
    assert adjustment.status_code == 200
    assert adjustment.json()["updated_users"] >= 1
    assert client.get("/users/admin-controls").json()["balance"] == 10005

    banned = client.post(
        "/admin/users/ban",
        json={"email": "admin-controls@gbn.cz"},
        headers=ADMIN_HEADERS,
    )
    assert banned.status_code == 200
    assert client.get("/auth/me").status_code == 401
    assert client.post(
        "/auth/login",
        json={"email": "admin-controls@gbn.cz", "password": "spravneheslo"},
    ).status_code == 401

    assert client.post(
        f"/markets/{market['id']}/resolve",
        json={"result": "1:0"},
        headers=ADMIN_HEADERS,
    ).status_code == 200
    assert client.delete(f"/markets/{market['id']}", headers=ADMIN_HEADERS).status_code == 204
    assert client.get(f"/markets/{market['id']}").status_code == 404


def test_admin_can_adjust_one_player_or_all_players():
    register("target-player")
    register("other-player")

    users = client.get("/admin/users", headers=ADMIN_HEADERS)
    assert users.status_code == 200
    target = next(user for user in users.json() if user["username"] == "target-player")

    targeted = client.post(
        "/admin/balance-adjustment",
        json={"points": 250, "user_id": target["id"]},
        headers=ADMIN_HEADERS,
    )
    assert targeted.status_code == 200
    balances = {
        row["username"]: row["balance"] for row in client.get("/leaderboard").json()
    }
    assert balances["target-player"] == 10250
    assert balances["other-player"] == 10000

    all_players = client.post(
        "/admin/balance-adjustment",
        json={"points": 100},
        headers=ADMIN_HEADERS,
    )
    assert all_players.status_code == 200
    assert all_players.json()["scope"] == "all"
    balances = {
        row["username"]: row["balance"] for row in client.get("/leaderboard").json()
    }
    assert balances["target-player"] == 10350
    assert balances["other-player"] == 10100


def test_maintenance_break_blocks_player_routes_but_admin_can_toggle_it():
    register("maintenance-user")
    enabled = client.post(
        "/admin/maintenance", json={"maintenance": True}, headers=ADMIN_HEADERS
    )
    assert enabled.status_code == 200
    assert enabled.json() == {"maintenance": True}
    assert client.get("/system/status").json() == {"maintenance": True}
    assert client.get("/markets").status_code == 503
    assert client.get("/leaderboard").status_code == 503
    assert client.get("/admin/verify", headers=ADMIN_HEADERS).status_code == 200

    disabled = client.post(
        "/admin/maintenance", json={"maintenance": False}, headers=ADMIN_HEADERS
    )
    assert disabled.status_code == 200
    assert client.get("/markets").status_code == 200


def test_score_guess_can_be_updated_and_only_exact_score_wins_reward():
    market_response = client.post(
        "/markets",
        json={"title": "Score guess match", "b": 20, "outcome_names": ["A", "B"]},
        headers=ADMIN_HEADERS,
    )
    assert market_response.status_code == 200
    market_id = market_response.json()["id"]

    exact_user = register("score-exact-player").json()
    miss_user = register("score-miss-player").json()
    exact_headers = {"Authorization": f"Bearer {exact_user['token']}"}
    miss_headers = {"Authorization": f"Bearer {miss_user['token']}"}

    first_guess = client.put(
        f"/markets/{market_id}/guess",
        json={"first": 0, "second": 0},
        headers=exact_headers,
    )
    assert first_guess.status_code == 200
    updated_guess = client.put(
        f"/markets/{market_id}/guess",
        json={"first": 5, "second": 4},
        headers=exact_headers,
    )
    assert updated_guess.status_code == 200
    assert updated_guess.json()["first"] == 5
    assert client.put(
        f"/markets/{market_id}/guess",
        json={"first": 5, "second": 3},
        headers=miss_headers,
    ).status_code == 200
    assert client.put(
        f"/markets/{market_id}/guess",
        json={"first": -1, "second": 4},
        headers=exact_headers,
    ).status_code == 422

    closed = client.post(
        f"/markets/{market_id}/status?status=closed", headers=ADMIN_HEADERS
    )
    assert closed.status_code == 200
    assert client.put(
        f"/markets/{market_id}/guess",
        json={"first": 5, "second": 4},
        headers=exact_headers,
    ).status_code == 400

    resolved = client.post(
        f"/markets/{market_id}/resolve",
        json={"result": "5:4"},
        headers=ADMIN_HEADERS,
    )
    assert resolved.status_code == 200
    exact_balance = client.get("/users/score-exact-player", headers=exact_headers).json()["balance"]
    miss_balance = client.get("/users/score-miss-player", headers=miss_headers).json()["balance"]
    assert exact_balance == 15000
    assert miss_balance == 10000

    exact_guess = client.get("/users/score-exact-player/guesses", headers=exact_headers).json()[0]
    miss_guess = client.get("/users/score-miss-player/guesses", headers=miss_headers).json()[0]
    assert exact_guess["won"] is True
    assert miss_guess["won"] is False

    duplicate_resolution = client.post(
        f"/markets/{market_id}/resolve",
        json={"result": "5:4"},
        headers=ADMIN_HEADERS,
    )
    assert duplicate_resolution.status_code == 400
    assert client.get("/users/score-exact-player", headers=exact_headers).json()["balance"] == 15000


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
    admin = client.post(
        "/auth/register",
        json={"email": "admin@gbn.cz", "username": "test-admin", "password": "spravneheslo"},
    )
    assert admin.status_code == 200
    ADMIN_HEADERS["Authorization"] = f"Bearer {admin.json()['token']}"


def test_factory_reset_deletes_resolved_markets():
    register("resolved-reset-user")
    market = client.post(
        "/markets",
        json={"title": "Resolved reset", "b": 20, "outcome_names": ["A", "B"]},
        headers=ADMIN_HEADERS,
    ).json()
    assert client.post(
        f"/markets/{market['id']}/resolve",
        json={"result": "1:0"},
        headers=ADMIN_HEADERS,
    ).status_code == 200

    response = client.post("/admin/factory-reset", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert client.get("/markets").json() == []
    assert client.get("/leaderboard").json() == []
