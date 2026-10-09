import assert from "node:assert/strict";
import test from "node:test";
import { getGroupResults } from "./tournamentResults.js";

function resolvedMarket(outcomes, result) {
    return {
        stage: "group",
        status: "resolved",
        result,
        outcomes,
    };
}

test("group standings show scores and points from the first outcome's perspective", () => {
    const { teams, results } = getGroupResults(
        [resolvedMarket([
            { id: 1, name: "Team A", team_id: 1 },
            { id: 2, name: "Team B", team_id: 2 },
        ], "3:1")],
        ["Team A", "Team B"],
    );

    assert.equal(results["Team A"]["Team B"], "3:1");
    assert.equal(results["Team B"]["Team A"], "1:3");
    assert.deepEqual(teams, [
        { name: "Team A", points: 3 },
        { name: "Team B", points: 0 },
    ]);
});

test("group standings use outcome ID order when the API array is reversed", () => {
    const { teams, results } = getGroupResults(
        [resolvedMarket([
            { id: 2, name: "Team B", team_id: 2 },
            { id: 1, name: "Team A", team_id: 1 },
        ], "3:1")],
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
        [resolvedMarket([
            { id: 1, name: "Team A", team_id: 1 },
            { id: 2, name: "Team B", team_id: 2 },
        ], "2:2")],
        ["Team A", "Team B"],
    );

    assert.equal(results["Team A"]["Team B"], "2:2");
    assert.equal(results["Team B"]["Team A"], "2:2");
    assert.deepEqual(teams, [
        { name: "Team A", points: 1 },
        { name: "Team B", points: 1 },
    ]);
});