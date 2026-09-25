import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./tournament.db")
# Neon/Render's connection string may start with "postgres://" — SQLAlchemy 2.x needs "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def ensure_auth_columns() -> None:
    """Add auth columns when starting against a pre-auth database.

    On a fresh database, create_all() already creates these columns from
    the model, so this becomes a no-op — it only does real work against an
    older SQLite file created before auth existed.
    """
    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    with engine.begin() as connection:
        if "email" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(254)"))
        if "password_hash" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
        if "is_banned" not in columns:
            connection.execute(text(
                "ALTER TABLE users ADD COLUMN is_banned BOOLEAN NOT NULL DEFAULT FALSE"
            ))


def ensure_pool_columns() -> None:
    """Add pool-betting fields without deleting legacy LMSR data."""
    position_columns = {column["name"] for column in inspect(engine).get_columns("positions")}
    transaction_columns = {column["name"] for column in inspect(engine).get_columns("transactions")}
    with engine.begin() as connection:
        if "stake_amount" not in position_columns:
            connection.execute(text("ALTER TABLE positions ADD COLUMN stake_amount FLOAT NOT NULL DEFAULT 0"))
        if "locked_payout" not in position_columns:
            connection.execute(text("ALTER TABLE positions ADD COLUMN locked_payout FLOAT NOT NULL DEFAULT 0"))
        if "locked_payout" not in transaction_columns:
            connection.execute(text("ALTER TABLE transactions ADD COLUMN locked_payout FLOAT"))
        # Preserve old open positions with their legacy share payout as a
        # fallback. New positions use the explicit pool-bet fields.
        connection.execute(text(
            "UPDATE positions SET stake_amount = COALESCE(stake_amount, 0), "
            "locked_payout = CASE WHEN COALESCE(locked_payout, 0) = 0 AND shares != 0 "
            "THEN shares ELSE COALESCE(locked_payout, 0) END"
        ))
        # Seed only untouched zero-state markets. Nonzero legacy quantities
        # are preserved so historical market records remain inspectable.
        connection.execute(text(
            "UPDATE outcomes SET quantity = ("
            "SELECT b FROM markets WHERE markets.id = outcomes.market_id"
            ") WHERE quantity = 0 AND NOT EXISTS ("
            "SELECT 1 FROM outcomes other WHERE other.market_id = outcomes.market_id "
            "AND other.quantity != 0"
            ")"
        ))


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()