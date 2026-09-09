import os

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app import auth, crud, models, schemas
from app.database import Base, ensure_auth_columns, engine, get_db

# Simple shared-secret admin auth. Change ADMIN_KEY via environment
# variable in production; this is fine for a school-tournament app run on
# a trusted local network / small group.
ADMIN_KEY = os.environ.get("ADMIN_KEY", "changeme")
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

Base.metadata.create_all(bind=engine)
ensure_auth_columns()

app = FastAPI(title="GBN Fantasy™")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Je vyžadován administrátorský klíč.")


def _market_to_out(market: models.Market) -> schemas.MarketOut:
    price_map = crud.market_prices(market)
    return schemas.MarketOut(
        id=market.id,
        title=market.title,
        description=market.description,
        b=market.b,
        status=market.status,
        resolved_outcome_id=market.resolved_outcome_id,
        outcomes=[
            schemas.OutcomeOut(
                id=o.id, name=o.name, quantity=o.quantity, price=price_map[o.id]
            )
            for o in market.outcomes
        ],
    )


def get_current_user(
    db: Session = Depends(get_db), gbn_session: str | None = Cookie(default=None)
) -> models.User:
    return auth.current_user(db, gbn_session)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        auth.SESSION_COOKIE,
        token,
        httponly=True,
        samesite="none",
        secure=True,
        max_age=auth.SESSION_DAYS * 24 * 60 * 60,
    )


# ---------- Users ----------

@app.post("/auth/register", response_model=schemas.AuthResponse)
def register(payload: schemas.RegisterRequest, response: Response, db: Session = Depends(get_db)):
    try:
        user, token = crud.register_user(db, payload.email, payload.username, payload.password)
    except crud.RegistrationError as error:
        raise HTTPException(status_code=400, detail=str(error))
    set_session_cookie(response, token)
    return {"user": user}


@app.post("/auth/login", response_model=schemas.AuthResponse)
def login(payload: schemas.LoginRequest, response: Response, db: Session = Depends(get_db)):
    try:
        user, token = crud.login_user(db, payload.email, payload.password)
    except crud.AuthenticationError as error:
        raise HTTPException(status_code=401, detail=str(error))
    set_session_cookie(response, token)
    return {"user": user}


@app.post("/auth/logout", status_code=204)
def logout(response: Response, db: Session = Depends(get_db), gbn_session: str | None = Cookie(default=None)):
    crud.revoke_session(db, gbn_session)
    response.delete_cookie(auth.SESSION_COOKIE, samesite="none", secure=True)


@app.get("/auth/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user


@app.get("/users/{username}", response_model=schemas.UserOut)
def get_user(username: str, user: models.User = Depends(get_current_user)):
    if username != user.username:
        raise HTTPException(status_code=403, detail="K tomuto účtu nemáš přístup.")
    return user


@app.get("/users/{username}/positions", response_model=list[schemas.PositionOut])
def get_user_positions(username: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if username != user.username:
        raise HTTPException(status_code=403, detail="K tomuto účtu nemáš přístup.")
    return crud.get_positions(db, user)


@app.get("/users/{username}/transactions", response_model=list[schemas.TransactionOut])
def get_user_transactions(username: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if username != user.username:
        raise HTTPException(status_code=403, detail="K tomuto účtu nemáš přístup.")
    return crud.get_transaction_history(db, user)


@app.get("/leaderboard", response_model=list[schemas.LeaderboardEntry])
def leaderboard(db: Session = Depends(get_db)):
    return crud.get_leaderboard(db)


@app.get("/admin/verify", dependencies=[Depends(require_admin)])
def verify_admin():
    return {"valid": True}


@app.post("/admin/factory-reset", dependencies=[Depends(require_admin)])
def factory_reset(db: Session = Depends(get_db)):
    crud.factory_reset(db)
    return {"status": "reset", "message": "Všichni uživatelé, zápasy a sázková data byla smazána."}


# ---------- Markets ----------

@app.post("/markets", response_model=schemas.MarketOut, dependencies=[Depends(require_admin)])
def create_market(payload: schemas.MarketCreate, db: Session = Depends(get_db)):
    market = crud.create_market(
        db, payload.title, payload.description, payload.b, payload.outcome_names
    )
    return _market_to_out(market)


@app.get("/markets", response_model=list[schemas.MarketOut])
def list_markets(db: Session = Depends(get_db)):
    return [_market_to_out(m) for m in crud.list_markets(db)]


@app.get("/markets/{market_id}", response_model=schemas.MarketOut)
def get_market(market_id: int, db: Session = Depends(get_db)):
    market = crud.get_market(db, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Zápas nebyl nalezen.")
    return _market_to_out(market)


@app.post(
    "/markets/{market_id}/status",
    response_model=schemas.MarketOut,
    dependencies=[Depends(require_admin)],
)
def set_market_status(market_id: int, status: models.MarketStatus, db: Session = Depends(get_db)):
    market = crud.get_market(db, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Zápas nebyl nalezen.")
    market = crud.set_market_status(db, market, status)
    return _market_to_out(market)


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
        market = crud.resolve_market(db, market, payload.winning_outcome_id)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except crud.MarketNotOpen as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _market_to_out(market)


# ---------- Trading ----------

@app.post("/markets/{market_id}/quote", response_model=schemas.QuoteResponse)
def quote_trade(market_id: int, payload: schemas.QuoteRequest, db: Session = Depends(get_db)):
    market = crud.get_market(db, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Zápas nebyl nalezen.")
    try:
        result = crud.quote_trade(db, market, payload.outcome_id, payload.shares)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except crud.InvalidTrade as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@app.post("/markets/{market_id}/wager/quote", response_model=schemas.WagerQuoteResponse)
def quote_wager(market_id: int, payload: schemas.WagerRequest, db: Session = Depends(get_db)):
    market = crud.get_market(db, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Zápas nebyl nalezen.")
    try:
        return crud.quote_wager(market, payload.outcome_id, payload.amount)
    except (KeyError, crud.InvalidTrade, crud.MarketNotOpen) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/markets/{market_id}/trade", response_model=schemas.TradeResponse)
def execute_trade(market_id: int, payload: schemas.TradeRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    market = crud.get_market(db, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Zápas nebyl nalezen.")
    try:
        result = crud.execute_trade(db, user, market, payload.outcome_id, payload.shares)
    except crud.MarketNotOpen as e:
        raise HTTPException(status_code=400, detail=str(e))
    except crud.InsufficientFunds as e:
        raise HTTPException(status_code=400, detail=str(e))
    except crud.InsufficientShares as e:
        raise HTTPException(status_code=400, detail=str(e))
    except crud.InvalidTrade as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@app.post("/markets/{market_id}/wager", response_model=schemas.WagerResponse)
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
    except (KeyError, crud.InvalidTrade) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok"}
