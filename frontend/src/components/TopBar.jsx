import { useCallback, useEffect, useState } from "react";
import { ChevronDown, LogOut, MessageSquareText, Send, X } from "lucide-react";
import { api } from "../api";
import { formatPoints } from "../format";

export default function TopBar({ username, balance, onLogout, isAdmin }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [messageText, setMessageText] = useState("");
  const [messageError, setMessageError] = useState("");
  const [messageBusy, setMessageBusy] = useState(false);
  const readStorageKey = `gbn-info-read:${username}`;
  const [lastReadId, setLastReadId] = useState(() => Number(localStorage.getItem(readStorageKey) || 0));

  const markMessagesRead = useCallback((nextMessages) => {
    const newestId = nextMessages[0]?.id || 0;
    if (newestId <= lastReadId) return;
    localStorage.setItem(readStorageKey, String(newestId));
    setLastReadId(newestId);
  }, [lastReadId, readStorageKey]);

  useEffect(() => {
    let active = true;
    async function loadMessages() {
      try {
        const nextMessages = await api.getInfoMessages();
        if (!active) return;
        setMessages(nextMessages);
        if (infoOpen) markMessagesRead(nextMessages);
      } catch {
        if (active) setMessageError("Zprávy se nepodařilo načíst.");
      }
    }
    loadMessages();
    const interval = setInterval(loadMessages, 15000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [infoOpen, markMessagesRead, username]);

  async function handleSendMessage(event) {
    event.preventDefault();
    if (!messageText.trim()) return;
    setMessageBusy(true);
    setMessageError("");
    try {
      const created = await api.createInfoMessage(messageText);
      setMessages((current) => [created, ...current]);
      markMessagesRead([created]);
      setMessageText("");
    } catch (error) {
      setMessageError(error.message || "Zprávu se nepodařilo odeslat.");
    } finally {
      setMessageBusy(false);
    }
  }

  return (
    <div className="topbar">
      <div className="topbar__brand">
        <img src="/playmmf-logo.svg" alt="PlayMMF" />
        <span>PlayMMF</span>
      </div>
      <div className="topbar__right">
        <button
          className="help-button"
          type="button"
          aria-label="Informační zprávy"
          aria-expanded={infoOpen}
          onClick={() => setInfoOpen((open) => !open)}
        >
          <MessageSquareText size={18} />
          {messages[0]?.id > lastReadId && <span className="info-unread-dot" aria-label="Nové informační zprávy" />}
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
        {infoOpen && (
          <div className="help-panel info-panel" role="dialog" aria-label="Informační zprávy">
            <button className="help-panel__close" type="button" aria-label="Zavřít informační zprávy" onClick={() => setInfoOpen(false)}>
              <X size={17} />
            </button>
            <strong>Informace</strong>
            <div className="info-message-list">
              {messages.length === 0 && !messageError && <p>Žádné zprávy.</p>}
              {messages.map((message) => (
                <article className="info-message" key={message.id}>
                  <time dateTime={message.created_at}>{new Date(message.created_at).toLocaleString("cs-CZ")}</time>
                  <p>{message.text}</p>
                </article>
              ))}
            </div>
            {messageError && <p className="info-message-error">{messageError}</p>}
            {isAdmin && (
              <form className="info-message-form" onSubmit={handleSendMessage}>
                <textarea
                  value={messageText}
                  onChange={(event) => setMessageText(event.target.value)}
                  placeholder="Zpráva pro všechny hráče"
                  maxLength={2000}
                  rows={3}
                />
                <button className="btn-small" type="submit" disabled={messageBusy || !messageText.trim()}>
                  <Send size={14} /> {messageBusy ? "Odesílám…" : "Odeslat všem"}
                </button>
              </form>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
