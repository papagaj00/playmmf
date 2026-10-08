import hashlib
import math
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app import auth, lmsr, models

STARTING_BALANCE = 10000.0
MIN_TRADE_SHARES = 1.0
MIN_TRADE_AMOUNT = 0.01
MIN_WAGER_AMOUNT = 100.0
SCORE_GUESS_REWARD = 5000
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "prokop_jan@gymbn.cz").strip().casefold()
TEAM_NAMES = [
    "Gladiators 4B (A)", "Gladiators 4B (B)", "8A8", "FC Gooners 4A",
    "FC Bumass 7A8", "3A", "FC Alpacas 2A", "FC Tortas 2B", "6B8",
    "AC Bez Práce 6A8", "FC Bohové 1B", "FC Bang Bros 1A",
    "FC Fibula 5A8", "FC Six Seven 5B8",
]


class InsufficientFunds(Exception):
    pass


class MarketNotOpen(Exception):
    pass


class InsufficientShares(Exception):
    pass


class InvalidTrade(Exception):
    pass


class RegistrationError(Exception):
    pass


class AuthenticationError(Exception):
    pass


class UserNotFound(Exception):
    pass


class TeamNotFound(Exception):
    pass


class TeamPlayerNotFound(Exception):
    pass


class DuplicateTeamPlayer(Exception):
    pass


class InvalidBalanceAdjustment(Exception):
    pass


class ExistingMarketPosition(Exception):
    pass


class GuessClosed(Exception):
    pass


MAINTENANCE_KEY = "maintenance"


def is_maintenance(db: Session) -> bool:
    setting = db.get(models.AppSetting, MAINTENANCE_KEY)
    return setting is not None and setting.value == "true"


def set_maintenance(db: Session, enabled: bool) -> bool:
    setting = db.get(models.AppSetting, MAINTENANCE_KEY)
    if setting is None:
        setting = models.AppSetting(key=MAINTENANCE_KEY)
        db.add(setting)
    setting.value = "true" if enabled else "false"
    db.commit()
    return enabled


def list_info_messages(db: Session) -> list[models.InfoMessage]:
    return (
        db.query(models.InfoMessage)
        .order_by(models.InfoMessage.created_at.desc(), models.InfoMessage.id.desc())
        .all()
    )


def create_info_message(db: Session, text: str) -> models.InfoMessage:
    message = models.InfoMessage(text=text)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def push_public_key() -> str | None:
    return os.environ.get("PUSH_VAPID_PUBLIC_KEY") or None


def push_status(db: Session, user: models.User) -> bool:
    return push_public_key() is not None and any(subscription.active for subscription in user.push_subscriptions)


def save_push_subscription(
    db: Session, user: models.User, endpoint: str, p256dh: str, auth: str
) -> models.PushSubscription:
    subscription = (
        db.query(models.PushSubscription)
        .filter_by(user_id=user.id)
        .order_by(models.PushSubscription.id.desc())
        .first()
    )
    if subscription is None:
        subscription = models.PushSubscription(
            user_id=user.id, endpoint=endpoint, p256dh=p256dh, auth=auth
        )
        db.add(subscription)
    else:
        subscription.p256dh = p256dh
        subscription.auth = auth
        subscription.active = True
    db.commit()
    db.refresh(subscription)
    return subscription


def remove_push_subscription(db: Session, user: models.User, endpoint: str) -> None:
    db.query(models.PushSubscription).filter_by(user_id=user.id).update(
        {models.PushSubscription.active: False}, synchronize_session=False
    )
    db.commit()


def _notify_push_subscribers(db: Session, notification: dict[str, str | int]) -> int:
    private_key = os.environ.get("PUSH_VAPID_PRIVATE_KEY")
    subject = os.environ.get("PUSH_VAPID_SUBJECT")
    if not private_key or not subject:
        return 0
    try:
        import json
        from pywebpush import WebPushException, webpush
    except ImportError:
        return 0

    payload = json.dumps(notification)
    sent = 0
    subscriptions = db.query(models.PushSubscription).filter_by(active=True).all()
    for subscription in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=payload,
                vapid_private_key=private_key,
                vapid_claims={"sub": subject},
            )
            sent += 1
        except WebPushException as error:
            response = getattr(error, "response", None)
            if response is not None and response.status_code in (404, 410):
                subscription.active = False
        except Exception:
            # Notification delivery must never roll back or hide a saved event.
            continue
    db.commit()
    return sent


