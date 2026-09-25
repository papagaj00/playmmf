"""
LMSR (Logarithmic Market Scoring Rule) engine.

This module is pure math with no database or web dependencies, so it can be
tested and reasoned about in isolation from everything else in the app.

Core idea
---------
A market has N outcomes (e.g. "Team A wins", "Team B wins"). At any moment,
`quantities[i]` is the number of outcome-`i` shares that have been sold so
far (can be any real number, including negative if net selling occurred).

The cost function:

    C(q) = b * ln( sum_i( exp(q_i / b) ) )

represents "how much money has flowed into the market so far, in total, to
reach this state". The price of outcome i (its current per-share cost, and
also the market's implied probability of that outcome) is the partial
derivative of C with respect to q_i:

    price_i(q) = exp(q_i / b) / sum_j( exp(q_j / b) )

Prices always sum to 1 and each lies in (0, 1). To actually buy `k` more
shares of outcome i, the cost is the *change* in C, not `k * price_i`,
because buying pushes the price up as you go (like a limit order book):

    cost_to_buy = C(q with q_i += k) - C(q)

Every winning share pays out exactly 1 unit at resolution; every losing
share pays out 0. `b` (the "liquidity parameter") controls how fast prices
move: small b -> prices swing wildly on small trades; large b -> prices
barely move but the market maker can lose more money subsidizing trades.

A useful sizing heuristic: the market maker's maximum possible loss is
`b * ln(N)` (N = number of outcomes), so choose b relative to how much of
your total point supply you're willing to have at risk per market.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


def _log_sum_exp(values: list[float]) -> float:
    """Numerically stable log(sum(exp(v) for v in values)).

    Naively computing exp(v) for large v overflows a Python float long
    before the final answer would be unreasonable. Factoring out the max
    value keeps every exponent <= 0, which is always safe.
    """
    if not values:
        raise ValueError("values must be non-empty")
    m = max(values)
    return m + math.log(sum(math.exp(v - m) for v in values))


def cost(quantities: list[float], b: float) -> float:
    """The LMSR cost function C(q) = b * ln(sum(exp(q_i / b))).

    This is "total money that has flowed into the market so far" — it has
    no meaning as a standalone number, only as something you take the
    difference of (see cost_to_trade) or differentiate (see price).
    """
    if b <= 0:
        raise ValueError("b (liquidity parameter) must be positive")
    scaled = [q / b for q in quantities]
    return b * _log_sum_exp(scaled)


def prices(quantities: list[float], b: float) -> list[float]:
    """Current price (= implied probability) of every outcome.

    Returns a list the same length as `quantities`, summing to 1.0.
    """
    if b <= 0:
        raise ValueError("b (liquidity parameter) must be positive")
    scaled = [q / b for q in quantities]
    m = max(scaled)
    exps = [math.exp(s - m) for s in scaled]
    total = sum(exps)
    return [e / total for e in exps]


def price(quantities: list[float], b: float, outcome_index: int) -> float:
    """Current price of a single outcome. Convenience wrapper over prices()."""
    return prices(quantities, b)[outcome_index]


def cost_to_trade(
    quantities: list[float], b: float, outcome_index: int, shares: float
) -> float:
    """Cost to change `quantities[outcome_index]` by `shares`.

    Positive `shares` = buying (returns a positive cost the trader pays).
    Negative `shares` = selling (returns a negative cost, i.e. a payment
    to the trader). This is `C(q') - C(q)`, not `shares * price`, because
    the price moves continuously as the trade is filled.
    """
    if outcome_index < 0 or outcome_index >= len(quantities):
        raise IndexError("outcome_index out of range")
    before = cost(quantities, b)
    after_q = list(quantities)
    after_q[outcome_index] += shares
    after = cost(after_q, b)
    return after - before


def shares_for_cost(
    quantities: list[float], b: float, outcome_index: int, amount: float
) -> float:
    """Return the shares whose LMSR cost is exactly ``amount``.

    ``amount`` must be positive. This inverse is used by the sportsbook-style
    wager API so users choose a stake while LMSR remains the settlement model.
    """
    if outcome_index < 0 or outcome_index >= len(quantities):
        raise IndexError("outcome_index out of range")
    if amount <= 0:
        raise ValueError("amount must be positive")

    probability = price(quantities, b, outcome_index)
    growth = math.expm1(amount / b)
    return b * math.log1p(growth / probability)


def max_loss(b: float, num_outcomes: int) -> float:
    """Worst-case subsidy the market maker can lose on a single market.

    Useful for picking `b`: e.g. if you have 1000 points in total
    circulation and want to risk at most 5% of that per market with 2
    outcomes, solve `b * ln(2) <= 50` for b.
    """
    return b * math.log(num_outcomes)


@dataclass
class Market:
    """Stateful convenience wrapper around the pure functions above.

    Keeps track of one market's outcome quantities so callers don't have
    to thread a list of floats through every call by hand. All the real
    logic still lives in the module-level functions.
    """

    outcome_names: list[str]
    b: float
    quantities: list[float] = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.b <= 0:
            raise ValueError("b (liquidity parameter) must be positive")
        if len(self.outcome_names) < 2:
            raise ValueError("a market needs at least 2 outcomes")
        if self.quantities is None:
            self.quantities = [0.0] * len(self.outcome_names)
        if len(self.quantities) != len(self.outcome_names):
            raise ValueError("quantities must match outcome_names length")

    @property
    def num_outcomes(self) -> int:
        return len(self.outcome_names)

    def prices(self) -> dict[str, float]:
        return dict(zip(self.outcome_names, prices(self.quantities, self.b)))

    def price_of(self, outcome_name: str) -> float:
        idx = self._index_of(outcome_name)
        return price(self.quantities, self.b, idx)

    def quote(self, outcome_name: str, shares: float) -> float:
        """Cost to buy (or sell, if shares < 0) `shares` of an outcome,
        WITHOUT actually executing the trade. Use this to show a user a
        price before they confirm.
        """
        idx = self._index_of(outcome_name)
        return cost_to_trade(self.quantities, self.b, idx, shares)

    def execute(self, outcome_name: str, shares: float) -> float:
        """Actually execute a trade, mutating this market's state, and
        return the amount the trader must pay (positive) or receive
        (negative, when selling).
        """
        idx = self._index_of(outcome_name)
        amount = cost_to_trade(self.quantities, self.b, idx, shares)
        self.quantities[idx] += shares
        return amount

    def max_loss(self) -> float:
        return max_loss(self.b, self.num_outcomes)

    def _index_of(self, outcome_name: str) -> int:
        try:
            return self.outcome_names.index(outcome_name)
        except ValueError:
            raise KeyError(f"unknown outcome: {outcome_name!r}") from None
