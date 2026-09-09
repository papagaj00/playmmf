import { Goal, Shield, Trophy, Wallet } from "lucide-react";

const ITEMS = [
    { id: "markets", label: "Zápasy", Icon: Goal },
    { id: "portfolio", label: "Sázky", Icon: Wallet },
    { id: "leaderboard", label: "Žebříček", Icon: Trophy },
    { id: "admin", label: "Správa", Icon: Shield },
];

export default function BottomNav({ tab, onChange }) {
    return (
        <nav className="bottom-nav" aria-label="Hlavní navigace">
            {ITEMS.map(({ id, label, Icon }) => (
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
