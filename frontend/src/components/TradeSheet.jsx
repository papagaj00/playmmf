import { X } from "lucide-react";
import { formatPoints } from "../format";

export default function TradeSheet({ outcome, amount, balance, onAmountChange, quote, busy, onClose, onConfirm }) {
    if (!outcome) return null;

    return (
        <div className="trade-sheet-layer" role="presentation">
            <button className="trade-sheet-scrim" aria-label="Zavřít tiket" onClick={onClose} />
            <section className="trade-sheet" role="dialog" aria-modal="true" aria-labelledby="trade-sheet-title">
                <div className="trade-sheet__handle" />
                <div className="trade-sheet__topline">
                    <div>
                        <p className="trade-sheet__eyebrow">Nová sázka</p>
                        <h3 id="trade-sheet-title">{outcome.name}</h3>
                    </div>
                    <button className="icon-button" onClick={onClose} aria-label="Zavřít tiket">
                        <X size={20} />
                    </button>
                </div>
                <div className="trade-sheet__odds">
                    <span>Aktuální kurz</span>
                    <strong>{(1 / outcome.price).toFixed(2)}</strong>
                </div>
                <div className="trade-sheet__unit">
                    <div>
                        <span className="trade-sheet__label">Vklad</span>
                        <strong className="trade-sheet__amount-value">{formatPoints(amount)} bodů</strong>
                    </div>
                    <span className="trade-sheet__balance">Zůstatek {formatPoints(balance)} bodů</span>
                </div>
                <div className="stake-control">
                    <div className="stake-control__input-row">
                        <input
                            className="stake-control__input"
                            type="number"
                            min="100"
                            step="1"
                            value={amount}
                            onChange={(event) => onAmountChange(Number(event.target.value))}
                            aria-label="Částka sázky v bodech"
                        />
                        <span>bodů</span>
                    </div>
                    <div className="stake-control__quick-picks">
                        {[100, 500, 1000].map((value) => (
                            <button key={value} type="button" className={amount === value ? "active" : ""} onClick={() => onAmountChange(value)}>
                                {formatPoints(value)}
                            </button>
                        ))}
                        {balance >= 100 && (
                            <button type="button" className={amount === balance ? "active" : ""} onClick={() => onAmountChange(balance)}>
                                Vše
                            </button>
                        )}
                    </div>
                </div>
                {quote && (
                    <div className="trade-sheet__payout">
                        <span>Možná výhra</span>
                        <strong>{formatPoints(quote.gross_payout)} bodů</strong>
                    </div>
                )}
                <button className="trade-sheet__confirm" disabled={busy || !quote || amount < 100 || amount > balance} onClick={onConfirm}>
                    {busy ? "Odesílání…" : `Vsadit ${formatPoints(amount)} bodů`}
                </button>
            </section>
        </div>
    );
}