def notify_info_message(db: Session, message: models.InfoMessage) -> int:
    body = message.text
    if len(body) > 180:
        body = body[:177].rstrip() + "..."
    return _notify_push_subscribers(
        db,
        {"title": "Nová informace", "body": body, "info_message_id": message.id},
    )


def notify_market_created(db: Session, market: models.Market) -> int:
    outcome_names = [outcome.name for outcome in market.outcomes]
    matchup = " vs ".join(outcome_names) if outcome_names else market.title
    body = matchup
    if market.scheduled_at:
        body += f" · {market.scheduled_at.astimezone(ZoneInfo('Europe/Prague')).strftime('%d.%m. %H:%M')}"
    return _notify_push_subscribers(
        db, {"title": "Nový zápas", "body": body, "market_id": market.id}
    )


def _validate_trade(shares: float, amount: float) -> None:
    if abs(shares) < MIN_TRADE_SHARES:
        raise InvalidTrade(f"Sázka musí mít alespoň {MIN_TRADE_SHARES:g} jednotku.")
    if abs(amount) < MIN_TRADE_AMOUNT:
        raise InvalidTrade(
            f"Sázka musí mít hodnotu alespoň {MIN_TRADE_AMOUNT:.2f} bodu."
        )


# ---------- Users ----------

def get_user_by_username(db: Session, username: str) -> models.User | None:
    return db.query(models.User).filter(models.User.username == username).first()


def get_user_by_email(db: Session, email: str) -> models.User | None:
    return db.query(models.User).filter(models.User.email == email).first()


def register_user(db: Session, email: str, username: str, password: str) -> tuple[models.User, str]:
    if not email.endswith(("@gbn.cz", "@gymbn.cz")):
        raise RegistrationError("Použij školní e-mail s doménou @gbn.cz nebo @gymbn.cz.")
    if get_user_by_email(db, email):
        raise RegistrationError("Tento e-mail je již registrovaný.")
    if get_user_by_username(db, username):
        raise RegistrationError("Toto uživatelské jméno je již obsazené.")
    user = models.User(
        email=email,
        username=username,
        password_hash=auth.hash_password(password),
        balance=STARTING_BALANCE,
        is_admin=email == ADMIN_EMAIL,
    )
    db.add(user)
    db.flush()
    db.add(models.Transaction(
        user_id=user.id,
        outcome_id=None,
        type=models.TransactionType.GRANT,
        shares=0,
        amount=-STARTING_BALANCE,
        balance_after=user.balance,
    ))
    db.commit()
    db.refresh(user)
    return user, auth.new_session(db, user)


def login_user(db: Session, email: str, password: str) -> tuple[models.User, str]:
    user = get_user_by_email(db, email)
    if user is None or user.password_hash is None or not auth.verify_password(password, user.password_hash):
        raise AuthenticationError("E-mail nebo heslo není správné.")
    if user.is_banned:
        raise AuthenticationError("Tento účet byl zablokován.")
    return user, auth.new_session(db, user)


def revoke_session(db: Session, raw_token: str | None) -> None:
    if not raw_token:
        return
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    session = db.query(models.Session).filter(models.Session.token_hash == token_hash).first()
    if session:
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()


def create_user(db: Session, username: str) -> models.User:
    existing = get_user_by_username(db, username)
    if existing:
        return existing
    user = models.User(username=username, balance=STARTING_BALANCE)
    db.add(user)
    db.flush()
    db.add(
        models.Transaction(
            user_id=user.id,
            outcome_id=None,
            type=models.TransactionType.GRANT,
            shares=0,
            amount=-STARTING_BALANCE,  # negative "cost" = money given to the user
            balance_after=user.balance,
        )
    )
    db.commit()
    db.refresh(user)
    return user


