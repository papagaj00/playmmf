import os

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app import auth, crud, models, schemas
from app.database import Base, ensure_auth_columns, ensure_pool_columns, ensure_push_subscriptions, engine, get_db

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "prokop_jan@gymbn.cz").strip().casefold()
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

Base.metadata.create_all(bind=engine)
ensure_auth_columns()
ensure_pool_columns()
ensure_push_subscriptions()

app = FastAPI(title="playmmf")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_app_open(db: Session = Depends(get_db)) -> None:
    if crud.is_maintenance(db):
        raise HTTPException(status_code=503, detail="The app is on a maintenance break.")


def _market_to_out(market: models.Market) -> schemas.MarketOut:
    price_map = crud.market_prices(market)
    return schemas.MarketOut(
        id=market.id,
        title=market.title,
        description=market.description,
        b=market.b,
        stage=market.stage,
        scheduled_at=market.scheduled_at,
        status=market.status,
        resolved_outcome_id=market.resolved_outcome_id,
        resolved_as_draw=market.resolved_as_draw,
        result=market.result,
        outcomes=[
            schemas.OutcomeOut(
                id=o.id, team_id=o.team_id, name=o.name, quantity=o.quantity, price=price_map[o.id]
            )
            for o in market.outcomes
        ],
    )


def get_current_user(
    db: Session = Depends(get_db), authorization: str | None = Header(default=None),
    gbn_session: str | None = Cookie(default=None),
) -> models.User:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    return auth.current_user(db, token=token, gbn_session=gbn_session)


def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if not user.is_admin or user.email.casefold() != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Tento účet nemá administrátorská oprávnění.")
    return user


def get_optional_current_user(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    gbn_session: str | None = Cookie(default=None),
) -> models.User | None:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    if not token and not gbn_session:
        return None
    try:
        return auth.current_user(db, token=token, gbn_session=gbn_session)
    except HTTPException:
        return None


def require_app_open_or_admin(
    db: Session = Depends(get_db), user: models.User | None = Depends(get_optional_current_user)
) -> None:
    if crud.is_maintenance(db) and not user:
        raise HTTPException(status_code=503, detail="The app is on a maintenance break.")
    if crud.is_maintenance(db) and user and not user.is_admin:
        raise HTTPException(status_code=503, detail="The app is on a maintenance break.")


# ---------- Users ----------

@app.post("/auth/register", response_model=schemas.AuthResponse)
def register(payload: schemas.RegisterRequest, response: Response, db: Session = Depends(get_db)):
    try:
        user, token = crud.register_user(db, payload.email, payload.username, payload.password)
    except crud.RegistrationError as error:
        raise HTTPException(status_code=400, detail=str(error))
    response.set_cookie(auth.SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=auth.SESSION_DAYS * 86400)
    return {"user": user, "token": token}


@app.post("/auth/login", response_model=schemas.AuthResponse)
def login(payload: schemas.LoginRequest, response: Response, db: Session = Depends(get_db)):
    try:
        user, token = crud.login_user(db, payload.email, payload.password)
    except crud.AuthenticationError as error:
        raise HTTPException(status_code=401, detail=str(error))
    response.set_cookie(auth.SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=auth.SESSION_DAYS * 86400)
    return {"user": user, "token": token}


@app.post("/auth/logout", status_code=204)
def logout(response: Response, db: Session = Depends(get_db), authorization: str | None = Header(default=None), gbn_session: str | None = Cookie(default=None)):
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    crud.revoke_session(db, token or gbn_session)
    response.delete_cookie(auth.SESSION_COOKIE)


