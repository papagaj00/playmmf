import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import auth, lmsr, models

STARTING_BALANCE = 100.0
MIN_TRADE_SHARES = 1.0
MIN_TRADE_AMOUNT = 0.01
MIN_WAGER_AMOUNT = 0.01
WAGER_UNIT = 1.0


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
    db.query(models.Transaction).delete(synchronize_session=False)
    db.query(models.Position).delete(synchronize_session=False)
    db.query(models.Outcome).delete(synchronize_session=False)
    db.query(models.Market).delete(synchronize_session=False)
    db.query(models.User).delete(synchronize_session=False)
    db.commit()


def get_leaderboard(db: Session) -> list[dict]:
    users = db.query(models.User).all()
    board = []
    for user in users:
        portfolio_value = 0.0
        for pos in user.positions:
            if pos.shares == 0:
                continue
            market = pos.outcome.market
            if market.status == models.MarketStatus.RESOLVED:
                continue
            portfolio_value += position_liquidation_value(pos)
        board.append(
            {
                "username": user.username,
                "balance": user.balance,
                "portfolio_value": portfolio_value,
                "total_value": user.balance + portfolio_value,
            }
        )
    board.sort(key=lambda row: row["total_value"], reverse=True)
    return board


# ---------- Markets ----------

def create_market(
    db: Session, title: str, description: str, b: float, outcome_names: list[str]
) -> models.Market:
    market = models.Market(title=title, description=description, b=b)
    db.add(market)
    db.flush()
    for name in outcome_names:
        db.add(models.Outcome(market_id=market.id, name=name, quantity=0.0))
    db.commit()
    db.refresh(market)
    return market


def get_market(db: Session, market_id: int) -> models.Market | None:
    return db.get(models.Market, market_id)


def list_markets(db: Session) -> list[models.Market]:
    return db.query(models.Market).order_by(models.Market.created_at.desc()).all()


def market_prices(market: models.Market) -> dict[int, float]:
    quantities = [o.quantity for o in market.outcomes]
    ps = lmsr.prices(quantities, market.b)
    return {o.id: p for o, p in zip(market.outcomes, ps)}


def position_liquidation_value(position: models.Position) -> float:
    """Return what selling this position would currently pay the holder."""
    market = position.outcome.market
    if market.status == models.MarketStatus.RESOLVED:
        return 0.0
    quantities = [o.quantity for o in market.outcomes]
    idx = [o.id for o in market.outcomes].index(position.outcome_id)
    return -lmsr.cost_to_trade(quantities, market.b, idx, -position.shares)


def set_market_status(db: Session, market: models.Market, status: models.MarketStatus) -> models.Market:
    market.status = status
    db.commit()
    db.refresh(market)
    return market


# ---------- Trading ----------

def quote_trade(db: Session, market: models.Market, outcome_id: int, shares: float) -> dict:
    outcome = next((o for o in market.outcomes if o.id == outcome_id), None)
    if outcome is None:
        raise KeyError("outcome not in this market")
    quantities = [o.quantity for o in market.outcomes]
    idx = [o.id for o in market.outcomes].index(outcome_id)
    price_before = lmsr.price(quantities, market.b, idx)
    cost = lmsr.cost_to_trade(quantities, market.b, idx, shares)
    _validate_trade(shares, cost)
    quantities[idx] += shares
    price_after = lmsr.price(quantities, market.b, idx)
    return {
        "outcome_id": outcome_id,
        "shares": shares,
        "cost": cost,
        "price_before": price_before,
        "price_after": price_after,
    }