def factory_reset(db: Session) -> None:
    """Delete every user, market, position, and transaction from the app."""
    db.query(models.Session).delete(synchronize_session=False)
    db.query(models.InfoMessage).delete(synchronize_session=False)
    db.query(models.Transaction).delete(synchronize_session=False)
    db.query(models.Position).delete(synchronize_session=False)
    db.query(models.ScoreGuess).delete(synchronize_session=False)
    # Market.resolved_outcome_id and Outcome.market_id form a circular
    # foreign-key relationship, so clear the pointer before deleting outcomes.
    db.query(models.Market).update(
        {models.Market.resolved_outcome_id: None}, synchronize_session=False
    )
    db.query(models.Outcome).delete(synchronize_session=False)
    db.query(models.Market).delete(synchronize_session=False)
    db.query(models.User).delete(synchronize_session=False)
    db.commit()


def list_users(db: Session) -> list[models.User]:
    return db.query(models.User).order_by(models.User.username.asc()).all()


def adjust_balances(db: Session, points: float, user_id: int | None = None) -> int:
    if points == 0:
        raise InvalidBalanceAdjustment("Zadej nenulovou změnu bodů.")
    if user_id is None:
        users = list_users(db)
    else:
        user = db.get(models.User, user_id)
        if user is None:
            raise UserNotFound("Vybraný hráč nebyl nalezen.")
        users = [user]
    if points < 0 and any(user.balance + points < 0 for user in users):
        raise InvalidBalanceAdjustment("Tato změna by snížila některý účet pod nulu.")
    for user in users:
        user.balance = round(user.balance + points)
        db.add(
            models.Transaction(
                user_id=user.id,
                outcome_id=None,
                type=models.TransactionType.GRANT,
                shares=0,
                amount=-points,
                balance_after=user.balance,
            )
        )
    db.commit()
    return len(users)


def adjust_all_balances(db: Session, points: float) -> int:
    return adjust_balances(db, points)


def set_user_banned(db: Session, email: str, banned: bool) -> models.User:
    user = get_user_by_email(db, email)
    if user is None:
        raise UserNotFound("Uživatel s tímto e-mailem nebyl nalezen.")
    user.is_banned = banned
    if banned:
        for session in user.sessions:
            session.revoked_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user


def get_leaderboard(db: Session) -> list[dict]:
    users = db.query(models.User).all()
    board = []
    for user in users:
        wagered_value = sum(
            position.stake_amount or 0.0
            for position in user.positions
            if position.outcome.market.status != models.MarketStatus.RESOLVED
        )
        board.append(
            {
                "username": user.username,
                "balance": user.balance,
                "wagered_value": wagered_value,
                "total_value": user.balance + wagered_value,
            }
        )
    board.sort(key=lambda row: row["total_value"], reverse=True)
    return board


def list_teams(db: Session) -> list[models.Team]:
    teams = db.query(models.Team).order_by(models.Team.sort_order.asc()).all()
    if not teams:
        db.add_all(
            models.Team(name=name, sort_order=index)
            for index, name in enumerate(TEAM_NAMES, start=1)
        )
        db.commit()
        teams = db.query(models.Team).order_by(models.Team.sort_order.asc()).all()
    return teams


def _team_goals_from_matches(db: Session) -> dict[int, int]:
    team_goals: dict[int, int] = {}
    markets = (
        db.query(models.Market)
        .filter(models.Market.status == models.MarketStatus.RESOLVED)
        .all()
    )
    for market in markets:
        if len(market.outcomes) != 2 or not re.fullmatch(r"\s*\d+\s*:\s*\d+\s*", market.result or ""):
            continue
        first, second = market.outcomes
        if first.team_id is None or second.team_id is None or first.team_id == second.team_id:
            continue
        first_goals, second_goals = (int(value.strip()) for value in market.result.split(":"))
        team_goals[first.team_id] = team_goals.get(first.team_id, 0) + second_goals
        team_goals[second.team_id] = team_goals.get(second.team_id, 0) + first_goals
    return team_goals


