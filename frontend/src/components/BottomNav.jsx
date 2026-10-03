import { Goal, Medal, Shield, Trophy, Wallet } from "lucide-react";

const ITEMS = [
    { id: "markets", label: "Zápasy", Icon: Goal },
    { id: "portfolio", label: "Moje sázky", Icon: Wallet },
    { id: "leaderboard", label: "Žebříček", Icon: Medal },
    { id: "tournament", label: "Turnaj", Icon: Trophy },
    { id: "admin", label: "Správa", Icon: Shield },
];

export default function BottomNav({ tab, onChange, isAdmin }) {
    const visibleItems = isAdmin ? ITEMS : ITEMS.filter((item) => item.id !== "admin");

    return (
        <nav className="bottom-nav" style={{ "--nav-items": visibleItems.length }} aria-label="Hlavní navigace">
            {visibleItems.map(({ id, label, Icon }) => (
                <button
                    key={id}
                    className={tab === id ? "active" : ""}
                    onClick={() => onChange(id)}
                    aria-current={tab === id ? "page" : undefined}
                >
                    <Icon size={21} strokeWidth={2} />
                    <span>{label}</span>
                </button>
            ))}
        </nav>
    );
}
