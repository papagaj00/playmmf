import { useCallback, useEffect, useState } from "react";
import { Bell, ChevronDown, LogOut, MessageSquareText, Send, X } from "lucide-react";
import { api } from "../api";
import { formatPoints } from "../format";

function isIOSDevice() {
  if (typeof navigator === "undefined") return false;
  return /iPhone|iPad|iPod/.test(navigator.userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

function supportsPushNotifications() {
  if (typeof window === "undefined" || !window.isSecureContext) return false;
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) return false;
  if (!isIOSDevice()) return true;
  return navigator.standalone === true || window.matchMedia?.("(display-mode: standalone)").matches === true;
}

export default function TopBar({ username, balance, onLogout, isAdmin }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [messageText, setMessageText] = useState("");
  const [messageError, setMessageError] = useState("");
  const [messageBusy, setMessageBusy] = useState(false);
  const [pushSupported] = useState(supportsPushNotifications);
  const [pushEnabled, setPushEnabled] = useState(false);
  const [pushConfigured, setPushConfigured] = useState(false);
  const [pushPublicKey, setPushPublicKey] = useState("");
  const [pushDialogMode, setPushDialogMode] = useState(null);
  const [pushBusy, setPushBusy] = useState(false);
  const [pushError, setPushError] = useState("");
  const [pushStatusError, setPushStatusError] = useState(false);
  const [pushPermission, setPushPermission] = useState(() => (
    typeof Notification === "undefined" ? "unsupported" : Notification.permission
  ));
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

  useEffect(() => {
    let active = true;
    Promise.all([
      api.getPushStatus(),
      api.getPushPublicKey().catch(() => ({ public_key: "" })),
    ]).then(([status, key]) => {
      if (!active) return;
      setPushEnabled(status.enabled);
      setPushPublicKey(key.public_key || "");
      setPushConfigured(status.configured && Boolean(key.public_key));
      setPushStatusError(false);
    }).catch(() => {
      if (active) setPushStatusError(true);
    });
    return () => {
      active = false;
    };
  }, [username]);

  function base64ToBytes(value) {
    const padding = "=".repeat((4 - (value.length % 4)) % 4);
    const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
    return Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
  }

  function closePushDialog() {
    setPushDialogMode(null);
    setPushError("");
  }

  async function enablePush() {
    if (!pushSupported || !pushConfigured || !pushPublicKey) return;
    if (Notification.permission === "denied") {
      setPushPermission("denied");
      return;
    }

    const permissionRequest = Notification.requestPermission();
    setPushBusy(true);
    setPushError("");
    try {
      const permission = await permissionRequest;
      setPushPermission(permission);
      if (permission !== "granted") {
        setPushError("Povolení upozornění nebylo uděleno.");
        return;
      }

      const registration = await navigator.serviceWorker.register("/sw.js");
      const existing = await registration.pushManager.getSubscription();
      if (existing) {
        const json = existing.toJSON();
        await api.subscribePush({ endpoint: json.endpoint, p256dh: json.keys.p256dh, auth: json.keys.auth });
      } else {
        const subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: base64ToBytes(pushPublicKey),
        });
        const json = subscription.toJSON();
        await api.subscribePush({ endpoint: json.endpoint, p256dh: json.keys.p256dh, auth: json.keys.auth });
      }
      setPushEnabled(true);
      setPushDialogMode(null);
    } catch (error) {
      setPushError(error.message || "Upozornění se nepodařilo nastavit.");
    } finally {
      setPushBusy(false);
    }
  }

  async function disablePush() {
    setPushBusy(true);
    setPushError("");
    try {
      const registration = await navigator.serviceWorker.getRegistration("/");
      const existing = await registration?.pushManager.getSubscription();
      if (!existing) throw new Error("Aktivní předplatné v tomto prohlížeči nebylo nalezeno.");
      const json = existing.toJSON();
      await api.unsubscribePush({ endpoint: json.endpoint, p256dh: json.keys.p256dh, auth: json.keys.auth });
      await existing.unsubscribe();
      setPushEnabled(false);
    } catch (error) {
      setPushError(error.message || "Upozornění se nepodařilo vypnout.");
      setPushDialogMode("settings");
    } finally {
      setPushBusy(false);
    }
  }

  function openPushSettings() {
    setPushError("");
    setPushDialogMode("settings");
  }

  const pushCanEnable = pushSupported && pushConfigured && pushPermission !== "denied";
  const pushHelp = pushStatusError
    ? "Stav upozornění se nepodařilo načíst. Zkus to znovu později."
    : !pushConfigured
      ? "Upozornění zatím nejsou na serveru nakonfigurovaná. Informační zprávy a novinky uvidíš přímo v aplikaci."
      : !pushSupported
        ? "Push upozornění nejsou v tomto prohlížeči dostupná."
        : pushPermission === "denied"
          ? "Upozornění jsou v prohlížeči zablokovaná. Povol je v nastavení oprávnění tohoto webu a pak to zkus znovu."
          : "Dostaneš upozornění na nové zápasy a důležité informační zprávy.";

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
        <button
          className="push-button"
          type="button"
          aria-label="Nastavení upozornění"
          title="Nastavení upozornění"
          aria-expanded={Boolean(pushDialogMode)}
          onClick={openPushSettings}
        >
          <Bell size={18} />
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
        {pushDialogMode && (
          <div className="push-onboarding-layer" role="presentation">
            <button className="push-onboarding-scrim" type="button" aria-label="Zavřít upozornění" onClick={closePushDialog} />
            <section className="push-onboarding" role="dialog" aria-modal="true" aria-labelledby="push-onboarding-title">
              <button className="push-onboarding__close" type="button" aria-label="Zavřít" onClick={closePushDialog}><X size={18} /></button>
              <span className="push-onboarding__icon"><Bell size={22} /></span>
              <h2 id="push-onboarding-title">Upozornění PlayMMF</h2>
              <p>{pushHelp}</p>
              {pushError && <p className="push-error">{pushError}</p>}
              <div className="push-onboarding__actions">
                {pushCanEnable && !pushEnabled && (
                  <button className="push-onboarding__enable" type="button" onClick={enablePush} disabled={pushBusy}>
                    <Bell size={16} /> {pushBusy ? "Nastavuji…" : "Povolit upozornění"}
                  </button>
                )}
                {pushEnabled && pushSupported && (
                  <button className="push-onboarding__enable" type="button" onClick={disablePush} disabled={pushBusy}>
                    {pushBusy ? "Vypínám…" : "Vypnout upozornění"}
                  </button>
                )}
                <button className="push-onboarding__dismiss" type="button" onClick={closePushDialog}>
                  Zavřít
                </button>
              </div>
            </section>
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
