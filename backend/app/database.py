import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./tournament.db")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "prokop_jan@gymbn.cz").strip().casefold()
TEAM_NAMES = [
    "Gladiators 4B (A)", "Gladiators 4B (B)", "8A8", "FC Gooners 4A",
    "FC Bumass 7A8", "3A", "FC Alpacas 2A", "FC Tortas 2B", "6B8",
    "AC Bez Práce 6A8", "FC Bohové 1B", "FC Bang Bros 1B",
    "FC Fibula 5A8", "FC Six Seven 5B8",
]
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
        connection.execute(
            text("UPDATE users SET is_admin = TRUE WHERE lower(email) = :email"),
            {"email": ADMIN_EMAIL},
        )


def ensure_pool_columns() -> None:
    """Add pool-betting fields without deleting legacy LMSR data."""
    position_columns = {column["name"] for column in inspect(engine).get_columns("positions")}
    transaction_columns = {column["name"] for column in inspect(engine).get_columns("transactions")}
    market_columns = {column["name"] for column in inspect(engine).get_columns("markets")}
    outcome_columns = {column["name"] for column in inspect(engine).get_columns("outcomes")}
    with engine.begin() as connection:
        if "team_id" not in outcome_columns:
            connection.execute(text("ALTER TABLE outcomes ADD COLUMN team_id INTEGER"))
        if "result" not in market_columns:
            connection.execute(text("ALTER TABLE markets ADD COLUMN result VARCHAR(32)"))
        if "scheduled_at" not in market_columns:
            connection.execute(text(
                "ALTER TABLE markets ADD COLUMN scheduled_at TIMESTAMP WITH TIME ZONE"
            ))
        if "stake_amount" not in position_columns:
            connection.execute(text("ALTER TABLE positions ADD COLUMN stake_amount FLOAT NOT NULL DEFAULT 0"))
        if "locked_payout" not in position_columns:
            connection.execute(text("ALTER TABLE positions ADD COLUMN locked_payout FLOAT NOT NULL DEFAULT 0"))
        if "locked_payout" not in transaction_columns:
            connection.execute(text("ALTER TABLE transactions ADD COLUMN locked_payout FLOAT"))
        market_columns = {column["name"] for column in inspect(engine).get_columns("markets")}
        if "resolved_as_draw" not in market_columns:
            connection.execute(text("ALTER TABLE markets ADD COLUMN resolved_as_draw BOOLEAN NOT NULL DEFAULT FALSE"))
        for order, name in enumerate(TEAM_NAMES, start=1):
            connection.execute(
                text("INSERT INTO teams (name, sort_order) VALUES (:name, :sort_order) "
                     "ON CONFLICT (name) DO NOTHING"),
                {"name": name, "sort_order": order},
            )
        # Existing outcome quantities and legacy positions are preserved. The
        # application handles zero/null migration fields with legacy fallbacks.


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()