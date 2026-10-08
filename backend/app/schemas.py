from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    wagered_value: float
    total_value: float


class SystemStatus(BaseModel):
    maintenance: bool


class InfoMessageCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Zpráva nesmí být prázdná.")
        return value


class InfoMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    text: str
    created_at: datetime


class PushSubscriptionCreate(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2000)
    p256dh: str = Field(min_length=1, max_length=255)
    auth: str = Field(min_length=1, max_length=255)


class PushStatus(BaseModel):
    enabled: bool


class PushPublicKey(BaseModel):
    public_key: str | None


# ---------- Markets / Outcomes ----------

class MarketCreate(BaseModel):
    title: str = Field(default="", max_length=200)
    description: str = ""
    b: float = Field(gt=0, description="Initial pool value per outcome")
    stage: str = Field(default="group", pattern=r"^(group|quarterfinal|semifinal|third_place|final)$")
    scheduled_at: datetime | None = None
    outcome_names: list[str] = Field(min_length=2)
    team_ids: list[int] | None = None


class OutcomeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    team_id: int | None
    name: str
    quantity: float
    price: float  # computed, not a DB column


class TeamOut(BaseModel):
    id: int
    name: str
    sort_order: int


class TeamPlayerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    goals: int = Field(default=0, ge=0)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Jméno hráče nesmí být prázdné.")
        return value


class TeamPlayerUpdate(TeamPlayerCreate):
    pass


class TeamPlayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    team_id: int
    name: str
    goals: int
    sort_order: int


class TeamRosterOut(BaseModel):
    id: int
    name: str
    sort_order: int
    players: list[TeamPlayerOut]
    team_goals: int
    roster_goals: int
    goals_status: str


class MarketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str
    b: float
    stage: str
    scheduled_at: datetime | None
    status: MarketStatus
    resolved_outcome_id: int | None
    resolved_as_draw: bool
    result: str | None
    outcomes: list[OutcomeOut]


class MarketResolve(BaseModel):
    result: str = Field(pattern=r"^\d+\s*:\s*\d+$")


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
    draw: bool = False


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
