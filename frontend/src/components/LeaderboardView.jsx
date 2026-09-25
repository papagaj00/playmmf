import { formatPoints } from "../format";

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
            </tr>
          </thead>
          <tbody>
            {entries.map((row, i) => (
              <tr key={row.username}>
                <td>{i + 1}</td>
                <td>{row.username}</td>
                <td className="num">{formatPoints(row.balance)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
