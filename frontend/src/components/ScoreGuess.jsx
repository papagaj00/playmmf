import { useState } from "react";
import { Check, ChevronDown, Lock, Minus, Plus, Target, Trophy } from "lucide-react";
import { api } from "../api";
import { formatPoints } from "../format";

// Keep in sync with SCORE_GUESS_REWARD in backend/app/crud.py.
const GUESS_REWARD = 5000;
const MAX_GOALS = 99;

function Stepper({ value, onChange, label }) {
  const set = (next) => onChange(Math.min(MAX_GOALS, Math.max(0, next)));
  return (
    <div className="score-stepper">
      <button type="button" aria-label={`${label}: méně`} disabled={value <= 0} onClick={() => set(value - 1)}>
        <Minus size={16} />
      </button>
      <input
        inputMode="numeric"
        aria-label={label}
        value={value}
        onFocus={(event) => event.target.select()}
        onChange={(event) => {
          const digits = event.target.value.replace(/\D/g, "").slice(0, 2);
          set(digits === "" ? 0 : Number(digits));
        }}
      />
      <button type="button" aria-label={`${label}: více`} disabled={value >= MAX_GOALS} onClick={() => set(value + 1)}>
        <Plus size={16} />
      </button>
    </div>
  );
}

export default function ScoreGuess({ market, left, right, guess, onSaved }) {
  const [first, setFirst] = useState(guess?.first ?? 0);
  const [second, setSecond] = useState(guess?.second ?? 0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState(false);

  const resolved = market.status === "resolved";
  if (resolved && !guess) return null;

  const unchanged = guess && guess.first === first && guess.second === second;

  async function save() {
    setSaving(true);
    setError("");
    try {
      await api.saveGuess(market.id, first, second);
      await onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  const mode = resolved ? (guess.won ? "won" : "lost") : market.status === "open" ? "open" : "locked";
  const collapsedSummary = guess
    ? `${resolved ? (guess.won ? "Trefa" : "Bez výhry") : "Tvůj tip"} ${guess.first}:${guess.second}`
    : mode === "locked" ? "Uzavřeno" : null;
  const contentId = `score-guess-content-${market.id}`;

  return (
    <section className={`score-guess score-guess--${mode}`} aria-label="Tip na přesný výsledek">
      <button
        className="score-guess__toggle"
        type="button"
        aria-expanded={expanded}
        aria-controls={contentId}
        onClick={() => setExpanded((current) => !current)}
      >
        <span className="score-guess__toggle-copy">
          <span className="score-guess__title"><Target size={14} /> Tip na přesný výsledek</span>
          <span className="score-guess__reward"><b>+{formatPoints(GUESS_REWARD)} bodů</b> při přesné trefě · zdarma</span>
        </span>
        <span className="score-guess__toggle-end">
          {collapsedSummary && <span className="score-guess__saved">{collapsedSummary}</span>}
          <ChevronDown className={`score-guess__chevron ${expanded ? "is-open" : ""}`} size={17} />
        </span>
      </button>

      <div id={contentId} className="score-guess__content" hidden={!expanded}>
        {mode === "open" && (
          <>
          <div className="score-guess__board">
            <Stepper value={first} onChange={setFirst} label={`Góly týmu ${left.name}`} />
            <span className="score-guess__colon" aria-hidden="true">:</span>
            <Stepper value={second} onChange={setSecond} label={`Góly týmu ${right.name}`} />
          </div>
          <button
            type="button"
            className={`score-guess__submit ${unchanged ? "is-saved" : ""}`}
            disabled={saving || unchanged}
            onClick={save}
          >
            {saving ? "Ukládám…" : unchanged
              ? <><Check size={16} /> Tip uložen · {first}:{second}</>
              : `${guess ? "Změnit tip na" : "Odeslat tip"} ${first}:${second}`}
          </button>
          {error && <p className="score-guess__error">{error}</p>}
          </>
        )}

        {mode === "locked" && (
          <div className="score-guess__summary">
            <span className="score-guess__summary-label"><Lock size={13} /> {guess ? "Tvůj tip" : "Tipování uzavřeno"}</span>
            {guess && <span className="score-guess__score">{guess.first} : {guess.second}</span>}
          </div>
        )}

        {(mode === "won" || mode === "lost") && (
          <div className="score-guess__summary">
            <span className="score-guess__summary-label">
              {mode === "won" ? <><Trophy size={14} /> Trefa! +{formatPoints(GUESS_REWARD)} bodů</> : "Tvůj tip nevyšel"}
            </span>
            <span className="score-guess__score">{guess.first} : {guess.second}</span>
          </div>
        )}
      </div>
    </section>
  );
}
