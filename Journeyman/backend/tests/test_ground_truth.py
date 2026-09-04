"""The ground-truth fixture and the scorer that uses it.

The fixture is filled in by hand, so most of what can go wrong is a typo or a
half-finished entry. These check the file stays usable, and that the scorer
distinguishes failure modes rather than just counting mismatches.
"""

import json

import pytest
from ground_truth import (
    GROUND_TRUTH_PATH,
    compare,
    format_report,
    load_ground_truth,
    score_source,
    verified_entries,
)
from teams import CONFERENCES

TRUTH = ["seattle supersonics", "phoenix suns", "boston celtics"]


class TestFixtureIsUsable:
    def test_it_parses(self):
        assert len(load_ground_truth()) >= 15

    def test_every_entry_has_what_the_scorer_needs(self):
        for entry in load_ground_truth():
            assert entry["name"]
            assert isinstance(entry["player_id"], int)
            assert entry["chosen_because"], f"{entry['name']} has no stated reason"

    def test_player_ids_are_unique(self):
        ids = [entry["player_id"] for entry in load_ground_truth()]
        assert len(ids) == len(set(ids))

    def test_every_team_named_is_one_the_game_knows(self):
        """A typo here would fail a source for the fixture's own mistake."""
        for entry in load_ground_truth():
            for team in (entry.get("verified_teams") or []) + entry["current_pool_teams"]:
                assert team in CONFERENCES, f"{entry['name']}: unknown team {team!r}"

    def test_a_verified_entry_carries_its_answer(self):
        for entry in load_ground_truth():
            if entry.get("verified"):
                assert entry.get("verified_teams"), f"{entry['name']} is verified but empty"

    def test_the_selection_covers_the_failure_modes_it_claims_to(self):
        """Guards the guard: 20 arbitrary players would prove nothing."""
        pool = [t for entry in load_ground_truth() for t in entry["current_pool_teams"]]
        for relocated in (
            "seattle supersonics",
            "vancouver grizzlies",
            "new jersey nets",
            "charlotte bobcats",
            "new orleans hornets",
        ):
            assert relocated in pool, f"no selected player covers {relocated}"

        returns = [
            e
            for e in load_ground_truth()
            if len(e["current_pool_teams"]) != len(set(e["current_pool_teams"]))
        ]
        assert len(returns) >= 4, "too few players who returned to a former team"

    def test_the_readme_survives_editing(self):
        with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
            assert json.load(f)["_readme"]


class TestCompare:
    def test_an_exact_match(self):
        assert compare(TRUTH, TRUTH)["match"] == "exact"

    def test_nulls_do_not_count_against_a_source(self):
        assert compare(TRUTH, TRUTH + [None])["match"] == "exact"

    def test_the_same_teams_in_the_wrong_order(self):
        """The Connie Hawkins signature: a mid-season trade interleaved."""
        assert compare(TRUTH, [TRUTH[1], TRUTH[0], TRUTH[2]])["match"] == "order"

    def test_a_dropped_return_is_reported_as_stints(self):
        expected = ["phoenix suns", "los angeles lakers", "phoenix suns"]
        assert compare(expected, ["phoenix suns", "los angeles lakers"])["match"] == "stints"

    def test_a_missing_franchise_is_wrong(self):
        outcome = compare(TRUTH, TRUTH[:2])
        assert outcome["match"] == "wrong"
        assert outcome["detail"]["missing"] == ["boston celtics"]

    def test_an_invented_franchise_is_wrong(self):
        outcome = compare(TRUTH, TRUTH + ["miami heat"])
        assert outcome["match"] == "wrong"
        assert outcome["detail"]["extra"] == ["miami heat"]

    def test_a_relocation_handled_as_the_modern_name_is_wrong(self):
        """Recording Seattle as Oklahoma City is the error most sources make."""
        outcome = compare(TRUTH, ["oklahoma city thunder", "phoenix suns", "boston celtics"])
        assert outcome["match"] == "wrong"
        assert "seattle supersonics" in outcome["detail"]["missing"]


class TestScoreSource:
    @pytest.fixture
    def truth_file(self, tmp_path):
        path = tmp_path / "truth.json"
        path.write_text(
            json.dumps(
                {
                    "_readme": ["test"],
                    "players": [
                        {
                            "player_id": 1,
                            "name": "Right",
                            "chosen_because": "x",
                            "current_pool_teams": TRUTH,
                            "verified_teams": TRUTH,
                            "verified": True,
                        },
                        {
                            "player_id": 2,
                            "name": "Wrong",
                            "chosen_because": "x",
                            "current_pool_teams": TRUTH,
                            "verified_teams": TRUTH,
                            "verified": True,
                        },
                        {
                            "player_id": 3,
                            "name": "Unverified",
                            "chosen_because": "x",
                            "current_pool_teams": TRUTH,
                            "verified_teams": None,
                            "verified": False,
                        },
                    ],
                }
            )
        )
        return path

    def test_unverified_entries_are_ignored(self, truth_file):
        assert len(verified_entries(truth_file)) == 2

    def test_a_perfect_source_scores_everything(self, truth_file):
        score = score_source(lambda _: TRUTH, truth_file)
        assert (score["exact"], score["total"]) == (2, 2)

    def test_failures_are_counted_by_kind(self, truth_file):
        score = score_source(lambda pid: TRUTH if pid == 1 else TRUTH[:1], truth_file)
        assert score["exact"] == 1
        assert score["by_failure"] == {"wrong": 1}

    def test_a_source_with_no_answer_is_recorded_as_absent(self, truth_file):
        score = score_source(lambda _: None, truth_file)
        assert score["by_failure"] == {"absent": 2}

    def test_a_source_that_raises_does_not_stop_the_run(self, truth_file):
        def explodes(pid):
            if pid == 1:
                raise RuntimeError("rate limited")
            return TRUTH

        score = score_source(explodes, truth_file)
        assert score["exact"] == 1
        assert score["by_failure"] == {"error": 1}

    def test_the_report_reads_as_a_summary(self, truth_file):
        report = format_report(score_source(lambda pid: TRUTH if pid == 1 else None, truth_file))
        assert "1/2 careers exactly correct" in report
        assert "Wrong" in report

    def test_an_empty_fixture_says_so_rather_than_claiming_success(self, tmp_path):
        path = tmp_path / "empty.json"
        path.write_text(json.dumps({"_readme": [], "players": []}))
        assert "No verified ground truth" in format_report(score_source(lambda _: TRUTH, path))
