import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MarketStatus(str, enum.Enum):
    OPEN = "open"          # accepting trades
    CLOSED = "closed"      # trading halted (e.g. match kicked off), awaiting result
    RESOLVED = "resolved"  # outcome decided, payouts distributed


class TransactionType(str, enum.Enum):
    GRANT = "grant"    # initial / admin-granted points
    TRADE = "trade"    # a buy or sell
    PAYOUT = "payout"  # payout after market resolution


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), default="")


class InfoMessage(Base):
    __tablename__ = "info_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "endpoint", name="uq_user_push_endpoint"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    endpoint: Mapped[str] = mapped_column(String(2000))
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped["User"] = relationship(back_populates="push_subscriptions")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, unique=True)
    roster: Mapped[list["TeamPlayer"]] = relationship(
        back_populates="team", cascade="all, delete-orphan", order_by="TeamPlayer.sort_order"
    )


class TeamPlayer(Base):
    __tablename__ = "team_players"
    __table_args__ = (UniqueConstraint("team_id", "name", name="uq_team_player_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    goals: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    team: Mapped["Team"] = relationship(back_populates="roster")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True, nullable=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    balance: Mapped[float] = mapped_column(Float, default=10000.0)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    positions: Mapped[list["Position"]] = relationship(back_populates="user")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="user")
    sessions: Mapped[list["Session"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    push_subscriptions: Mapped[list["PushSubscription"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="sessions")


class Market(Base):
    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(1000), default="")
    b: Mapped[float] = mapped_column(Float)  # initial pool value L per outcome
    stage: Mapped[str] = mapped_column(String(32), default="group")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[MarketStatus] = mapped_column(
        Enum(MarketStatus), default=MarketStatus.OPEN
    )
    resolved_outcome_id: Mapped[int | None] = mapped_column(
        ForeignKey("outcomes.id"), nullable=True
    )
    resolved_as_draw: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    outcomes: Mapped[list["Outcome"]] = relationship(
        back_populates="market",
        foreign_keys="Outcome.market_id",
        cascade="all, delete-orphan",
    )


class Outcome(Base):
    __tablename__ = "outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[float] = mapped_column(Float, default=0.0)  # pool value q_i

    market: Mapped["Market"] = relationship(
        back_populates="outcomes", foreign_keys=[market_id]
    )
    positions: Mapped[list["Position"]] = relationship(back_populates="outcome")


class Position(Base):
    """One user's stake and locked payout for an outcome."""

    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("user_id", "outcome_id", name="uq_user_outcome"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    outcome_id: Mapped[int] = mapped_column(ForeignKey("outcomes.id"))
    shares: Mapped[float] = mapped_column(Float, default=0.0)  # legacy LMSR data
    stake_amount: Mapped[float] = mapped_column(Float, default=0.0)
    locked_payout: Mapped[float] = mapped_column(Float, default=0.0)

    user: Mapped["User"] = relationship(back_populates="positions")
    outcome: Mapped["Outcome"] = relationship(back_populates="positions")


class Transaction(Base):
    """Audit trail: every grant, trade, and payout."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    outcome_id: Mapped[int | None] = mapped_column(ForeignKey("outcomes.id"), nullable=True)
    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType))
    shares: Mapped[float] = mapped_column(Float, default=0.0)  # + buy / - sell
    amount: Mapped[float] = mapped_column(Float)  # points paid (+) or received (-)
    locked_payout: Mapped[float | None] = mapped_column(Float, nullable=True)
    balance_after: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped["User"] = relationship(back_populates="transactions")
