import MarketCard from "./MarketCard";
import LoadingState from "./LoadingState";

export default function MarketsView({ markets, username, balance, positions, loading, onChanged, isAdmin }) {
  const sortBySchedule = (left, right) => {
    if (left.scheduled_at && right.scheduled_at) {
      return new Date(left.scheduled_at) - new Date(right.scheduled_at);
    }
    if (left.scheduled_at) return -1;
    if (right.scheduled_at) return 1;
    return 0;
  };
  const open = markets.filter((m) => m.status !== "resolved").sort(sortBySchedule);
  const resolved = markets.filter((m) => m.status === "resolved").sort(sortBySchedule);

  return (
    <div>
      <h2 className="section-title">Zápasy</h2>
      {loading && <LoadingState label="Načítám zápasy…" />}
      {!loading && markets.length === 0 && <div className="empty-state">Zatím nejsou vytvořené žádné zápasy.</div>}

      {open.map((m) => (
        <MarketCard
          key={m.id}
          market={m}
          username={username}
          balance={balance}
          positions={positions}
          onChanged={onChanged}
          isAdmin={isAdmin}
        />
      ))}

      {resolved.length > 0 && (
        <>
          <h3 className="section-title" style={{ fontSize: 18, marginTop: 32 }}>
            Vyhodnocené zápasy
          </h3>
          {resolved.map((m) => (
            <MarketCard
              key={m.id}
              market={m}
              username={username}
              balance={balance}
              positions={positions}
              onChanged={onChanged}
              isAdmin={isAdmin}
            />
          ))}
        </>
      )}
    </div>
  );
}
