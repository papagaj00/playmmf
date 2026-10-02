import { useEffect, useState } from "react";
import { api } from "../api";
import TradeSheet from "./TradeSheet";
import { formatPoints } from "../format";
import LoadingState from "./LoadingState";

const STATUS_LABELS = {
  open: "otevřený",
  closed: "uzavřený",
  resolved: "vyhodnocený",
};

function formatMatchDate(value) {
  if (!value) return null;
  return new Intl.DateTimeFormat("cs-CZ", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export default function MarketCard({ market, username, balance, positions, onChanged, isAdmin }) {
  const [adminBusy, setAdminBusy] = useState(false);
  const [selectedOutcomeId, setSelectedOutcomeId] = useState(null);
  const [amount, setAmount] = useState(100);
  const [quote, setQuote] = useState(null);
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [resolveOpen, setResolveOpen] = useState(false);
  const [matchResult, setMatchResult] = useState("");

  const orderedOutcomes = [...market.outcomes].sort((left, right) => left.id - right.id);
  const leadingOutcomeIndex = orderedOutcomes.reduce(
    (leadingIndex, outcome, index) =>
      outcome.price > orderedOutcomes[leadingIndex].price ? index : leadingIndex,
    0
  );
  const selectedOutcome = market.outcomes.find((outcome) => outcome.id === selectedOutcomeId);
  const tradable = market.status === "open" && username;
  const openPosition = positions.find((position) => position.market_id === market.id);

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
      setUpdating(true);
      try {
        await onChanged();
      } catch {
        setMessage({
          type: "success",
          text: "Sázka byla přijata. Kurzy se aktualizují při dalším načtení.",
        });
      }
    } catch (err) {
      setMessage({ type: "error", text: err.message });
    } finally {
      setUpdating(false);
      setBusy(false);
    }
  }

  async function handleAdminAction(action) {
    setAdminBusy(true);
    try {
      if (action === "close") {
        await api.setMarketStatus(market.id, "closed");
      } else if (action === "reopen") {
        await api.setMarketStatus(market.id, "open");
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
      await api.deleteMarket(market.id);
      onChanged();
    } catch (err) {
      alert(err.message);
    } finally {
      setAdminBusy(false);
    }
  }

  async function handleResolve() {
    const result = matchResult.trim();
    if (!/^\d+\s*:\s*\d+$/.test(result)) {
      setMessage({ type: "error", text: "Zadej výsledek ve formátu 5:2." });
      return;
    }
    if (!confirm("Vyhodnotit zápas podle tohoto výsledku? Tuto akci nelze vrátit.")) return;
    setAdminBusy(true);
    try {
      await api.resolveMarket(market.id, result);
      setResolveOpen(false);
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
          {market.scheduled_at && (
            <p className="market-card__schedule">{formatMatchDate(market.scheduled_at)}</p>
          )}
          {market.status === "resolved" && market.result && (
            <p className="market-card__result">Výsledek {market.result}</p>
          )}
          {market.description && <p className="market-card__desc">{market.description}</p>}
        </div>
        <span className={`status-badge ${market.status}`}>
          {market.resolved_as_draw ? "remíza" : STATUS_LABELS[market.status]}
        </span>
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
              if (openPosition && openPosition.outcome_id !== outcome.id) {
                setMessage({
                  type: "error",
                  text: `Na tento zápas už máš otevřenou sázku na „${openPosition.outcome_name}“. Další výsledek můžeš vsadit až po vyhodnocení zápasu.`,
                });
                return;
              }
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
      {updating && <LoadingState label="Aktualizuji kurzy a zůstatek…" />}
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
          {market.status !== "resolved" && (
            <button className="btn-small" disabled={adminBusy} onClick={() => setResolveOpen(true)}>
              Vyhodnotit zápas
            </button>
          )}
          <button className="btn-small danger" disabled={adminBusy} onClick={handleDelete}>
            Smazat zápas
          </button>
        </div>
      )}
      {resolveOpen && (
        <div className="resolve-dialog-layer" role="presentation">
          <button className="resolve-dialog-scrim" aria-label="Zavřít vyhodnocení" onClick={() => setResolveOpen(false)} />
          <section className="resolve-dialog" role="dialog" aria-modal="true" aria-labelledby={`resolve-title-${market.id}`}>
            <div className="resolve-dialog__head">
              <div>
                <p className="trade-sheet__eyebrow">Výsledek zápasu</p>
                <h3 id={`resolve-title-${market.id}`}>{market.title}</h3>
              </div>
              <button className="icon-button" type="button" onClick={() => setResolveOpen(false)} aria-label="Zavřít vyhodnocení">×</button>
            </div>
            <p className="resolve-dialog__hint">Pořadí: {orderedOutcomes.map((outcome) => outcome.name).join(" : ")}</p>
            <input
              className="resolve-dialog__input"
              inputMode="numeric"
              placeholder="5:2"
              value={matchResult}
              onChange={(event) => setMatchResult(event.target.value)}
              autoFocus
            />
            <button className="btn-primary resolve-dialog__submit" type="button" disabled={adminBusy} onClick={handleResolve}>
              {adminBusy ? "Vyhodnocování…" : "Potvrdit výsledek"}
            </button>
          </section>
        </div>
      )}
    </div>
  );
}