def quote_wager(market: models.Market, outcome_id: int, amount: float) -> dict:
    if market.status != models.MarketStatus.OPEN:
        raise MarketNotOpen(f"Zápas {market.id} není otevřený pro sázení.")
    if amount != WAGER_UNIT:
        raise InvalidTrade(f"Sázka musí být přesně {WAGER_UNIT:.2f} bodu.")

    outcome = next((o for o in market.outcomes if o.id == outcome_id), None)
    if outcome is None:
        raise KeyError("outcome not in this market")

    quantities = [o.quantity for o in market.outcomes]
    idx = [o.id for o in market.outcomes].index(outcome_id)
    price_before = lmsr.price(quantities, market.b, idx)
    shares = lmsr.shares_for_cost(quantities, market.b, idx, amount)
    quantities[idx] += shares
    price_after = lmsr.price(quantities, market.b, idx)
    return {
        "outcome_id": outcome_id,
        "amount": amount,
        "shares": shares,
        "price_before": price_before,
        "price_after": price_after,
        "gross_payout": shares,
        "multiplier": shares / amount,
    }


def execute_wager(
    db: Session, user: models.User, market: models.Market, outcome_id: int, amount: float
) -> dict:
    if amount > user.balance:
        raise InsufficientFunds(
            f"Sázka stojí {amount:.2f} bodu, ale na účtu máš pouze {user.balance:.2f} bodu."
        )
    quote = quote_wager(market, outcome_id, amount)
    shares = quote["shares"]
    outcome = next(o for o in market.outcomes if o.id == outcome_id)
    position = (
        db.query(models.Position)
        .filter(models.Position.user_id == user.id, models.Position.outcome_id == outcome_id)
        .first()
    )

    outcome.quantity += shares
    user.balance -= amount
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
    user.balance -= amount

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


def resolve_market(db: Session, market: models.Market, winning_outcome_id: int) -> models.Market:
    if market.status == models.MarketStatus.RESOLVED:
        raise MarketNotOpen("Tento zápas už byl vyhodnocen.")
    winning = next((o for o in market.outcomes if o.id == winning_outcome_id), None)
    if winning is None:
        raise KeyError("winning outcome not in this market")

    positions = (
        db.query(models.Position)
        .join(models.Outcome)
        .filter(models.Outcome.market_id == market.id, models.Position.shares != 0)
        .all()
    )
    for pos in positions:
        payout = pos.shares if pos.outcome_id == winning_outcome_id else 0.0
        if payout != 0:
            user = db.get(models.User, pos.user_id)
            user.balance += payout
            db.add(
                models.Transaction(
                    user_id=user.id,
                    outcome_id=pos.outcome_id,
                    type=models.TransactionType.PAYOUT,
                    shares=0,
                    amount=-payout,  # negative "cost" = money paid out
                    balance_after=user.balance,
                )
            )

    market.status = models.MarketStatus.RESOLVED
    market.resolved_outcome_id = winning_outcome_id
    db.commit()
    db.refresh(market)
    return market


def get_positions(db: Session, user: models.User) -> list[dict]:
    out = []
    for pos in user.positions:
        if pos.shares == 0:
            continue
        market = pos.outcome.market
        if market.status == models.MarketStatus.RESOLVED:
            continue
        quantities = [o.quantity for o in market.outcomes]
        idx = [o.id for o in market.outcomes].index(pos.outcome_id)
        current_price = lmsr.price(quantities, market.b, idx)
        out.append(
            {
                "market_id": market.id,
                "market_title": market.title,
                "outcome_id": pos.outcome_id,
                "outcome_name": pos.outcome.name,
                "shares": pos.shares,
                "potential_payout": pos.shares,
                "current_price": current_price,
                "liquidation_value": position_liquidation_value(pos),
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
        if transaction.outcome_id is not None:
            outcome = db.get(models.Outcome, transaction.outcome_id)
            if outcome is not None:
                market = outcome.market
                market_title = market.title
                outcome_name = outcome.name
                resolved = market.status == models.MarketStatus.RESOLVED
                if transaction.type == models.TransactionType.TRADE and resolved:
                    won = transaction.outcome_id == market.resolved_outcome_id
                    winnings = transaction.shares if won else 0.0
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
            }
        )
    return history
