import MarketCard from "./MarketCard";
import LoadingState from "./LoadingState";

export default function MarketsView({ markets, username, balance, positions, loading, onChanged, isAdmin, adminKey }) {
  const open = markets.filter((m) => m.status !== "resolved");
  const resolved = markets.filter((m) => m.status === "resolved");

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
          adminKey={adminKey}
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
              adminKey={adminKey}
            />
          ))}
        </>
      )}
    </div>
  );
}
