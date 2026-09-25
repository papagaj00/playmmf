import { formatPoints } from "../format";

const STATUS_LABELS = {
  open: "otevřená",
  closed: "uzavřená",
  resolved: "vyhodnocená",
};

export default function PortfolioView({ user, positions, transactions }) {
  const activity = transactions.filter((transaction) => transaction.type !== "payout");

  return (
    <div>
      <h2 className="section-title">Moje sázky</h2>
      <div className="stat-row stat-row--single">
        <div className="stat-box">
          <div className="stat-box__label">Hotovost</div>
          <div className="stat-box__value">{formatPoints(user.balance)}</div>
        </div>
      </div>

      <h3 className="section-title" style={{ fontSize: 18 }}>
        Otevřené sázky
      </h3>
      {positions.length === 0 ? (
        <div className="empty-state">Zatím nemáš žádné otevřené sázky. Vyber si tip v sekci Zápasy.</div>
      ) : (
        <table className="positions-table" style={{ marginBottom: 28 }}>
          <thead>
            <tr>
              <th>Zápas</th>
              <th>Tip</th>
              <th>Možná výhra</th>
              <th>Stav</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr key={`${p.market_id}-${p.outcome_id}`}>
                <td>{p.market_title}</td>
                <td>{p.outcome_name}</td>
                <td className="num">{formatPoints(p.potential_payout)}</td>
                <td>{STATUS_LABELS[p.market_status] || p.market_status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3 className="section-title" style={{ fontSize: 18 }}>
        Poslední aktivita
      </h3>
      {activity.length === 0 ? (
        <div className="empty-state">Zatím žádná aktivita.</div>
      ) : (
        <table className="positions-table">
          <thead>
            <tr>
              <th>Zápas</th>
              <th>Tip</th>
              <th>Vklad</th>
              <th>Výsledek</th>
            </tr>
          </thead>
          <tbody>
            {activity.slice(0, 20).map((t) => (
              <tr key={t.id}>
                {t.type === "grant" ? (
                  <>
                    <td>Startovní body</td>
                    <td>—</td>
                    <td className="num">+{formatPoints(Math.abs(t.amount))} bodů</td>
                    <td className="activity-result neutral">Připsáno</td>
                  </>
                ) : (
                  <>
                    <td>{t.market_title || "—"}</td>
                    <td>{t.outcome_name || "—"}</td>
                    <td className="num">{formatPoints(t.amount)} bodů</td>
                    <td className={`activity-result ${t.resolved ? (t.won ? "won" : "lost") : "pending"}`}>
                      {!t.resolved ? "Čeká" : t.won ? `+${formatPoints(t.winnings)} bodů` : "Prohra"}
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
