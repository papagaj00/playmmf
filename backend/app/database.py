import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./tournament.db")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "prokop_jan@gymbn.cz").strip().casefold()
# Neon/Render's connection string may start with "postgres://" — SQLAlchemy 2.x needs "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _execute_migration(statement: str, parameters: dict | None = None) -> None:
    """Execute one startup migration statement in its own short transaction.

    Neon pooler connections can return multiple results for a single final
    COMMIT after a long batch of DDL statements. Keeping each idempotent schema
    change isolated makes retries safe and avoids that protocol failure.
    """
    with engine.connect() as connection:
        connection.execute(text(statement), parameters or {})
        connection.commit()


def ensure_auth_columns() -> None:
    """Add auth columns when starting against a pre-auth database.

    On a fresh database, create_all() already creates these columns from
    the model, so this becomes a no-op — it only does real work against an
    older SQLite file created before auth existed.
    """
    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    if "email" not in columns:
        _execute_migration("ALTER TABLE users ADD COLUMN email VARCHAR(254)")
    if "password_hash" not in columns:
        _execute_migration("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)")
    if "is_banned" not in columns:
        _execute_migration(
            "ALTER TABLE users ADD COLUMN is_banned BOOLEAN NOT NULL DEFAULT FALSE"
        )
    _execute_migration(
        "UPDATE users SET is_admin = TRUE WHERE lower(email) = :email",
        {"email": ADMIN_EMAIL},
    )
    _execute_migration("UPDATE users SET balance = ROUND(balance)")


def ensure_push_subscriptions() -> None:
    """Collapse legacy duplicate subscriptions before enforcing one per user."""
    if "push_subscriptions" not in inspect(engine).get_table_names():
        return
    _execute_migration(
        "DELETE FROM push_subscriptions "
        "WHERE id NOT IN (SELECT MAX(id) FROM push_subscriptions GROUP BY user_id)"
    )
    _execute_migration(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_push_subscription_user "
        "ON push_subscriptions (user_id)"
    )


def ensure_pool_columns() -> None:
    """Add pool-betting fields without deleting legacy LMSR data."""
    position_columns = {column["name"] for column in inspect(engine).get_columns("positions")}
    transaction_columns = {column["name"] for column in inspect(engine).get_columns("transactions")}
    market_columns = {column["name"] for column in inspect(engine).get_columns("markets")}
    outcome_columns = {column["name"] for column in inspect(engine).get_columns("outcomes")}
    if "team_id" not in outcome_columns:
        _execute_migration("ALTER TABLE outcomes ADD COLUMN team_id INTEGER")
    if "result" not in market_columns:
        _execute_migration("ALTER TABLE markets ADD COLUMN result VARCHAR(32)")
    if "stage" not in market_columns:
        _execute_migration("ALTER TABLE markets ADD COLUMN stage VARCHAR(32) NOT NULL DEFAULT 'group'")
    if "scheduled_at" not in market_columns:
        _execute_migration(
            "ALTER TABLE markets ADD COLUMN scheduled_at TIMESTAMP WITH TIME ZONE"
        )
    if "stake_amount" not in position_columns:
        _execute_migration("ALTER TABLE positions ADD COLUMN stake_amount FLOAT NOT NULL DEFAULT 0")
    if "locked_payout" not in position_columns:
        _execute_migration("ALTER TABLE positions ADD COLUMN locked_payout FLOAT NOT NULL DEFAULT 0")
    if "locked_payout" not in transaction_columns:
        _execute_migration("ALTER TABLE transactions ADD COLUMN locked_payout FLOAT")
    if "resolved_as_draw" not in market_columns:
        _execute_migration("ALTER TABLE markets ADD COLUMN resolved_as_draw BOOLEAN NOT NULL DEFAULT FALSE")
    _execute_migration(
        "UPDATE teams SET name = 'FC Bang Bros 1A' "
        "WHERE name = 'FC Bang Bros 1B' "
        "AND NOT EXISTS (SELECT 1 FROM teams WHERE name = 'FC Bang Bros 1A')"
    )
    _execute_migration(
        "UPDATE outcomes SET name = 'FC Bang Bros 1A' "
        "WHERE name = 'FC Bang Bros 1B'"
    )
    _execute_migration(
        "UPDATE markets SET title = replace(title, 'FC Bang Bros 1B', 'FC Bang Bros 1A') "
        "WHERE title LIKE '%FC Bang Bros 1B%'"
    )
    _execute_migration(
        "UPDATE outcomes SET team_id = (SELECT id FROM teams WHERE name = 'FC Bang Bros 1A') "
        "WHERE team_id = (SELECT id FROM teams WHERE name = 'FC Bang Bros 1B') "
        "AND EXISTS (SELECT 1 FROM teams WHERE name = 'FC Bang Bros 1A')"
    )
    _execute_migration(
        "DELETE FROM teams WHERE name = 'FC Bang Bros 1B' "
        "AND EXISTS (SELECT 1 FROM teams WHERE name = 'FC Bang Bros 1A')"
    )


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()