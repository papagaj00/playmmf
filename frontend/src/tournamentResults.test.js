import assert from "node:assert/strict";
import test from "node:test";
import { getGroupResults } from "./tournamentResults.js";

function resolvedMarket(outcomeNames, result) {
    return {
        stage: "group",
        status: "resolved",
        result,
        outcomes: outcomeNames.map((name, index) => ({ name, team_id: index + 1 })),
    };
}

test("group standings show scores and points from the first outcome's perspective", () => {
    const { teams, results } = getGroupResults(
        [resolvedMarket(["Team A", "Team B"], "3:1")],
        ["Team A", "Team B"],
    );

    assert.equal(results["Team A"]["Team B"], "3:1");
    assert.equal(results["Team B"]["Team A"], "1:3");
    assert.deepEqual(teams, [
        { name: "Team A", points: 3 },
        { name: "Team B", points: 0 },
    ]);
});

test("group standings preserve each team's perspective when outcomes are reversed", () => {
    const { teams, results } = getGroupResults(
        [resolvedMarket(["Team B", "Team A"], "1:3")],
        ["Team A", "Team B"],
    );

    assert.equal(results["Team A"]["Team B"], "3:1");
    assert.equal(results["Team B"]["Team A"], "1:3");
    assert.deepEqual(teams, [
        { name: "Team A", points: 3 },
        { name: "Team B", points: 0 },
    ]);
});

test("group draws award one point and show the same score from both perspectives", () => {
    const { teams, results } = getGroupResults(
        [resolvedMarket(["Team A", "Team B"], "2:2")],
        ["Team A", "Team B"],
    );

    assert.equal(results["Team A"]["Team B"], "2:2");
    assert.equal(results["Team B"]["Team A"], "2:2");
    assert.deepEqual(teams, [
        { name: "Team A", points: 1 },
        { name: "Team B", points: 1 },
    ]);
});