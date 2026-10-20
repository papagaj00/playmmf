import { useEffect, useState } from "react";
import { api } from "../api";

export default function AdminView({
  isAdmin,
  onMarketCreated,
  maintenance,
  onMaintenanceChange,
  scoreGuessReward,
  onScoreGuessRewardChange,
}) {
  const [description, setDescription] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [stage, setStage] = useState("group");
  const [b, setB] = useState(20000);
  const [teamIds, setTeamIds] = useState(["", ""]);
  const [initialProbabilities, setInitialProbabilities] = useState([50, 50]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);
  const [rewardMessage, setRewardMessage] = useState(null);
  const [points, setPoints] = useState(0);
  const [users, setUsers] = useState([]);
  const [teams, setTeams] = useState([]);
  const [selectedUserId, setSelectedUserId] = useState("");
  const [rewardDraft, setRewardDraft] = useState(String(scoreGuessReward));

  useEffect(() => {
    setRewardDraft(String(scoreGuessReward));
  }, [scoreGuessReward]);

  useEffect(() => {
    if (isAdmin) {
      api.getAdminUsers().then(setUsers).catch(() => setUsers([]));
      api.getTeams().then(setTeams).catch(() => setTeams([]));
    }
  }, [isAdmin]);

  async function handleMaintenanceToggle() {
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.setMaintenance(!maintenance);
      onMaintenanceChange(result.maintenance);
      setMessage({
        type: "success",
        text: result.maintenance ? "Maintenance break zapnut." : "Maintenance break vypnut.",
      });
    } catch (err) {
      setMessage({ type: "error", text: err.message });
    } finally {
      setBusy(false);
    }
  }

  async function handleBalanceAdjustment(e) {
    e.preventDefault();
    const value = Number(points);
    if (!Number.isFinite(value) || value === 0) {
      setMessage({ type: "error", text: "Zadej nenulový počet bodů." });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.adjustBalances(value, selectedUserId);
      setMessage({
        type: "success",
        text: result.scope === "all"
          ? `Upraveno účtů: ${result.updated_users}.`
          : "Body hráče byly upraveny.",
      });
      onMarketCreated();
    } catch (err) {
      setMessage({ type: "error", text: err.message });
    } finally {
      setBusy(false);
    }
  }

  async function handleScoreGuessRewardSave(event) {
    event.preventDefault();
    const amount = Number(rewardDraft);
    if (!Number.isSafeInteger(amount) || amount < 0 || amount > 1_000_000_000) {
      setRewardMessage({ type: "error", text: "Odměna musí být celé číslo od 0 do 1 000 000 000." });
      return;
    }
    setBusy(true);
    setRewardMessage(null);
    try {
      const result = await api.setScoreGuessReward(amount);
      onScoreGuessRewardChange(result.amount);
      setRewardMessage({ type: "success", text: `Odměna za přesný tip je nyní ${result.amount} bodů.` });
    } catch (err) {
      setRewardMessage({ type: "error", text: err.message });
    } finally {
      setBusy(false);
    }
  }

  function updateTeam(i, value) {
    const next = [...teamIds];
    next[i] = value;
    setTeamIds(next);
  }

  function addOutcome() {
    setTeamIds([...teamIds, ""]);
    setInitialProbabilities([...initialProbabilities, 0]);
  }

  function removeOutcome(i) {
    setTeamIds(teamIds.filter((_, idx) => idx !== i));
    setInitialProbabilities(initialProbabilities.filter((_, idx) => idx !== i));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const selectedTeamIds = teamIds.map((id) => Number(id)).filter(Boolean);
    const names = selectedTeamIds.map((id) => teams.find((team) => team.id === id)?.name).filter(Boolean);
    const probabilities = initialProbabilities.map(Number);
    const probabilityTotal = probabilities.reduce((total, value) => total + value, 0);
    if (!scheduledAt || selectedTeamIds.length < 2 || new Set(selectedTeamIds).size !== selectedTeamIds.length) {
      setMessage({ type: "error", text: "Zadej datum a čas zápasu a vyber alespoň 2 různé týmy." });
      return;
    }
    if (probabilities.length !== selectedTeamIds.length || probabilities.some((value) => !Number.isFinite(value) || value <= 0) || Math.abs(probabilityTotal - 100) > 0.01) {
      setMessage({ type: "error", text: `Pravděpodobnosti musí být kladné a mít součet 100 % (aktuálně ${probabilityTotal.toFixed(1)} %).` });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      await api.createMarket(
        {
          description: description.trim(),
          b: Number(b),
          stage,
          outcome_names: names,
          team_ids: selectedTeamIds,
          initial_probabilities: probabilities,
          scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : null,
        },
      );
      setMessage({ type: "success", text: "Zápas byl vytvořen." });
      setDescription("");
      setScheduledAt("");
      setStage("group");
      setTeamIds(["", ""]);
      setInitialProbabilities([50, 50]);
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

      {isAdmin && <>
        <section className="admin-form maintenance-control">
          <h3>Maintenance break</h3>
          <p>{maintenance ? "Hráči nyní nemají k aplikaci přístup." : "Pozastav přístup hráčům do aplikace."}</p>
          <button type="button" className="btn-small" disabled={busy} onClick={handleMaintenanceToggle}>
            {maintenance ? "Vypnout maintenance break" : "Zapnout maintenance break"}
          </button>
        </section>

        <form className="admin-form" style={{ marginTop: 28 }} onSubmit={handleScoreGuessRewardSave}>
          <h3>Odměna za přesný výsledek</h3>
          <p>Částka vyplacená hráči za správný tip na přesné skóre.</p>
          <div className="admin-inline-form">
            <input
              type="number"
              min="0"
              max="1000000000"
              step="1"
              value={rewardDraft}
              onChange={(event) => setRewardDraft(event.target.value)}
              aria-label="Odměna za přesný výsledek v bodech"
              required
            />
            <button className="btn-small" disabled={busy}>
              {busy ? "Ukládání…" : "Uložit odměnu"}
            </button>
          </div>
          {rewardMessage && <div className={`trade-message ${rewardMessage.type}`} style={{ marginTop: 12 }}>{rewardMessage.text}</div>}
        </form>

        <form className="admin-form" onSubmit={handleSubmit}>
          <label>Popis (nepovinné)</label>
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Vítěz postupuje do sobotního finále"
          />

          <label htmlFor="market-scheduled-at">Datum a čas zápasu</label>
          <input
            id="market-scheduled-at"
            type="datetime-local"
            value={scheduledAt}
            onChange={(e) => setScheduledAt(e.target.value)}
            required
          />

          <label>Celkový počáteční pool (b)</label>
          <input type="number" min="1" step="1" value={b} onChange={(e) => setB(e.target.value)} />

          <label htmlFor="market-stage">Fáze turnaje</label>
          <select id="market-stage" value={stage} onChange={(e) => setStage(e.target.value)}>
            <option value="group">Skupinová fáze</option>
            <option value="quarterfinal">Čtvrtfinále</option>
            <option value="semifinal">Semifinále</option>
            <option value="third_place">O 3. místo</option>
            <option value="final">Finále</option>
          </select>

          <label>Možné výsledky</label>
          {teamIds.map((teamId, i) => (
            <div className="outcome-input-row" key={i}>
              <select value={teamId} onChange={(e) => updateTeam(i, e.target.value)} required>
                <option value="">Vyber tým {i + 1}</option>
                {teams.map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}
              </select>
              {teamIds.length > 2 && (
                <button type="button" className="btn-small" onClick={() => removeOutcome(i)}>
                  Odebrat
                </button>
              )}
            </div>
          ))}
          <button type="button" className="btn-small" onClick={addOutcome}>
            + Přidat výsledek
          </button>

          <label>Počáteční pravděpodobnosti (%)</label>
          {teamIds.map((teamId, i) => (
            <div className="outcome-input-row probability-input-row" key={`probability-${i}`}>
              <span>{teams.find((team) => String(team.id) === teamId)?.name || `Výsledek ${i + 1}`}</span>
              <input
                type="number"
                min="0.01"
                max="99.99"
                step="0.01"
                value={initialProbabilities[i] ?? ""}
                onChange={(e) => setInitialProbabilities(initialProbabilities.map((value, index) => index === i ? e.target.value : value))}
                aria-label={`Pravděpodobnost výsledku ${i + 1} v procentech`}
              />
              <span>%</span>
            </div>
          ))}

          {message && <div className={`trade-message ${message.type}`} style={{ marginTop: 12 }}>{message.text}</div>}

          <div className="admin-form-actions">
            <button className="btn-primary" disabled={busy}>
              {busy ? "Vytváření…" : "Vytvořit zápas"}
            </button>
          </div>
        </form>

        <section className="admin-form" style={{ marginTop: 28 }}>
          <h3>Body hráčů</h3>
          <p>Přidej nebo odeber body jednomu hráči nebo všem hráčům.</p>
          <form className="admin-inline-form" onSubmit={handleBalanceAdjustment}>
            <select value={selectedUserId} onChange={(e) => setSelectedUserId(e.target.value)}>
              <option value="">Všichni hráči</option>
              {users.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.username} {user.is_shadow ? "(shadow) " : ""}{user.is_banned ? "(zablokován)" : ""}
                </option>
              ))}
            </select>
            <input type="number" step="0.01" value={points} onChange={(e) => setPoints(e.target.value)} />
            <button className="btn-small" disabled={busy}>Upravit body</button>
          </form>
        </section>

      </>}
    </div>
  );
}