def list_team_rosters(db: Session) -> list[dict]:
    teams = list_teams(db)
    team_goals = _team_goals_from_matches(db)
    rosters = []
    for team in teams:
        roster_goals = sum(player.goals for player in team.roster)
        resolved_goals = team_goals.get(team.id, 0)
        has_resolved_matches = team.id in team_goals
        rosters.append(
            {
                "id": team.id,
                "name": team.name,
                "sort_order": team.sort_order,
                "players": team.roster,
                "team_goals": resolved_goals,
                "roster_goals": roster_goals,
                "goals_status": (
                    "pending" if not has_resolved_matches
                    else "consistent" if resolved_goals == roster_goals
                    else "mismatch"
                ),
            }
        )
    return rosters


def add_team_player(db: Session, team_id: int, name: str, goals: int) -> models.TeamPlayer:
    team = db.get(models.Team, team_id)
    if team is None:
        raise TeamNotFound("Tým nebyl nalezen.")
    if db.query(models.TeamPlayer).filter_by(team_id=team_id, name=name).first():
        raise DuplicateTeamPlayer("Tento hráč už je v týmu.")
    next_order = (max((player.sort_order for player in team.roster), default=-1) + 1)
    player = models.TeamPlayer(team_id=team_id, name=name, goals=goals, sort_order=next_order)
    db.add(player)
    db.commit()
    db.refresh(player)
    return player


def update_team_player(db: Session, team_id: int, player_id: int, name: str, goals: int) -> models.TeamPlayer:
    player = db.get(models.TeamPlayer, player_id)
    if player is None or player.team_id != team_id:
        raise TeamPlayerNotFound("Hráč nebyl nalezen v tomto týmu.")
    duplicate = db.query(models.TeamPlayer).filter(
        models.TeamPlayer.team_id == team_id,
        models.TeamPlayer.name == name,
        models.TeamPlayer.id != player_id,
    ).first()
    if duplicate:
        raise DuplicateTeamPlayer("Tento hráč už je v týmu.")
    player.name = name
    player.goals = goals
    db.commit()
    db.refresh(player)
    return player


def delete_team_player(db: Session, team_id: int, player_id: int) -> None:
    player = db.get(models.TeamPlayer, player_id)
    if player is None or player.team_id != team_id:
        raise TeamPlayerNotFound("Hráč nebyl nalezen v tomto týmu.")
    db.delete(player)
    db.commit()


# ---------- Markets ----------

def create_market(
    db: Session,
    title: str,
    description: str,
    b: float,
    outcome_names: list[str],
    scheduled_at: datetime | None = None,
    team_ids: list[int] | None = None,
    stage: str = "group",
    initial_probabilities: list[float] | None = None,
) -> models.Market:
    if team_ids:
        teams = [db.get(models.Team, team_id) for team_id in team_ids]
        if len(teams) != len(team_ids) or any(team is None for team in teams):
            raise KeyError("team not found")
        outcome_names = [team.name for team in teams]
        title = " vs ".join(outcome_names)
    else:
        teams = [None] * len(outcome_names)
        if not title.strip():
            raise InvalidTrade("Zadej název zápasu nebo vyber týmy.")
    if initial_probabilities is None:
        initial_probabilities = [100 / len(outcome_names)] * len(outcome_names)
    if len(initial_probabilities) != len(outcome_names):
        raise InvalidTrade("Zadej pravděpodobnost pro každý výsledek.")
    if any(not math.isfinite(probability) or probability <= 0 for probability in initial_probabilities):
        raise InvalidTrade("Pravděpodnosti musí být kladná čísla.")
    if not math.isclose(sum(initial_probabilities), 100, abs_tol=0.01):
        raise InvalidTrade("Pravděpodobnosti musí mít součet 100 %.")

    market = models.Market(
        title=title,
        description=description,
        b=b,
        stage=stage,
        scheduled_at=scheduled_at,
    )
    db.add(market)
    db.flush()
    for name, team, probability in zip(outcome_names, teams, initial_probabilities):
        db.add(
            models.Outcome(
                market_id=market.id,
                name=name,
                team_id=team.id if team else None,
                quantity=b * probability / 100,
            )
        )
    db.commit()
    db.refresh(market)
    return market


