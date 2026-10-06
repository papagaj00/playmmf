import { useState } from "react";
import LoadingState from "./LoadingState";
import { api } from "../api";
import { TEAM_LOGOS, teamInitials } from "../teamLogos";

const GROUPS = {
    "Skupina A": ["3A", "FC Gooners 4A", "6B8", "FC Bumass 7A8", "FC Alpacas 2A", "FC Fibula 5A8", "FC Tortas 2B"],
    "Skupina B": ["Gladiators 4B (A)", "Gladiators 4B (B)", "8A8", "FC Six Seven 5B8", "FC Bang Bros 1A", "FC Bohové 1B", "AC Bez Práce 6A8"],
};

const PLAYOFF_STAGES = [
    ["quarterfinal", "Čtvrtfinále"],
    ["semifinal", "Semifinále"],
    ["third_place", "O 3. místo"],
    ["final", "Finále"],
];

function parseScore(result) {
    if (!/^\s*\d+\s*:\s*\d+\s*$/.test(result || "")) return null;
    return result.split(":").map((score) => Number(score.trim()));
}

function getGroupResults(markets, teamNames) {
    const teams = Object.fromEntries(teamNames.map((name) => [name, { name, points: 0 }]));
    const results = {};
    const saveResult = (row, column, result) => {
        if (!results[row]) results[row] = {};
        results[row][column] = result;
    };

    markets
        .filter((market) => market.stage === "group" && market.status === "resolved")
        .forEach((market) => {
            if (market.outcomes.length !== 2) return;
            const first = market.outcomes.find((outcome) => teams[outcome.name]);
            const second = market.outcomes.find((outcome) => teams[outcome.name] && outcome !== first);
            const score = parseScore(market.result);
            if (!first || !second || first.team_id === second.team_id || !score) return;

            const [firstScore, secondScore] = score;
            saveResult(first.name, second.name, `${secondScore}:${firstScore}`);
            saveResult(second.name, first.name, `${firstScore}:${secondScore}`);
            if (firstScore === secondScore) {
                teams[first.name].points += 1;
                teams[second.name].points += 1;
            } else if (firstScore > secondScore) {
                teams[second.name].points += 3;
            } else {
                teams[first.name].points += 3;
            }
        });

    return { teams: teamNames.map((name) => teams[name]), results };
}

function TeamMark({ name }) {
    const logo = TEAM_LOGOS[name];
    const variant = name.endsWith("(A)") ? "A" : name.endsWith("(B)") ? "B" : null;
    return logo
        ? <span className="tournament-team-mark" title={name}><img className="tournament-team-logo" src={logo} alt={name} />{variant && <b className="tournament-team-variant">{variant}</b>}</span>
        : <span className="tournament-team-mark" title={name}><span className="tournament-team-logo tournament-team-logo--fallback">{teamInitials(name)}</span>{variant && <b className="tournament-team-variant">{variant}</b>}</span>;
}

