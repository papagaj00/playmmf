function parseScore(result) {
    if (!/^\s*\d+\s*:\s*\d+\s*$/.test(result || "")) return null;
    return result.split(":").map((score) => Number(score.trim()));
}

export function getGroupResults(markets, teamNames) {
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
            const orderedOutcomes = [...market.outcomes].sort((left, right) => left.id - right.id);
            const first = orderedOutcomes.find((outcome) => teams[outcome.name]);
            const second = orderedOutcomes.find((outcome) => teams[outcome.name] && outcome !== first);
            const score = parseScore(market.result);
            if (!first || !second || first.team_id === second.team_id || !score) return;

            const [firstScore, secondScore] = score;
            saveResult(first.name, second.name, `${firstScore}:${secondScore}`);
            saveResult(second.name, first.name, `${secondScore}:${firstScore}`);
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