def close_due_markets(db: Session, now: datetime | None = None) -> int:
    """Close open markets one minute before their scheduled start time."""
    current_time = now or datetime.now(timezone.utc)
    cutoff = current_time + timedelta(minutes=1)
    due_markets = (
        db.query(models.Market)
        .filter(
            models.Market.status == models.MarketStatus.OPEN,
            models.Market.scheduled_at.is_not(None),
        )
        .all()
    )
    closed_count = 0
    for market in due_markets:
        scheduled_at = market.scheduled_at
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
        if scheduled_at <= cutoff:
            market.status = models.MarketStatus.CLOSED
            closed_count += 1
    if closed_count:
        db.commit()
    return closed_count


def get_market(db: Session, market_id: int) -> models.Market | None:
    close_due_markets(db)
    return db.get(models.Market, market_id)


def delete_market(db: Session, market: models.Market) -> None:
    outcome_ids = [outcome.id for outcome in market.outcomes]
    db.query(models.ScoreGuess).filter(models.ScoreGuess.market_id == market.id).delete(
        synchronize_session=False
    )
    if outcome_ids:
        db.query(models.Transaction).filter(models.Transaction.outcome_id.in_(outcome_ids)).delete(
            synchronize_session=False
        )
        db.query(models.Position).filter(models.Position.outcome_id.in_(outcome_ids)).delete(
            synchronize_session=False
        )
    # A resolved market points back to one of its outcomes. Clear that
    # circular foreign-key reference before removing the outcomes.
    market.resolved_outcome_id = None
    db.flush()
    if outcome_ids:
        db.query(models.Outcome).filter(models.Outcome.id.in_(outcome_ids)).delete(
            synchronize_session=False
        )
    db.query(models.Market).filter(models.Market.id == market.id).delete(
        synchronize_session=False
    )
    db.commit()


def list_markets(db: Session) -> list[models.Market]:
    close_due_markets(db)
    return db.query(models.Market).order_by(models.Market.created_at.desc()).all()


def market_prices(market: models.Market) -> dict[int, float]:
    if market.status == models.MarketStatus.RESOLVED:
        return historical_pool_prices(market)
    total_pool = sum(o.quantity for o in market.outcomes)
    if total_pool <= 0:
        return {o.id: 1 / len(market.outcomes) for o in market.outcomes}
    return {o.id: o.quantity / total_pool for o in market.outcomes}


def historical_pool_prices(market: models.Market) -> dict[int, float]:
    """Reconstruct resolved odds as if this match used point pools.

    This keeps old LMSR markets visually compatible with the current engine
    without changing their stored quantities, payouts, or transaction data.
    """
    stakes_by_outcome = {
        outcome.id: 0.0 for outcome in market.outcomes
    }
    for outcome in market.outcomes:
        for position in outcome.positions:
            for transaction in position.user.transactions:
                if (
                    transaction.type == models.TransactionType.TRADE
                    and transaction.outcome_id == outcome.id
                    and transaction.amount > 0
                ):
                    stakes_by_outcome[outcome.id] += transaction.amount
    pools = {
        outcome.id: market.b + stakes_by_outcome[outcome.id]
        for outcome in market.outcomes
    }
    total_pool = sum(pools.values())
    return {outcome_id: pool / total_pool for outcome_id, pool in pools.items()}


def set_market_status(db: Session, market: models.Market, status: models.MarketStatus) -> models.Market:
    market.status = status
    db.commit()
    db.refresh(market)
    return market


# ---------- Exact-score guesses ----------

def save_score_guess(
    db: Session, user: models.User, market: models.Market, first: int, second: int
) -> models.ScoreGuess:
    close_due_markets(db)
    db.refresh(market)
    if market.status != models.MarketStatus.OPEN or len(market.outcomes) != 2:
        raise GuessClosed("Tipování přesného výsledku je pro tento zápas uzavřeno.")
    guess = (
        db.query(models.ScoreGuess)
        .filter_by(user_id=user.id, market_id=market.id)
        .first()
    )
    if guess is None:
        guess = models.ScoreGuess(user_id=user.id, market_id=market.id, first=first, second=second)
        db.add(guess)
    else:
        guess.first = first
        guess.second = second
    db.commit()
    db.refresh(guess)
    return guess


