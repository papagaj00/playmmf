import { formatPoints } from "../format";
import LoadingState from "./LoadingState";

export default function LeaderboardView({ entries, loading }) {
  return (
    <div className="leaderboard-view">
      <h2 className="section-title">Žebříček</h2>
      {loading ? (
        <LoadingState label="Načítám žebříček…" />
      ) : entries.length === 0 ? (
        <div className="empty-state">Zatím zde nejsou žádní hráči.</div>
      ) : (
        <table className="positions-table leaderboard-table">
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
