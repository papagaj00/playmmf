const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function request(path, { method = "GET", body, adminKey } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (adminKey) headers["X-Admin-Key"] = adminKey;

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    credentials: "include",
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

export const api = {
  register: (email, username, password) =>
    request("/auth/register", { method: "POST", body: { email, username, password } }),
  login: (email, password) =>
    request("/auth/login", { method: "POST", body: { email, password } }),
  logout: () => request("/auth/logout", { method: "POST" }),
  me: () => request("/auth/me"),
  getUser: (username) => request(`/users/${encodeURIComponent(username)}`),
  getPositions: (username) => request(`/users/${encodeURIComponent(username)}/positions`),
  getTransactions: (username) => request(`/users/${encodeURIComponent(username)}/transactions`),
  verifyAdminKey: (adminKey) => request("/admin/verify", { adminKey }),
  getLeaderboard: () => request("/leaderboard"),
  factoryReset: (adminKey) =>
    request("/admin/factory-reset", { method: "POST", adminKey }),

  listMarkets: () => request("/markets"),
  getMarket: (id) => request(`/markets/${id}`),
  createMarket: (payload, adminKey) =>
    request("/markets", { method: "POST", body: payload, adminKey }),
  setMarketStatus: (id, status, adminKey) =>
    request(`/markets/${id}/status?status=${status}`, { method: "POST", adminKey }),
  resolveMarket: (id, winning_outcome_id, adminKey) =>
    request(`/markets/${id}/resolve`, {
      method: "POST",
      body: { winning_outcome_id },
      adminKey,
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