def list_score_guesses(db: Session, user: models.User) -> list[models.ScoreGuess]:
    return db.query(models.ScoreGuess).filter_by(user_id=user.id).all()


def _settle_score_guesses(db: Session, market: models.Market, scores: list[int]) -> None:
    """Pay the flat reward to every user who guessed the exact result."""
    guesses = db.query(models.ScoreGuess).filter_by(market_id=market.id).all()
    reward_outcome_id = market.outcomes[0].id
    for guess in guesses:
        guess.won = [guess.first, guess.second] == scores
        if not guess.won:
            continue
        user = db.get(models.User, guess.user_id)
        user.balance = round(user.balance + SCORE_GUESS_REWARD)
        db.add(
            models.Transaction(
                user_id=user.id,
                outcome_id=reward_outcome_id,
                type=models.TransactionType.GRANT,
                shares=0,
                amount=-SCORE_GUESS_REWARD,
                balance_after=user.balance,
            )
        )


# ---------- Trading ----------

def quote_trade(db: Session, market: models.Market, outcome_id: int, shares: float) -> dict:
    outcome = next((o for o in market.outcomes if o.id == outcome_id), None)
    if outcome is None:
        raise KeyError("outcome not in this market")
    quantities = [o.quantity for o in market.outcomes]
    idx = [o.id for o in market.outcomes].index(outcome_id)
    price_before = lmsr.capped_price(lmsr.price(quantities, market.b, idx))
    cost = lmsr.cost_to_trade(quantities, market.b, idx, shares)
    _validate_trade(shares, cost)
    price_after = lmsr.capped_price(
        lmsr.prices_after_trade(quantities, market.b, idx, shares)[idx]
    )
    return {
        "outcome_id": outcome_id,
        "shares": shares,
        "cost": cost,
        "price_before": price_before,
        "price_after": price_after,
    }


def _open_position_for_market(
    db: Session, user: models.User, market: models.Market
) -> models.Position | None:
    return (
        db.query(models.Position)
        .join(models.Outcome)
        .filter(
            models.Position.user_id == user.id,
            models.Outcome.market_id == market.id,
            (models.Position.stake_amount > 0) | (models.Position.shares != 0),
        )
        .first()
    )


def quote_wager(
    db: Session, user: models.User, market: models.Market, outcome_id: int, amount: float
) -> dict:
    close_due_markets(db)
    db.refresh(market)
    if market.status != models.MarketStatus.OPEN:
        raise MarketNotOpen(f"Zápas {market.id} není otevřený pro sázení.")
    if not math.isfinite(amount) or amount < MIN_WAGER_AMOUNT:
        raise InvalidTrade(f"Sázka musí mít alespoň {MIN_WAGER_AMOUNT:.0f} bodů.")

    outcome = next((o for o in market.outcomes if o.id == outcome_id), None)
    if outcome is None:
        raise KeyError("outcome not in this market")

    existing = _open_position_for_market(db, user, market)
    if existing is not None and existing.outcome_id != outcome_id:
        raise ExistingMarketPosition(
            "Na tento zápas už máš otevřenou sázku na jiný výsledek."
        )
    total_pool = sum(o.quantity for o in market.outcomes)
    price_before = outcome.quantity / total_pool
    payout = amount / price_before
    next_total = total_pool + amount
    price_after = (outcome.quantity + amount) / next_total
    return {
        "outcome_id": outcome_id,
        "amount": amount,
        "stake_amount": amount,
        "price_before": price_before,
        "price_after": price_after,
        "locked_payout": payout,
        "gross_payout": payout,
        "multiplier": payout / amount,
    }


