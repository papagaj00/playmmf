import { useState } from "react";
import LoadingState from "./LoadingState";
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
        teams[first.name].points += 3;
      } else {
        teams[second.name].points += 3;
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

export default function TournamentView({ markets, loading }) {
  const [openGroups, setOpenGroups] = useState({ "Skupina A": false, "Skupina B": false });
  const [playoffsOpen, setPlayoffsOpen] = useState(false);

  if (loading) return <LoadingState label="Načítám turnaj…" />;

  return (
    <div className="tournament-view">
      <h2 className="section-title tournament-title">Turnaj</h2>
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