function ResultsMatrix({ groupName, teams, results }) {
    return (
        <div className="standings-table-wrap">
            <table className="results-matrix">
                <thead>
                    <tr>
                        <th aria-label={`${groupName} týmy`} />
                        {teams.map((team) => <th key={team.name} title={team.name}><TeamMark name={team.name} /></th>)}
                        <th className="results-matrix__points">Body</th>
                    </tr>
                </thead>
                <tbody>
                    {teams.map((rowTeam) => (
                        <tr key={rowTeam.name}>
                            <th title={rowTeam.name}><TeamMark name={rowTeam.name} /></th>
                            {teams.map((columnTeam) => (
                                <td className={rowTeam.name === columnTeam.name ? "results-matrix__diagonal" : ""} key={columnTeam.name}>
                                    {rowTeam.name === columnTeam.name ? "" : results[rowTeam.name]?.[columnTeam.name] || "–"}
                                </td>
                            ))}
                            <td className="results-matrix__points">{rowTeam.points}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function GroupTable({ name, groupData, open, onToggle }) {
    return (
        <section className="tournament-section">
            <button className="tournament-section__toggle" type="button" onClick={onToggle} aria-expanded={open}>
                <span>{name}</span>
                <span className="tournament-section__arrow">{open ? "↑" : "↓"}</span>
            </button>
            {open && <ResultsMatrix groupName={name} teams={groupData.teams} results={groupData.results} />}
        </section>
    );
}

function PlayoffMatch({ market }) {
    const score = parseScore(market.result);
    return (
        <article className={`playoff-match playoff-match--${market.status}`}>
            <div className="playoff-match__meta">{market.status === "resolved" ? "Výsledek" : "Čeká na výsledek"}</div>
            {market.outcomes.slice(0, 2).map((outcome, index) => (
                <div className="playoff-team" key={outcome.id}>
                    <TeamMark name={outcome.name} />
                    <span>{outcome.name}</span>
                    {score && <strong>{score[index]}</strong>}
                </div>
            ))}
        </article>
    );
}

function PlayoffBracket({ markets, open, onToggle }) {
    const playoffMarkets = markets.filter((market) => market.stage !== "group");
    return (
        <section className="tournament-section tournament-section--playoffs">
            <button className="tournament-section__toggle" type="button" onClick={onToggle} aria-expanded={open}>
                <span>Play-off</span>
                <span className="tournament-section__arrow">{open ? "↑" : "↓"}</span>
            </button>
            {open && (
                <div className="playoff-bracket">
                    {PLAYOFF_STAGES.map(([stage, label]) => {
                        const stageMarkets = playoffMarkets.filter((market) => market.stage === stage);
                        return (
                            <div className={`playoff-round playoff-round--${stage}`} key={stage}>
                                <h3>{label}</h3>
                                {stageMarkets.length > 0
                                    ? stageMarkets.map((market) => <PlayoffMatch key={market.id} market={market} />)
                                    : <div className="playoff-empty">Zatím bez zápasu</div>}
                            </div>
                        );
                    })}
                </div>
            )}
        </section>
    );
}

function RosterPlayer({ teamId, player, isAdmin, onChange, onRemove, onError }) {
    const [goals, setGoals] = useState(player.goals);
    const [saving, setSaving] = useState(false);

    async function saveGoals() {
        const nextGoals = Math.max(0, Number(goals) || 0);
        if (nextGoals === player.goals) return;
        setSaving(true);
        try {
            const updated = await api.updateTeamPlayer(teamId, player.id, player.name, nextGoals);
            onChange(updated);
        } catch (error) {
            setGoals(player.goals);
            onError(error.message || "Góly se nepodařilo uložit.");
        } finally {
            setSaving(false);
        }
    }

    return (
        <div className="roster-player">
            <span className="roster-player__number">{player.sort_order + 1}</span>
            <span>{player.name}</span>
            {isAdmin ? (
                <input
                    className="roster-player__goals-input"
                    type="number"
                    min="0"
                    step="1"
                    value={goals}
                    aria-label={`Góly hráče ${player.name}`}
                    disabled={saving}
                    onChange={(event) => setGoals(event.target.value)}
                    onBlur={saveGoals}
                />
            ) : <strong>{player.goals} g</strong>}
            {isAdmin && (
                <button className="roster-player__delete" type="button" title={`Odebrat ${player.name}`} aria-label={`Odebrat ${player.name}`} onClick={() => onRemove(player)}>
                    ×
                </button>
            )}
        </div>
    );
}

function RosterPanel({ roster, isAdmin, onRosterChange }) {
    const [addOpen, setAddOpen] = useState(false);
    const [playerName, setPlayerName] = useState("");
    const [playerGoals, setPlayerGoals] = useState(0);
    const [error, setError] = useState("");
    if (!roster) return <div className="roster-empty">Vyber tým a zobrazí se jeho soupiska.</div>;
    const statusText = {
        pending: "Zatím nebyl vyhodnocen žádný zápas.",
        consistent: "Góly hráčů souhlasí s výsledky týmu.",
        mismatch: "Součet gólů hráčů nesouhlasí s výsledky týmu.",
    }[roster.goals_status];
    return (
        <div className="roster-panel">
            <div className="roster-panel__header">
                <TeamMark name={roster.name} />
                <div>
                    <h3>{roster.name}</h3>
                    <p>{roster.players.length} hráčů</p>
                </div>
                <div className={`roster-goals roster-goals--${roster.goals_status}`}>
                    <strong>{roster.roster_goals}</strong><span> / {roster.team_goals} gólů</span>
                </div>
                {isAdmin && <button className="roster-add-button" type="button" title="Přidat hráče" aria-label="Přidat hráče" onClick={() => setAddOpen((open) => !open)}>+</button>}
            </div>
            <div className={`roster-status roster-status--${roster.goals_status}`} role="status">{statusText}</div>
            {error && !addOpen && <div className="roster-panel__error" role="alert">{error}</div>}
            {isAdmin && addOpen && (
                <form className="roster-add-form" onSubmit={async (event) => {
                    event.preventDefault();
                    const name = playerName.trim();
                    if (!name) return setError("Zadej jméno hráče.");
                    try {
                        const player = await api.addTeamPlayer(roster.id, name, Math.max(0, Number(playerGoals) || 0));
                        onRosterChange({ ...roster, players: [...roster.players, player], roster_goals: roster.roster_goals + player.goals });
                        setPlayerName("");
                        setPlayerGoals(0);
                        setAddOpen(false);
                        setError("");
                    } catch (err) {
                        setError(err.message);
                    }
                }}>
                    <input value={playerName} onChange={(event) => setPlayerName(event.target.value)} placeholder="Jméno hráče" autoFocus />
                    <input type="number" min="0" step="1" value={playerGoals} onChange={(event) => setPlayerGoals(event.target.value)} aria-label="Počáteční góly" />
                    <button className="btn-small" type="submit">Přidat</button>
                    {error && <span className="roster-add-form__error">{error}</span>}
                </form>
            )}
            {roster.players.length === 0 ? (
                <div className="roster-empty">Soupiska zatím není vyplněná.</div>
            ) : (
                <div className="roster-player-list">
                    {roster.players.map((player) => <RosterPlayer key={player.id} teamId={roster.id} player={player} isAdmin={isAdmin} onError={setError} onChange={(updated) => onRosterChange({ ...roster, players: roster.players.map((item) => item.id === updated.id ? updated : item), roster_goals: roster.players.reduce((total, item) => total + (item.id === updated.id ? updated.goals : item.goals), 0) })} onRemove={async (removed) => {
                        if (!window.confirm(`Odebrat hráče ${removed.name} ze soupisky?`)) return;
                        try {
                            await api.deleteTeamPlayer(roster.id, removed.id);
                            onRosterChange({ ...roster, players: roster.players.filter((item) => item.id !== removed.id), roster_goals: roster.roster_goals - removed.goals });
                        } catch (err) {
                            setError(err.message);
                        }
                    }} />)}
                </div>
            )}
        </div>
    );
}

function RosterDirectory({ rosters, open, onToggle, selectedTeamId, onSelect, isAdmin, onRosterChange }) {
    const selectedRoster = rosters.find((roster) => roster.id === selectedTeamId);
    return (
        <section className="tournament-section tournament-section--rosters">
            <button className="tournament-section__toggle" type="button" onClick={onToggle} aria-expanded={open}>
                <span>Týmy</span>
                <span className="tournament-section__arrow">{open ? "↑" : "↓"}</span>
            </button>
            {open && (
                <div className="roster-directory">
                    <div className="roster-team-picker">
                        {rosters.map((roster) => (
                            <button
                                className={`roster-team-button ${selectedTeamId === roster.id ? "active" : ""}`}
                                type="button"
                                key={roster.id}
                                onClick={() => onSelect(roster.id)}
                            >
                                <TeamMark name={roster.name} />
                                <span>{roster.name}</span>
                            </button>
                        ))}
                    </div>
                    <RosterPanel roster={selectedRoster} isAdmin={isAdmin} onRosterChange={onRosterChange} />
                </div>
            )}
        </section>
    );
}

export default function TournamentView({ markets, rosters, loading, isAdmin, onRosterChange }) {
    const [openGroups, setOpenGroups] = useState({ "Skupina A": false, "Skupina B": false });
    const [playoffsOpen, setPlayoffsOpen] = useState(false);
    const [rosterDirectoryOpen, setRosterDirectoryOpen] = useState(false);
    const [selectedTeamId, setSelectedTeamId] = useState(null);

    if (loading) return <LoadingState label="Načítám turnaj…" />;

    return (
        <div className="tournament-view">
            <h2 className="section-title tournament-title">Turnaj</h2>
            <RosterDirectory
                rosters={rosters}
                open={rosterDirectoryOpen}
                selectedTeamId={selectedTeamId}
                onToggle={() => setRosterDirectoryOpen((open) => !open)}
                onSelect={setSelectedTeamId}
                isAdmin={isAdmin}
                onRosterChange={onRosterChange}
            />
            <div className="tournament-groups">
                {Object.entries(GROUPS).map(([name, teamNames]) => (
                    <GroupTable
                        key={name}
                        name={name}
                        groupData={getGroupResults(markets, teamNames)}
                        open={openGroups[name]}
                        onToggle={() => setOpenGroups((current) => ({ ...current, [name]: !current[name] }))}
                    />
                ))}
            </div>
            <PlayoffBracket markets={markets} open={playoffsOpen} onToggle={() => setPlayoffsOpen((open) => !open)} />
        </div>
    );
}