def execute_wager(
    db: Session, user: models.User, market: models.Market, outcome_id: int, amount: float
) -> dict:
    if amount > user.balance:
        raise InsufficientFunds(
            f"Sázka stojí {amount:.2f} bodu, ale na účtu máš pouze {user.balance:.2f} bodu."
        )
    quote = quote_wager(db, user, market, outcome_id, amount)
    outcome = next(o for o in market.outcomes if o.id == outcome_id)
    position = (
        db.query(models.Position)
        .filter(models.Position.user_id == user.id, models.Position.outcome_id == outcome_id)
        .first()
    )

    outcome.quantity += amount
    user.balance = round(user.balance - amount)
    if position is None:
        position = models.Position(user_id=user.id, outcome_id=outcome_id, shares=0.0)
        db.add(position)
    position.stake_amount = (position.stake_amount or 0.0) + amount
    position.locked_payout = (position.locked_payout or 0.0) + quote["locked_payout"]
    db.add(
        models.Transaction(
            user_id=user.id,
            outcome_id=outcome_id,
            type=models.TransactionType.TRADE,
            shares=0,
            amount=amount,
            locked_payout=quote["locked_payout"],
            balance_after=user.balance,
        )
    )
    db.commit()
    db.refresh(user)
    db.refresh(outcome)
    return {**quote, "new_balance": user.balance}


def execute_trade(
    db: Session, user: models.User, market: models.Market, outcome_id: int, shares: float
) -> dict:
    if market.status != models.MarketStatus.OPEN:
        raise MarketNotOpen(f"Zápas {market.id} není otevřený pro sázení.")

    outcome = next((o for o in market.outcomes if o.id == outcome_id), None)
    if outcome is None:
        raise KeyError("outcome not in this market")

    position = (
        db.query(models.Position)
        .filter(models.Position.user_id == user.id, models.Position.outcome_id == outcome_id)
        .first()
    )
    current_shares = position.shares if position else 0.0

    if shares < 0 and abs(shares) > current_shares:
        raise InsufficientShares(
            f"Nelze vsadit {abs(shares)} jednotek, aktuálně držíš pouze {current_shares}."
        )

    quantities = [o.quantity for o in market.outcomes]
    idx = [o.id for o in market.outcomes].index(outcome_id)
    amount = lmsr.cost_to_trade(quantities, market.b, idx, shares)
    _validate_trade(shares, amount)

    if amount > 0 and amount > user.balance:
        raise InsufficientFunds(
            f"Sázka stojí {amount:.2f} bodu, ale na účtu máš pouze {user.balance:.2f} bodu."
        )

    # Apply the trade
    outcome.quantity += shares
    user.balance = round(user.balance - amount)

    if position is None:
        position = models.Position(user_id=user.id, outcome_id=outcome_id, shares=0.0)
        db.add(position)
    position.shares += shares

    db.add(
        models.Transaction(
            user_id=user.id,
            outcome_id=outcome_id,
            type=models.TransactionType.TRADE,
            shares=shares,
            amount=amount,
            balance_after=user.balance,
        )
    )
    db.commit()
    db.refresh(user)
    db.refresh(outcome)

    new_quantities = [o.quantity for o in market.outcomes]
    new_price = lmsr.price(new_quantities, market.b, idx)

    return {
        "outcome_id": outcome_id,
        "shares_traded": shares,
        "amount": amount,
        "new_balance": user.balance,
        "new_price": new_price,
    }


def _legacy_position_stake(position: models.Position) -> float:
    return sum(
        transaction.amount
        for transaction in position.user.transactions
        if transaction.type == models.TransactionType.TRADE
        and transaction.outcome_id == position.outcome_id
        and transaction.amount > 0
    )


