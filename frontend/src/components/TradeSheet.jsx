import { X } from "lucide-react";

export default function TradeSheet({ outcome, quote, busy, onClose, onConfirm }) {
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
                    <span>Vklad</span>
                    <strong>1 bod</strong>
                </div>
                {quote && (
                    <div className="trade-sheet__payout">
                        <span>Možná výhra</span>
                        <strong>{quote.gross_payout.toFixed(2)} bodu</strong>
                    </div>
                )}
                <button className="trade-sheet__confirm" disabled={busy || !quote} onClick={onConfirm}>
                    {busy ? "Odesílání…" : "Vsadit 1 bod"}
                </button>
            </section>
        </div>
    );
}
