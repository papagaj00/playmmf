import { useEffect, useState } from "react";
import { api } from "../api";

export default function AdminView({ adminKey, setAdminKey, onAdminVerificationChange, onMarketCreated, onFactoryReset }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [b, setB] = useState(100);
  const [outcomeNames, setOutcomeNames] = useState(["", ""]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);
  const [verified, setVerified] = useState(false);
  const [checkingKey, setCheckingKey] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!adminKey.trim()) {
      setVerified(false);
      onAdminVerificationChange(false);
      return undefined;
    }
    setCheckingKey(true);
    api.verifyAdminKey(adminKey)
      .then(() => {
        if (!cancelled) {
          setVerified(true);
          onAdminVerificationChange(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setVerified(false);
          onAdminVerificationChange(false);
        }
      })
      .finally(() => {
        if (!cancelled) setCheckingKey(false);
      });
    return () => {
      cancelled = true;
    };
  }, [adminKey, onAdminVerificationChange]);

  async function handleFactoryReset() {
    const confirmed = window.confirm(
      "Tovární reset trvale smaže všechny uživatele, zápasy, sázky a historii. Pokračovat?"
    );
    if (!confirmed) return;

    setBusy(true);
    setMessage(null);
    try {
      await api.factoryReset(adminKey);
      onFactoryReset();
    } catch (err) {
      setMessage({ type: "error", text: err.message });
      setBusy(false);
    }
  }

  function updateOutcome(i, value) {
    const next = [...outcomeNames];
    next[i] = value;
    setOutcomeNames(next);
  }

  function addOutcome() {
    setOutcomeNames([...outcomeNames, ""]);
  }

  function removeOutcome(i) {
    setOutcomeNames(outcomeNames.filter((_, idx) => idx !== i));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const names = outcomeNames.map((n) => n.trim()).filter(Boolean);
    if (!title.trim() || names.length < 2) {
      setMessage({ type: "error", text: "Zadej název zápasu a alespoň 2 možné výsledky." });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      await api.createMarket(
        { title: title.trim(), description: description.trim(), b: Number(b), outcome_names: names },
        adminKey
      );
      setMessage({ type: "success", text: "Zápas byl vytvořen." });
      setTitle("");
      setDescription("");
      setOutcomeNames(["", ""]);
      onMarketCreated();
    } catch (err) {
      setMessage({ type: "error", text: err.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h2 className="section-title">Správa</h2>

      <div className="admin-form">
        <label>Administrátorský klíč</label>
        <input
          type="password"
          value={adminKey}
          onChange={(e) => {
            setAdminKey(e.target.value);
            setVerified(false);
            onAdminVerificationChange(false);
          }}
        />
        {checkingKey && <p className="admin-key-status">Ověřování klíče…</p>}
        {!checkingKey && adminKey && !verified && (
          <p className="admin-key-status error">Klíč není platný.</p>
        )}
      </div>

      {verified && <>
        <form className="admin-form" onSubmit={handleSubmit}>
          <label>Název zápasu</label>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Semifinále: Lvi vs. Tygři" />

          <label>Popis (nepovinné)</label>
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Vítěz postupuje do sobotního finále"
          />

          <label>Parametr likvidity (b)</label>
          <input type="number" min="1" step="1" value={b} onChange={(e) => setB(e.target.value)} />

          <label>Možné výsledky</label>
          {outcomeNames.map((name, i) => (
            <div className="outcome-input-row" key={i}>
              <input
                value={name}
                onChange={(e) => updateOutcome(i, e.target.value)}
                placeholder={`Výsledek ${i + 1}`}
              />
              {outcomeNames.length > 2 && (
                <button type="button" className="btn-small" onClick={() => removeOutcome(i)}>
                  Odebrat
                </button>
              )}
            </div>
          ))}
          <button type="button" className="btn-small" onClick={addOutcome}>
            + Přidat výsledek
          </button>

          {message && <div className={`trade-message ${message.type}`} style={{ marginTop: 12 }}>{message.text}</div>}

          <div className="admin-form-actions">
            <button className="btn-primary" disabled={busy}>
              {busy ? "Vytváření…" : "Vytvořit zápas"}
            </button>
          </div>
        </form>

        <section className="admin-form" style={{ marginTop: 28 }}>
          <h3>Tovární reset</h3>
          <p>Tato akce trvale smaže všechny uživatele, zápasy, sázky a historii transakcí.</p>
          <button
            type="button"
            className="btn-small"
            disabled={busy || !adminKey.trim()}
            onClick={handleFactoryReset}
          >
            Obnovit aplikaci do výchozího stavu
          </button>
        </section>
      </>}
    </div>
  );
}
