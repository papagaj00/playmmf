import { useEffect, useState } from "react";
import { api } from "../api";
import TradeSheet from "./TradeSheet";
import { formatPoints } from "../format";

const STATUS_LABELS = {
  open: "otevřený",
  closed: "uzavřený",
  resolved: "vyhodnocený",
};

export default function MarketCard({ market, username, balance, onChanged, isAdmin, adminKey }) {
  const [adminBusy, setAdminBusy] = useState(false);
  const [selectedOutcomeId, setSelectedOutcomeId] = useState(null);
  const [amount, setAmount] = useState(100);
  const [quote, setQuote] = useState(null);
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);

  const orderedOutcomes = [...market.outcomes].sort((left, right) => left.id - right.id);
  const leadingOutcomeIndex = orderedOutcomes.reduce(
    (leadingIndex, outcome, index) =>
      outcome.price > orderedOutcomes[leadingIndex].price ? index : leadingIndex,
    0
  );
  const selectedOutcome = market.outcomes.find((outcome) => outcome.id === selectedOutcomeId);
  const tradable = market.status === "open" && username;

  useEffect(() => {
    if (!tradable || !selectedOutcomeId) {
      setQuote(null);
      return;
    }
    let cancelled = false;
    api
      .quoteWager(market.id, selectedOutcomeId, amount)
      .then((nextQuote) => {
        if (!cancelled) setQuote(nextQuote);
      })
      .catch(() => {
        if (!cancelled) setQuote(null);
      });
    return () => {
      cancelled = true;
    };
  }, [amount, market.id, market.outcomes, market.status, selectedOutcomeId, tradable]);

  async function placeWager() {
    if (!selectedOutcome) {
      setMessage({ type: "error", text: "Nejprve vyber tip." });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.placeWager(
        market.id,
        selectedOutcome.id,
        amount
      );
      setMessage({
        type: "success",
        text: `Sázka ${formatPoints(amount)} bodů na „${selectedOutcome.name}“ přijata. Možná výhra: ${formatPoints(result.gross_payout)} bodů (kurz ${result.multiplier.toFixed(2)}).`,
      });
      setQuote(null);
      setSelectedOutcomeId(null);
      onChanged();
    } catch (err) {
      setMessage({ type: "error", text: err.message });
    } finally {
      setBusy(false);
    }
  }

  async function handleAdminAction(action) {
    setAdminBusy(true);
    try {
      if (action === "close") {
        await api.setMarketStatus(market.id, "closed", adminKey);
      } else if (action === "reopen") {
        await api.setMarketStatus(market.id, "open", adminKey);
      }
      onChanged();
    } catch (err) {
      alert(err.message);
    } finally {
      setAdminBusy(false);
    }
  }

  async function handleDelete() {
    if (!confirm("Trvale smazat tento zápas, všechny sázky a jeho historii? Tuto akci nelze vrátit.")) return;
    setAdminBusy(true);
    try {
      await api.deleteMarket(market.id, adminKey);
      onChanged();
    } catch (err) {
      alert(err.message);
    } finally {
      setAdminBusy(false);
    }
  }

  async function handleResolve(outcomeId) {
    if (!outcomeId) return;
    if (!confirm("Vyhodnotit zápas a vyplatit výherní sázky? Tuto akci nelze vrátit.")) return;
    setAdminBusy(true);
    try {
      await api.resolveMarket(market.id, Number(outcomeId), adminKey);
      onChanged();
    } catch (err) {
      alert(err.message);
    } finally {
      setAdminBusy(false);
    }
  }

  return (
    <div className={`market-card status-${market.status}`}>
      <div className="market-card__head">
        <div>
          <h3 className="market-card__title">{market.title}</h3>
          {market.description && <p className="market-card__desc">{market.description}</p>}
        </div>
        <span className={`status-badge ${market.status}`}>{STATUS_LABELS[market.status]}</span>
      </div>

      <div className="tug-bar">
        {orderedOutcomes.map((o, i) => (
          <div
            key={o.id}
            className="tug-bar__side"
            style={{
              width: `${o.price * 100}%`,
              background: i === leadingOutcomeIndex
                ? "var(--accent)"
                : "var(--surface-raised)",
              justifyContent: i === 0 ? "flex-start" : "flex-end",
              paddingLeft: i === 0 ? 10 : 0,
              paddingRight: i === 0 ? 0 : 10,
            }}
          >
            {o.price > 0.12 ? `${(o.price * 100).toFixed(0)}%` : ""}
          </div>
        ))}
      </div>

      <div className="outcome-bets">
        {orderedOutcomes.map((outcome) => (
          <button
            key={outcome.id}
            className={`outcome-bet ${selectedOutcomeId === outcome.id ? "selected" : ""} ${market.resolved_outcome_id === outcome.id ? "winner" : ""}`}
            disabled={!tradable}
            type="button"
            onClick={() => {
              setSelectedOutcomeId(outcome.id);
              setMessage(null);
            }}
          >
            <span className="outcome-bet__name">{outcome.name}</span>
            <span className="outcome-bet__odds">{(1 / outcome.price).toFixed(2)}</span>
          </button>
        ))}
      </div>

      {tradable && selectedOutcome && (
        <TradeSheet
          outcome={selectedOutcome}
          amount={amount}
          balance={balance}
          onAmountChange={(nextAmount) => {
            setAmount(nextAmount);
            setQuote(null);
          }}
          quote={quote}
          busy={busy}
          onClose={() => setSelectedOutcomeId(null)}
          onConfirm={placeWager}
        />
      )}
      {message && <div className={`trade-message ${message.type}`}>{message.text}</div>}

      {isAdmin && (
        <div className="market-card__footer">
          {market.status !== "resolved" && market.status === "open" && (
            <button className="btn-small" disabled={adminBusy} onClick={() => handleAdminAction("close")}>
              Uzavřít sázky
            </button>
          )}
          {market.status !== "resolved" && market.status === "closed" && (
            <button className="btn-small" disabled={adminBusy} onClick={() => handleAdminAction("reopen")}>
              Znovu otevřít sázky
            </button>
          )}
          {market.status !== "resolved" && <div className="resolve-row">
            <select
              disabled={adminBusy}
              defaultValue=""
              onChange={(e) => handleResolve(e.target.value)}
            >
              <option value="" disabled>
                Vyhodnotit jako…
              </option>
              {orderedOutcomes.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </div>}
          <button className="btn-small danger" disabled={adminBusy} onClick={handleDelete}>
            Smazat zápas
          </button>
        </div>
      )}
    </div>
  );
}
