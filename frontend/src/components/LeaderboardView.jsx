export default function LeaderboardView({ entries }) {
  return (
    <div>
      <h2 className="section-title">Žebříček</h2>
      {entries.length === 0 ? (
        <div className="empty-state">Zatím zde nejsou žádní hráči.</div>
      ) : (
        <table className="positions-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Hráč</th>
              <th>Hotovost</th>
              <th>Hodnota sázek</th>
              <th>Celkem</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((row, i) => (
              <tr key={row.username}>
                <td>{i + 1}</td>
                <td>{row.username}</td>
                <td className="num">{row.balance.toFixed(1)}</td>
                <td className="num">{row.portfolio_value.toFixed(1)}</td>
                <td className="num">{row.total_value.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
