import { useEffect, useState, useCallback, useRef } from "react";
import { api } from "./api";
import LoginScreen from "./components/LoginScreen";
import TopBar from "./components/TopBar";
import LeaderboardView from "./components/LeaderboardView";
import MarketsView from "./components/MarketsView";
import PortfolioView from "./components/PortfolioView";
import AdminView from "./components/AdminView";
import BottomNav from "./components/BottomNav";
import TournamentView from "./components/TournamentView";

const TAB_ORDER = ["markets", "portfolio", "leaderboard", "tournament", "admin"];

export default function App() {
  const [username, setUsername] = useState("");
  const [adminVerified, setAdminVerified] = useState(false);
  const [tab, setTab] = useState("markets");

  const [user, setUser] = useState(null);
  const [markets, setMarkets] = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);
  const [positions, setPositions] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [rosters, setRosters] = useState([]);
  const [guesses, setGuesses] = useState([]);
  const [error, setError] = useState(null);
  const [initialDataLoading, setInitialDataLoading] = useState(true);
  const [maintenance, setMaintenance] = useState(false);
  const refreshFailures = useRef(0);
  const swipeStart = useRef(null);

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
      if (system.maintenance && !adminVerified) {
        setInitialDataLoading(false);
        setError(null);
        return;
      }
      const [u, m, lb, pos, tx, rosterData, guessData] = await Promise.all([
        api.getUser(username),
        api.listMarkets(),
        api.getLeaderboard(),
        api.getPositions(username),
        api.getTransactions(username),
        api.getTeamRosters(),
        api.getGuesses(username),
      ]);
      setUser(u);
      setMarkets(m);
      setLeaderboard(lb);
      setPositions(pos);
      setTransactions(tx);
      setRosters(rosterData);
      setGuesses(guessData);
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
  }, [adminVerified, username, markets.length]);

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

  function handleMaintenanceChange(enabled) {
    setMaintenance(enabled);
    if (!enabled) refreshAll();
  }

  function handleRosterChange(updatedRoster) {
    setRosters((current) => current.map((roster) => roster.id === updatedRoster.id ? updatedRoster : roster));
  }

  if (!username) {
    return <LoginScreen onLogin={handleLogin} />;
  }

  const isAdmin = adminVerified;
  const canUseApp = !maintenance || isAdmin;
  const handleTouchStart = (event) => {
    if (event.touches.length !== 1 || event.target.closest?.("button, a, input, textarea, select, [data-no-tab-swipe]")) {
      swipeStart.current = null;
      return;
    }
    const { clientX, clientY } = event.touches[0];
    swipeStart.current = { x: clientX, y: clientY };
  };
  const handleTouchEnd = (event) => {
    const start = swipeStart.current;
    swipeStart.current = null;
    if (!start || !canUseApp) return;

    const touch = event.changedTouches[0];
    const deltaX = touch.clientX - start.x;
    const deltaY = touch.clientY - start.y;
    if (Math.abs(deltaX) < 60 || Math.abs(deltaX) <= Math.abs(deltaY) * 1.3) return;

    const tabs = TAB_ORDER.filter((id) => id !== "admin" || isAdmin);
    const nextIndex = tabs.indexOf(tab) + (deltaX < 0 ? 1 : -1);
    if (nextIndex >= 0 && nextIndex < tabs.length) setTab(tabs[nextIndex]);
  };

  return (
    <div className="app">
      <TopBar username={username} balance={user ? user.balance : 0} onLogout={handleLogout} isAdmin={isAdmin} />
      <div className="main" onTouchStart={handleTouchStart} onTouchEnd={handleTouchEnd} onTouchCancel={() => { swipeStart.current = null; }}>
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
        {canUseApp && tab === "markets" && (
          <MarketsView
            markets={markets}
            username={username}
            balance={user ? user.balance : 0}
            positions={positions}
            guesses={guesses}
            loading={initialDataLoading}
            onChanged={refreshAll}
            isAdmin={isAdmin}
          />
        )}
        {canUseApp && tab === "portfolio" && user && (
          <PortfolioView user={user} positions={positions} transactions={transactions} loading={initialDataLoading} />
        )}
        {canUseApp && tab === "leaderboard" && <LeaderboardView entries={leaderboard} username={username} loading={initialDataLoading} />}
        {canUseApp && tab === "tournament" && <TournamentView markets={markets} rosters={rosters} loading={initialDataLoading} isAdmin={isAdmin} onRosterChange={handleRosterChange} />}
        {tab === "admin" && (
          <AdminView
            isAdmin={adminVerified}
            onMarketCreated={refreshAll}
            maintenance={maintenance}
            onMaintenanceChange={handleMaintenanceChange}
          />
        )}
      </div>
      <BottomNav tab={tab} onChange={setTab} isAdmin={isAdmin} />
    </div>
  );
}