def resolve_market(
    db: Session,
    market: models.Market,
    winning_outcome_id: int | None,
    draw: bool = False,
    result: str | None = None,
) -> models.Market:
    if market.status == models.MarketStatus.RESOLVED:
        raise MarketNotOpen("Tento zápas už byl vyhodnocen.")
    winning = next((o for o in market.outcomes if o.id == winning_outcome_id), None) if not draw else None
    if not draw and winning is None:
        raise KeyError("winning outcome not in this market")

    positions = (
        db.query(models.Position)
        .join(models.Outcome)
        .filter(
            models.Outcome.market_id == market.id,
            (models.Position.stake_amount > 0) | (models.Position.shares != 0),
        )
        .all()
    )
    for pos in positions:
        if draw:
            payout = pos.stake_amount if (pos.stake_amount or 0) > 0 else _legacy_position_stake(pos)
        else:
            payout = (
                pos.locked_payout if (pos.stake_amount or 0) > 0 else pos.shares
            ) if pos.outcome_id == winning_outcome_id else 0.0
        if payout != 0:
            user = db.get(models.User, pos.user_id)
            user.balance = round(user.balance + payout)
            db.add(
                models.Transaction(
                    user_id=user.id,
                    outcome_id=pos.outcome_id,
                    type=models.TransactionType.PAYOUT,
                    shares=0,
                    amount=-payout,
                    locked_payout=payout,
                    balance_after=user.balance,
                )
            )

    market.status = models.MarketStatus.RESOLVED
    market.resolved_outcome_id = winning_outcome_id
    market.resolved_as_draw = draw
    market.result = result
    if result and re.fullmatch(r"\d+:\d+", result):
        _settle_score_guesses(db, market, [int(part) for part in result.split(":")])
    db.commit()
    db.refresh(market)
    return market


def resolve_market_by_result(db: Session, market: models.Market, result: str) -> models.Market:
    if len(market.outcomes) != 2:
        raise InvalidTrade("Skóre ve formátu A:B je podporováno pro zápasy se dvěma výsledky.")
    scores = [int(part.strip()) for part in result.split(":")]
    if any(score < 0 for score in scores):
        raise InvalidTrade("Skóre nemůže být záporné.")
    normalized_result = f"{scores[0]}:{scores[1]}"
    if scores[0] == scores[1]:
        return resolve_market(db, market, None, True, normalized_result)
    winner = market.outcomes[0].id if scores[0] > scores[1] else market.outcomes[1].id
    return resolve_market(db, market, winner, False, normalized_result)


def get_positions(db: Session, user: models.User) -> list[dict]:
    out = []
    for pos in user.positions:
        if (pos.stake_amount or 0) == 0 and pos.shares == 0:
            continue
        market = pos.outcome.market
        if market.status == models.MarketStatus.RESOLVED:
            continue
        total_pool = sum(o.quantity for o in market.outcomes)
        current_price = pos.outcome.quantity / total_pool
        out.append(
            {
                "market_id": market.id,
                "market_title": market.title,
                "outcome_id": pos.outcome_id,
                "outcome_name": pos.outcome.name,
                "shares": pos.shares,
                "stake_amount": pos.stake_amount or 0.0,
                "potential_payout": pos.locked_payout if (pos.stake_amount or 0) > 0 else pos.shares,
                "locked_payout": pos.locked_payout if (pos.stake_amount or 0) > 0 else pos.shares,
                "current_price": current_price,
                "market_status": market.status,
            }
        )
    return out


def get_transaction_history(db: Session, user: models.User) -> list[dict]:
    history = []
    for transaction in sorted(user.transactions, key=lambda item: item.created_at, reverse=True):
        market_title = None
        outcome_name = None
        resolved = False
        won = None
        winnings = None
        drawn = False
        if transaction.outcome_id is not None:
            outcome = db.get(models.Outcome, transaction.outcome_id)
            if outcome is not None:
                market = outcome.market
                market_title = market.title
                outcome_name = outcome.name
                resolved = market.status == models.MarketStatus.RESOLVED
                drawn = market.resolved_as_draw
                if transaction.type == models.TransactionType.TRADE and resolved:
                    if not drawn:
                        won = transaction.outcome_id == market.resolved_outcome_id
                        winnings = (
                            transaction.locked_payout
                            if transaction.locked_payout is not None
                            else transaction.shares
                        ) if won else 0.0
        history.append(
            {
                "id": transaction.id,
                "type": transaction.type,
                "outcome_id": transaction.outcome_id,
                "shares": transaction.shares,
                "amount": transaction.amount,
                "balance_after": transaction.balance_after,
                "created_at": transaction.created_at,
                "market_title": market_title,
                "outcome_name": outcome_name,
                "resolved": resolved,
                "won": won,
                "winnings": winnings,
                "draw": drawn,
            }
        )
    return history
