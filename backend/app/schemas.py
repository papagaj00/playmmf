from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import MarketStatus, TransactionType


# ---------- Users ----------

class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=6, max_length=254)
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().casefold()

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip()


class LoginRequest(BaseModel):
    email: str = Field(min_length=6, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().casefold()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    balance: float
    is_admin: bool
    is_banned: bool


class AuthResponse(BaseModel):
    user: UserOut
    token: str


class LeaderboardEntry(BaseModel):
    username: str
    balance: float


class SystemStatus(BaseModel):
    maintenance: bool


# ---------- Markets / Outcomes ----------

class MarketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    b: float = Field(gt=0, description="Initial pool value per outcome")
    outcome_names: list[str] = Field(min_length=2)


class OutcomeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    quantity: float
    price: float  # computed, not a DB column


class MarketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str
    b: float
    status: MarketStatus
    resolved_outcome_id: int | None
    outcomes: list[OutcomeOut]


class MarketResolve(BaseModel):
    winning_outcome_id: int


class BalanceAdjustmentRequest(BaseModel):
    points: float = Field(description="Positive adds points, negative removes points")
    user_id: int | None = Field(default=None, gt=0)


class BanUserRequest(BaseModel):
    email: str = Field(min_length=6, max_length=254)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().casefold()


# ---------- Trading ----------

class QuoteRequest(BaseModel):
    outcome_id: int
    shares: float = Field(description="Positive to buy, negative to sell")


class QuoteResponse(BaseModel):
    outcome_id: int
    shares: float
    cost: float  # positive = you pay this, negative = you receive this
    price_before: float
    price_after: float


class WagerRequest(BaseModel):
    outcome_id: int
    amount: float = Field(gt=0, description="Point amount to stake")


class WagerQuoteResponse(BaseModel):
    outcome_id: int
    amount: float
    stake_amount: float
    price_before: float
    price_after: float
    gross_payout: float
    locked_payout: float
    multiplier: float


class TradeRequest(BaseModel):
    username: str
    outcome_id: int
    shares: float = Field(description="Positive to buy, negative to sell")


class TradeResponse(BaseModel):
    outcome_id: int
    shares_traded: float
    amount: float
    new_balance: float
    new_price: float


class WagerResponse(WagerQuoteResponse):
    new_balance: float


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: TransactionType
    outcome_id: int | None
    shares: float
    amount: float
    balance_after: float
    created_at: datetime
    market_title: str | None = None
    outcome_name: str | None = None
    resolved: bool = False
    won: bool | None = None
    winnings: float | None = None


class PositionOut(BaseModel):
    market_id: int
    market_title: str
    outcome_id: int
    outcome_name: str
    shares: float = 0.0  # legacy LMSR compatibility only
    stake_amount: float
    potential_payout: float
    locked_payout: float
    current_price: float
    market_status: MarketStatus
