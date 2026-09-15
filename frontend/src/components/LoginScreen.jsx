import { useState } from "react";
import { api } from "../api";

export default function LoginScreen({ onLogin }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const registering = mode === "register";

  async function handleSubmit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = registering
        ? await api.register(email, username, password)
        : await api.login(email, password);
      onLogin(response.user);
    } catch (err) {
      setError(err.message || "Přihlášení se nepodařilo");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={handleSubmit}>
        <h1>playmff</h1>
        <p>{registering ? "Vytvoř si účet pomocí školního e-mailu a sázej na výsledky turnaje." : "Přihlas se školním e-mailem a pokračuj ve svých sázkách."}</p>
        <div className="auth-mode-toggle">
          <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>Přihlášení</button>
          <button type="button" className={registering ? "active" : ""} onClick={() => setMode("register")}>Registrace</button>
        </div>
        <label htmlFor="auth-email">Školní e-mail</label>
        <input id="auth-email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
        {registering && (
          <>
            <label htmlFor="auth-username">Uživatelské jméno</label>
            <input id="auth-username" required minLength="3" maxLength="32" value={username} onChange={(event) => setUsername(event.target.value)} />
          </>
        )}
        <label htmlFor="auth-password">Heslo</label>
        <input id="auth-password" type="password" required minLength="8" maxLength="128" value={password} onChange={(event) => setPassword(event.target.value)} />
        {error && <div className="login-error">{error}</div>}
        <button className="btn-primary" disabled={loading}>{loading ? "Pracujeme…" : registering ? "Vytvořit účet" : "Přihlásit se"}</button>
      </form>
    </div>
  );
}
