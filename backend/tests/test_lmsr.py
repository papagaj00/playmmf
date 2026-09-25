import math

import pytest

from app.lmsr import (
    MAX_PRICE,
    MIN_PRICE,
    Market,
    cost,
    cost_to_trade,
    max_loss,
    price,
    prices,
    prices_after_trade,
    prices_within_odds_cap,
    shares_for_cost,
)


def test_prices_start_at_uniform_when_no_trades():
    q = [0.0, 0.0]
    p = prices(q, b=10)
    assert p == pytest.approx([0.5, 0.5])


def test_prices_sum_to_one():
    q = [3.2, -1.5, 0.7]
    p = prices(q, b=5)
    assert sum(p) == pytest.approx(1.0)


def test_odds_cap_is_symmetric_and_trade_check_is_exact():
    after = prices_after_trade([0.0, 0.0], b=5000, outcome_index=0, shares=13115.40630199832)
    assert after[0] == pytest.approx(0.9323323584)
    assert prices_within_odds_cap(after)
    assert prices_within_odds_cap([MAX_PRICE, MIN_PRICE])
    assert not prices_within_odds_cap([MAX_PRICE + 0.001, MIN_PRICE - 0.001])


def test_buying_shares_raises_that_outcome_price():
    q = [0.0, 0.0]
    b = 10
    before = price(q, b, 0)
    paid = cost_to_trade(q, b, outcome_index=0, shares=5)
    q[0] += 5
    after = price(q, b, 0)
    assert after > before
    assert paid > 0  # buying costs money


def test_selling_shares_lowers_price_and_pays_out():
    q = [5.0, 0.0]
    b = 10
    before = price(q, b, 0)
    paid = cost_to_trade(q, b, outcome_index=0, shares=-5)
    q[0] -= 5
    after = price(q, b, 0)
    assert after < before
    assert paid < 0  # selling returns money to the trader


def test_cost_function_is_symmetric_at_origin():
    # With equal quantities, cost should just be b*ln(N)
    q = [2.0, 2.0]
    b = 4
    assert cost(q, b) == pytest.approx(b * math.log(2) + 2.0)


def test_no_overflow_with_large_quantities():
    # Naive exp(q/b) would overflow for q/b > ~709; make sure the
    # log-sum-exp trick keeps this stable.
    q = [100_000.0, 0.0]
    b = 1.0
    p = prices(q, b)
    assert p[0] == pytest.approx(1.0, abs=1e-9)
    assert p[1] == pytest.approx(0.0, abs=1e-9)
    # Should not raise OverflowError
    cost(q, b)


def test_max_loss_matches_formula():
    b = 50
    assert max_loss(b, num_outcomes=2) == pytest.approx(b * math.log(2))


def test_round_trip_buy_then_sell_costs_more_than_zero_but_less_than_double():
    # Buying then immediately selling the same number of shares back
    # should net out to (close to) zero cost, modulo any spread — LMSR
    # has no bid/ask spread, so it should be *exactly* zero net cost.
    q = [0.0, 0.0]
    b = 10
    buy_cost = cost_to_trade(q, b, 0, 5)
    q[0] += 5
    sell_proceeds = cost_to_trade(q, b, 0, -5)
    assert buy_cost + sell_proceeds == pytest.approx(0.0, abs=1e-9)


def test_shares_for_cost_is_exact_inverse_of_lmsr_cost():
    q = [0.0, 0.0]
    amount = 5.0
    shares = shares_for_cost(q, b=20, outcome_index=0, amount=amount)
    assert cost_to_trade(q, 20, 0, shares) == pytest.approx(amount)
    assert shares > 0


class TestMarketClass:
    def test_construction_defaults_to_zero_quantities(self):
        m = Market(outcome_names=["A wins", "B wins"], b=10)
        assert m.quantities == [0.0, 0.0]
        assert m.prices() == pytest.approx({"A wins": 0.5, "B wins": 0.5})

    def test_rejects_single_outcome(self):
        with pytest.raises(ValueError):
            Market(outcome_names=["only one"], b=10)

    def test_rejects_non_positive_b(self):
        with pytest.raises(ValueError):
            Market(outcome_names=["A", "B"], b=0)

    def test_execute_mutates_state_and_moves_price(self):
        m = Market(outcome_names=["A wins", "B wins"], b=10)
        paid = m.execute("A wins", 5)
        assert paid > 0
        assert m.quantities[0] == 5.0
        assert m.price_of("A wins") > 0.5

    def test_quote_does_not_mutate_state(self):
        m = Market(outcome_names=["A wins", "B wins"], b=10)
        m.quote("A wins", 5)
        assert m.quantities == [0.0, 0.0]

    def test_unknown_outcome_raises_keyerror(self):
        m = Market(outcome_names=["A wins", "B wins"], b=10)
        with pytest.raises(KeyError):
            m.price_of("C wins")

    def test_three_outcome_market(self):
        m = Market(outcome_names=["A", "B", "Draw"], b=15)
        assert sum(m.prices().values()) == pytest.approx(1.0)
        m.execute("Draw", 10)
        assert m.price_of("Draw") > 1 / 3
