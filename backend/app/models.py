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
    b: Mapped[float] = mapped_column(Float)  # LMSR liquidity parameter
    status: Mapped[MarketStatus] = mapped_column(
        Enum(MarketStatus), default=MarketStatus.OPEN
    )
    resolved_outcome_id: Mapped[int | None] = mapped_column(
        ForeignKey("outcomes.id"), nullable=True
    )
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
    name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[float] = mapped_column(Float, default=0.0)  # LMSR q_i

    market: Mapped["Market"] = relationship(
        back_populates="outcomes", foreign_keys=[market_id]
    )
    positions: Mapped[list["Position"]] = relationship(back_populates="outcome")


class Position(Base):
    """How many shares of one outcome one user currently holds."""

    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("user_id", "outcome_id", name="uq_user_outcome"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    outcome_id: Mapped[int] = mapped_column(ForeignKey("outcomes.id"))
    shares: Mapped[float] = mapped_column(Float, default=0.0)

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
    balance_after: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped["User"] = relationship(back_populates="transactions")
