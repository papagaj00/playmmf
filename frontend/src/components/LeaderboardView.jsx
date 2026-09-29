import { formatPoints } from "../format";
import LoadingState from "./LoadingState";

export default function LeaderboardView({ entries, username, loading }) {
  const podiumEntries = entries.slice(0, 3);
  const tableEntries = entries.slice(3);

  return (
    <div className="leaderboard-view">
      <h2 className="section-title">Žebříček</h2>
      {loading ? (
        <LoadingState label="Načítám žebříček…" />
      ) : entries.length === 0 ? (
        <div className="empty-state">Zatím zde nejsou žádní hráči.</div>
      ) : (
        <>
          <div className="winners-podium" aria-label="Nejlepší hráči">
            {[1, 0, 2].map((entryIndex) => {
              const row = podiumEntries[entryIndex];
              if (!row) return <div className={`podium-slot podium-slot--${entryIndex + 1}`} key={entryIndex} />;
              const rank = entryIndex + 1;
              return (
                <div
                  className={`podium-slot podium-slot--${rank} ${row.username === username ? "podium-slot--current" : ""}`}
                  key={row.username}
                >
                  <div className="podium-player">
                    <span className="podium-medal">{rank === 1 ? "1" : rank === 2 ? "2" : "3"}</span>
                    <strong>{row.username}</strong>
                    <span>{formatPoints(row.balance)} bodů</span>
                  </div>
                  <div className="podium-block"><span>{rank}</span></div>
                </div>
              );
            })}
          </div>

          {tableEntries.length > 0 && (
            <table className="positions-table leaderboard-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Hráč</th>
                  <th>Body</th>
                </tr>
              </thead>
              <tbody>
                {tableEntries.map((row, index) => (
                  <tr key={row.username} className={row.username === username ? "leaderboard-row--current" : ""}>
                    <td>{index + 4}</td>
                    <td>{row.username}</td>
                    <td className="num">{formatPoints(row.balance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
