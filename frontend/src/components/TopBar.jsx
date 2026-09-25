import { useState } from "react";
import { ChevronDown, CircleHelp, LogOut, X } from "lucide-react";
import { formatPoints } from "../format";

export default function TopBar({ username, balance, onLogout }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);

  return (
    <div className="topbar">
      <div className="topbar__brand">
        <img src="/playmmf-logo.svg" alt="playmmf" />
        <span>playmmf</span>
      </div>
      <div className="topbar__right">
        <button
          className="help-button"
          type="button"
          aria-label="Nápověda a kontakt"
          aria-expanded={helpOpen}
          onClick={() => setHelpOpen((open) => !open)}
        >
          <CircleHelp size={18} />
          <span>?</span>
        </button>
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
        {helpOpen && (
          <div className="help-panel" role="dialog" aria-label="Nápověda a kontakt">
            <button className="help-panel__close" type="button" aria-label="Zavřít nápovědu" onClick={() => setHelpOpen(false)}>
              <X size={17} />
            </button>
            <strong>Potřebujete pomoc?</strong>
            <p>
              Máte požadavek nebo jste narazili na problém? Ozvěte se nám na Instagramu{" "}
              <a href="https://instagram.com/honza_proky7" target="_blank" rel="noreferrer">@honza_proky7</a>.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