@app.get("/auth/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user


@app.get("/users/{username}", response_model=schemas.UserOut, dependencies=[Depends(require_app_open_or_admin)])
def get_user(username: str, user: models.User = Depends(get_current_user)):
    if username != user.username:
        raise HTTPException(status_code=403, detail="K tomuto účtu nemáš přístup.")
    return user


@app.get("/users/{username}/positions", response_model=list[schemas.PositionOut], dependencies=[Depends(require_app_open_or_admin)])
def get_user_positions(username: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if username != user.username:
        raise HTTPException(status_code=403, detail="K tomuto účtu nemáš přístup.")
    return crud.get_positions(db, user)


@app.get("/users/{username}/transactions", response_model=list[schemas.TransactionOut], dependencies=[Depends(require_app_open_or_admin)])
def get_user_transactions(username: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if username != user.username:
        raise HTTPException(status_code=403, detail="K tomuto účtu nemáš přístup.")
    return crud.get_transaction_history(db, user)


@app.get("/leaderboard", response_model=list[schemas.LeaderboardEntry], dependencies=[Depends(require_app_open_or_admin)])
def leaderboard(db: Session = Depends(get_db)):
    return crud.get_leaderboard(db)


@app.get("/admin/verify", dependencies=[Depends(require_admin)])
def verify_admin():
    return {"valid": True}


@app.get("/system/status", response_model=schemas.SystemStatus)
def system_status(db: Session = Depends(get_db)):
    return {"maintenance": crud.is_maintenance(db)}


@app.get("/info/messages", response_model=list[schemas.InfoMessageOut])
def info_messages(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return crud.list_info_messages(db)


@app.get("/push/public-key", response_model=schemas.PushPublicKey)
def push_public_key():
    return {"public_key": crud.push_public_key()}


@app.get("/push/status", response_model=schemas.PushStatus)
def push_status(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"enabled": crud.push_status(db, user)}


@app.post("/push/subscribe", response_model=schemas.PushStatus)
def push_subscribe(
    payload: schemas.PushSubscriptionCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    crud.save_push_subscription(db, user, payload.endpoint, payload.p256dh, payload.auth)
    return {"enabled": crud.push_status(db, user)}


@app.delete("/push/subscribe", response_model=schemas.PushStatus)
def push_unsubscribe(
    payload: schemas.PushSubscriptionCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    crud.remove_push_subscription(db, user, payload.endpoint)
    return {"enabled": crud.push_status(db, user)}


@app.post("/admin/info/messages", response_model=schemas.InfoMessageOut, dependencies=[Depends(require_admin)])
def create_info_message(payload: schemas.InfoMessageCreate, db: Session = Depends(get_db)):
    return crud.create_info_message(db, payload.text)


@app.post("/admin/maintenance", response_model=schemas.SystemStatus, dependencies=[Depends(require_admin)])
def set_maintenance(payload: schemas.SystemStatus, db: Session = Depends(get_db)):
    return {"maintenance": crud.set_maintenance(db, payload.maintenance)}


@app.get("/admin/users", response_model=list[schemas.UserOut], dependencies=[Depends(require_admin)])
def admin_users(db: Session = Depends(get_db)):
    return crud.list_users(db)


@app.get("/teams", response_model=list[schemas.TeamOut], dependencies=[Depends(require_admin)])
def teams(db: Session = Depends(get_db)):
    return crud.list_teams(db)


@app.get("/teams/rosters", response_model=list[schemas.TeamRosterOut], dependencies=[Depends(require_app_open_or_admin)])
def team_rosters(db: Session = Depends(get_db)):
    return crud.list_team_rosters(db)


@app.post("/admin/teams/{team_id}/players", response_model=schemas.TeamPlayerOut, dependencies=[Depends(require_admin)])
def add_team_player(team_id: int, payload: schemas.TeamPlayerCreate, db: Session = Depends(get_db)):
    try:
        return crud.add_team_player(db, team_id, payload.name, payload.goals)
    except crud.TeamNotFound as error:
        raise HTTPException(status_code=404, detail=str(error))
    except crud.DuplicateTeamPlayer as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.patch("/admin/teams/{team_id}/players/{player_id}", response_model=schemas.TeamPlayerOut, dependencies=[Depends(require_admin)])
def update_team_player(team_id: int, player_id: int, payload: schemas.TeamPlayerUpdate, db: Session = Depends(get_db)):
    try:
        return crud.update_team_player(db, team_id, player_id, payload.name, payload.goals)
    except crud.TeamPlayerNotFound as error:
        raise HTTPException(status_code=404, detail=str(error))
    except crud.DuplicateTeamPlayer as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.delete("/admin/teams/{team_id}/players/{player_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_team_player(team_id: int, player_id: int, db: Session = Depends(get_db)):
    try:
        crud.delete_team_player(db, team_id, player_id)
    except crud.TeamPlayerNotFound as error:
        raise HTTPException(status_code=404, detail=str(error))


@app.post("/admin/factory-reset", dependencies=[Depends(require_admin)])
def factory_reset(db: Session = Depends(get_db)):
    crud.factory_reset(db)
    return {"status": "reset", "message": "Všichni uživatelé, zápasy a sázková data byla smazána."}


@app.post("/admin/balance-adjustment", dependencies=[Depends(require_admin)])
def balance_adjustment(payload: schemas.BalanceAdjustmentRequest, db: Session = Depends(get_db)):
    try:
        count = crud.adjust_balances(db, payload.points, payload.user_id)
    except crud.InvalidBalanceAdjustment as error:
        raise HTTPException(status_code=400, detail=str(error))
    except crud.UserNotFound as error:
        raise HTTPException(status_code=404, detail=str(error))
    return {
        "updated_users": count,
        "points": payload.points,
        "scope": "all" if payload.user_id is None else "player",
    }


@app.post("/admin/users/ban", response_model=schemas.UserOut, dependencies=[Depends(require_admin)])
def ban_user(payload: schemas.BanUserRequest, db: Session = Depends(get_db)):
    try:
        return crud.set_user_banned(db, payload.email, True)
    except crud.UserNotFound as error:
        raise HTTPException(status_code=404, detail=str(error))


@app.post("/admin/users/unban", response_model=schemas.UserOut, dependencies=[Depends(require_admin)])
def unban_user(payload: schemas.BanUserRequest, db: Session = Depends(get_db)):
    try:
        return crud.set_user_banned(db, payload.email, False)
    except crud.UserNotFound as error:
        raise HTTPException(status_code=404, detail=str(error))


# ---------- Markets ----------

@app.post("/markets", response_model=schemas.MarketOut, dependencies=[Depends(require_admin)])
def create_market(payload: schemas.MarketCreate, db: Session = Depends(get_db)):
    try:
        market = crud.create_market(
            db,
            payload.title,
            payload.description,
            payload.b,
            payload.outcome_names,
            payload.scheduled_at,
            payload.team_ids,
            payload.stage,
            payload.initial_probabilities,
        )
    except (crud.InvalidTrade, KeyError) as error:
        raise HTTPException(status_code=400, detail=str(error))
    crud.notify_market_created(db, market)
    return _market_to_out(market)


@app.get("/markets", response_model=list[schemas.MarketOut], dependencies=[Depends(require_app_open_or_admin)])
def list_markets(db: Session = Depends(get_db)):
    return [_market_to_out(m) for m in crud.list_markets(db)]


@app.get("/markets/{market_id}", response_model=schemas.MarketOut, dependencies=[Depends(require_app_open_or_admin)])
def get_market(market_id: int, db: Session = Depends(get_db)):
    market = crud.get_market(db, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Zápas nebyl nalezen.")
    return _market_to_out(market)


@app.post(
    "/markets/{market_id}/status",
    response_model=schemas.MarketOut,
    dependencies=[Depends(require_admin), Depends(require_app_open_or_admin)],
)
def set_market_status(market_id: int, status: models.MarketStatus, db: Session = Depends(get_db)):
    market = crud.get_market(db, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Zápas nebyl nalezen.")
    market = crud.set_market_status(db, market, status)
    return _market_to_out(market)


@app.delete("/markets/{market_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_market(market_id: int, db: Session = Depends(get_db)):
    market = crud.get_market(db, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Zápas nebyl nalezen.")
    crud.delete_market(db, market)


@app.post(
    "/markets/{market_id}/resolve",
    response_model=schemas.MarketOut,
    dependencies=[Depends(require_admin)],
)
def resolve_market(market_id: int, payload: schemas.MarketResolve, db: Session = Depends(get_db)):
    market = crud.get_market(db, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Zápas nebyl nalezen.")
    try:
        market = crud.resolve_market_by_result(db, market, payload.result)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except crud.MarketNotOpen as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _market_to_out(market)


# ---------- Trading ----------

@app.post("/markets/{market_id}/quote", response_model=schemas.QuoteResponse, dependencies=[Depends(require_app_open)])
def quote_trade(market_id: int, payload: schemas.QuoteRequest, db: Session = Depends(get_db)):
    raise HTTPException(
        status_code=410,
        detail="Tento LMSR endpoint byl nahrazen poolovým sázením.",
    )


@app.post("/markets/{market_id}/wager/quote", response_model=schemas.WagerQuoteResponse, dependencies=[Depends(require_app_open)])
def quote_wager(
    market_id: int,
    payload: schemas.WagerRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    market = crud.get_market(db, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Zápas nebyl nalezen.")
    try:
        return crud.quote_wager(db, user, market, payload.outcome_id, payload.amount)
    except (KeyError, crud.InvalidTrade, crud.MarketNotOpen, crud.ExistingMarketPosition) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/markets/{market_id}/trade", response_model=schemas.TradeResponse, dependencies=[Depends(require_app_open)])
def execute_trade(market_id: int, payload: schemas.TradeRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    raise HTTPException(
        status_code=410,
        detail="Tento LMSR endpoint byl nahrazen poolovým sázením.",
    )


@app.post("/markets/{market_id}/wager", response_model=schemas.WagerResponse, dependencies=[Depends(require_app_open)])
def execute_wager(market_id: int, payload: schemas.WagerRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    market = crud.get_market(db, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Zápas nebyl nalezen.")
    try:
        return crud.execute_wager(db, user, market, payload.outcome_id, payload.amount)
    except crud.MarketNotOpen as e:
        raise HTTPException(status_code=400, detail=str(e))
    except crud.InsufficientFunds as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (KeyError, crud.InvalidTrade, crud.ExistingMarketPosition) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok"}
