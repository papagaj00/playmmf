import { formatPoints } from "../format";

export default function LeaderboardTicker({ entries }) {
  if (!entries.length) return null;
  const top = entries.slice(0, 8);
  return (
    <div className="ticker">
      {top.map((row, i) => (
        <div className="ticker__item" key={row.username}>
          <span className="ticker__rank">{i + 1}</span>
          <span className="ticker__name">{row.username}</span>
          <span className="ticker__value">{formatPoints(row.total_value)} bodů</span>
        </div>
      ))}
    </div>
  );
}
