import { useEffect, useState, useCallback } from "react";
import { api } from "./api";
import LoginScreen from "./components/LoginScreen";
import TopBar from "./components/TopBar";
import LeaderboardView from "./components/LeaderboardView";
import MarketsView from "./components/MarketsView";
import PortfolioView from "./components/PortfolioView";
import AdminView from "./components/AdminView";
import BottomNav from "./components/BottomNav";

const ADMIN_KEY_KEY = "playmmf-admin-key";

export default function App() {
  const [username, setUsername] = useState("");
  const [adminKey, setAdminKey] = useState(() => localStorage.getItem(ADMIN_KEY_KEY) || "");
  const [adminVerified, setAdminVerified] = useState(false);
  const [tab, setTab] = useState("markets");

  const [user, setUser] = useState(null);
  const [markets, setMarkets] = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);
  const [positions, setPositions] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [error, setError] = useState(null);
  const [initialDataLoading, setInitialDataLoading] = useState(true);

  useEffect(() => {
    api.me()
      .then((currentUser) => {
        setUser(currentUser);
        setUsername(currentUser.username);
      })
      .catch(() => setUsername(""));
  }, []);

  const refreshAll = useCallback(async () => {
    if (!username) return;
    try {
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
    } catch (err) {
      setError(err.message || "Server není dostupný");
    } finally {
      setInitialDataLoading(false);
    }
  }, [username]);

  useEffect(() => {
    refreshAll();
    const interval = setInterval(refreshAll, 5000);
    return () => clearInterval(interval);
  }, [refreshAll]);

  useEffect(() => {
    localStorage.setItem(ADMIN_KEY_KEY, adminKey);
  }, [adminKey]);

  function handleLogin(currentUser) {
    setInitialDataLoading(true);
    setUser(currentUser);
    setUsername(currentUser.username);
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

        {tab === "markets" && (
          <MarketsView
            markets={markets}
            username={username}
            balance={user ? user.balance : 0}
            loading={initialDataLoading}
            onChanged={refreshAll}
            isAdmin={isAdmin}
            adminKey={adminKey}
          />
        )}
        {tab === "portfolio" && user && (
          <PortfolioView user={user} positions={positions} transactions={transactions} />
        )}
        {tab === "leaderboard" && <LeaderboardView entries={leaderboard} loading={initialDataLoading} />}
        {tab === "admin" && (
          <AdminView
            adminKey={adminKey}
            setAdminKey={setAdminKey}
            onAdminVerificationChange={setAdminVerified}
            onMarketCreated={refreshAll}
            onFactoryReset={handleFactoryReset}
          />
        )}
      </div>
      <BottomNav tab={tab} onChange={setTab} />
    </div>
  );
}
