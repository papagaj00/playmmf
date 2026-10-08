const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const TOKEN_KEY = "gbn-token";

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch {
      // response wasn't JSON; keep statusText
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

async function requestAuth(path, body) {
  const result = await request(path, { method: "POST", body });
  setToken(result.token);
  return result;
}

export const api = {
  register: (email, username, password) =>
    requestAuth("/auth/register", { email, username, password }),
  login: (email, password) => requestAuth("/auth/login", { email, password }),
  logout: async () => {
    try {
      await request("/auth/logout", { method: "POST" });
    } finally {
      setToken(null);
    }
  },
  me: () => request("/auth/me"),
  systemStatus: () => request("/system/status"),
  getInfoMessages: () => request("/info/messages"),
  getPushPublicKey: () => request("/push/public-key"),
  getPushStatus: () => request("/push/status"),
  subscribePush: (payload) => request("/push/subscribe", { method: "POST", body: payload }),
  unsubscribePush: (payload) => request("/push/subscribe", { method: "DELETE", body: payload }),
  createInfoMessage: (text) =>
    request("/admin/info/messages", { method: "POST", body: { text } }),
  getUser: (username) => request(`/users/${encodeURIComponent(username)}`),
  getPositions: (username) => request(`/users/${encodeURIComponent(username)}/positions`),
  getTransactions: (username) => request(`/users/${encodeURIComponent(username)}/transactions`),
  verifyAdmin: () => request("/admin/verify"),
  setMaintenance: (maintenance) =>
    request("/admin/maintenance", {
      method: "POST",
      body: { maintenance },
    }),
  getAdminUsers: () => request("/admin/users"),
  getTeams: () => request("/teams"),
  getTeamRosters: () => request("/teams/rosters"),
  getLeaderboard: () => request("/leaderboard"),
  factoryReset: () =>
    request("/admin/factory-reset", { method: "POST" }),
  adjustBalances: (points, userId) =>
    request("/admin/balance-adjustment", {
      method: "POST",
      body: { points, user_id: userId || null },
    }),
  banUser: (email) =>
    request("/admin/users/ban", { method: "POST", body: { email } }),
  unbanUser: (email) =>
    request("/admin/users/unban", { method: "POST", body: { email } }),
  addTeamPlayer: (teamId, name, goals) =>
    request(`/admin/teams/${teamId}/players`, { method: "POST", body: { name, goals } }),
  updateTeamPlayer: (teamId, playerId, name, goals) =>
    request(`/admin/teams/${teamId}/players/${playerId}`, {
      method: "PATCH",
      body: { name, goals },
    }),
  deleteTeamPlayer: (teamId, playerId) =>
    request(`/admin/teams/${teamId}/players/${playerId}`, { method: "DELETE" }),

  listMarkets: () => request("/markets"),
  getMarket: (id) => request(`/markets/${id}`),
  createMarket: (payload) =>
    request("/markets", { method: "POST", body: payload }),
  setMarketStatus: (id, status) =>
    request(`/markets/${id}/status?status=${status}`, { method: "POST" }),
  deleteMarket: (id) =>
    request(`/markets/${id}`, { method: "DELETE" }),
  resolveMarket: (id, result) =>
    request(`/markets/${id}/resolve`, {
      method: "POST",
      body: { result },
    }),

  quoteWager: (marketId, outcome_id, amount) =>
    request(`/markets/${marketId}/wager/quote`, {
      method: "POST",
      body: { outcome_id, amount },
    }),
  placeWager: (marketId, outcome_id, amount) =>
    request(`/markets/${marketId}/wager`, {
      method: "POST",
      body: { outcome_id, amount },
    }),
};