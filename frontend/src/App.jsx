import { useEffect, useState, useCallback, useRef } from "react";
import { api } from "./api";
import LoginScreen from "./components/LoginScreen";
import TopBar from "./components/TopBar";
import LeaderboardView from "./components/LeaderboardView";
import MarketsView from "./components/MarketsView";
import PortfolioView from "./components/PortfolioView";
import AdminView from "./components/AdminView";
import BottomNav from "./components/BottomNav";

export default function App() {
  const [username, setUsername] = useState("");
  const [adminVerified, setAdminVerified] = useState(false);
  const [tab, setTab] = useState("markets");

  const [user, setUser] = useState(null);
  const [markets, setMarkets] = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);
  const [positions, setPositions] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [error, setError] = useState(null);
  const [initialDataLoading, setInitialDataLoading] = useState(true);
  const [maintenance, setMaintenance] = useState(false);
  const refreshFailures = useRef(0);

  useEffect(() => {
    api.me()
      .then((currentUser) => {
        setUser(currentUser);
        setUsername(currentUser.username);
        setAdminVerified(currentUser.is_admin);
      })
      .catch(() => setUsername(""));
  }, []);

  const refreshAll = useCallback(async () => {
    if (!username) return;
    try {
      const system = await api.systemStatus();
      setMaintenance(system.maintenance);
      if (system.maintenance) {
        setInitialDataLoading(false);
        setError(null);
        return;
      }
      const [u, m, lb, pos, tx] = await Promise.all([
        api.getUser(username),
        api.listMarkets(),
        api.getLeaderboard(),
        api.getPositions(username),
        api.getTransactions(username),
      ]);
      setUser(u);
      setMarkets(m);
      setLeaderboard(lb);
      setPositions(pos);
      setTransactions(tx);
      setError(null);
      refreshFailures.current = 0;
    } catch (err) {
      refreshFailures.current += 1;
      if (refreshFailures.current >= 2) {
        setError(err.message || "Server není dostupný");
      }
    } finally {
      setInitialDataLoading(refreshFailures.current > 0 && !markets.length);
    }
  }, [username, markets.length]);

  useEffect(() => {
    refreshAll();
    const interval = setInterval(refreshAll, 5000);
    return () => clearInterval(interval);
  }, [refreshAll]);

  function handleLogin(currentUser) {
    setInitialDataLoading(true);
    setUser(currentUser);
    setUsername(currentUser.username);
    setAdminVerified(currentUser.is_admin);
  }

  function handleLogout() {
    api.logout().finally(() => {
      setUsername("");
      setUser(null);
      setAdminVerified(false);
      setTab("markets");
    });
  }

  function handleFactoryReset() {
    setUsername("");
    setUser(null);
    setMarkets([]);
    setLeaderboard([]);
    setPositions([]);
    setTransactions([]);
    setAdminVerified(false);
    setTab("markets");
  }

  function handleMaintenanceChange(enabled) {
    setMaintenance(enabled);
    if (!enabled) refreshAll();
  }

  if (!username) {
    return <LoginScreen onLogin={handleLogin} />;
  }

  const isAdmin = adminVerified;

  return (
    <div className="app">
      <TopBar username={username} balance={user ? user.balance : 0} onLogout={handleLogout} />
      <div className="main">
        {error && (
          <div className="trade-message error" style={{ marginBottom: 20 }}>
            {error} — běží backend na očekávané adrese?
          </div>
        )}

        {maintenance && !isAdmin && (
          <div className="maintenance-screen" role="status">
            <div className="maintenance-screen__mark">●</div>
            <h2>Maintenance break</h2>
            <p>The app is temporarily paused. Please check back later.</p>
          </div>
        )}
        {!maintenance && tab === "markets" && (
          <MarketsView
            markets={markets}
            username={username}
            balance={user ? user.balance : 0}
            positions={positions}
            loading={initialDataLoading}
            onChanged={refreshAll}
            isAdmin={isAdmin}
          />
        )}
        {!maintenance && tab === "portfolio" && user && (
          <PortfolioView user={user} positions={positions} transactions={transactions} />
        )}
        {!maintenance && tab === "leaderboard" && <LeaderboardView entries={leaderboard} username={username} loading={initialDataLoading} />}
        {tab === "admin" && (
          <AdminView
            isAdmin={adminVerified}
            onMarketCreated={refreshAll}
            onFactoryReset={handleFactoryReset}
            maintenance={maintenance}
            onMaintenanceChange={handleMaintenanceChange}
          />
        )}
      </div>
      <BottomNav tab={tab} onChange={setTab} isAdmin={isAdmin} />
    </div>
  );
}
