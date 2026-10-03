export const TEAM_LOGOS = {
  "3A": "/team-logos/3A.png",
  "Gladiators 4B (A)": "/team-logos/4B.jpg",
  "Gladiators 4B (B)": "/team-logos/4B.jpg",
  "FC Gooners 4A": "/team-logos/4A.jpeg",
  "FC Bumass 7A8": "/team-logos/7A8.jpeg",
  "FC Alpacas 2A": "/team-logos/2A.jpeg",
  "FC Tortas 2B": "/team-logos/2B.jpeg",
  "6B8": "/team-logos/6B8.jpeg",
  "AC Bez Práce 6A8": "/team-logos/6A8.png",
  "FC Bohové 1B": "/team-logos/1B.png",
  "FC Bang Bros 1A": "/team-logos/1A.jpeg",
  "FC Fibula 5A8": "/team-logos/5A8.jpeg",
  "FC Six Seven 5B8": "/team-logos/5B8.jpeg",
  "8A8": "/team-logos/8A8.png",
};

export function teamInitials(name) {
  return name
    .replace(/^FC |^AC /, "")
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 3)
    .toUpperCase();
}
