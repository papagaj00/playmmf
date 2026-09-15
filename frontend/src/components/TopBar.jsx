import { useState } from "react";
import { ChevronDown, LogOut } from "lucide-react";
import { formatPoints } from "../format";

export default function TopBar({ username, balance, onLogout }) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="topbar">
      <p className="topbar__brand">
        playmmf
      </p>
      <div className="topbar__right">
        <button className="balance-chip" onClick={() => setMenuOpen((open) => !open)} aria-expanded={menuOpen}>
          <b>{formatPoints(balance)}</b> bodů
          <ChevronDown size={16} />
        </button>
        {menuOpen && (
          <div className="account-menu">
            <span>{username}</span>
            <button onClick={onLogout}><LogOut size={16} /> Přepnout uživatele</button>
          </div>
        )}
      </div>
    </div>
  );
}
