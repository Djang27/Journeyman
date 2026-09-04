"""The conference map behind the hint badge.

This is the only copy -- team_list.js used to hold one too, but deriving the
hint in the browser required the client to hold the answer, so the frontend copy
went with the switch to the session API.

What still has to hold is coverage: the server must know a conference for every
team the frontend's autocomplete will accept.
"""

import json
import re
from pathlib import Path

from teams import CONFERENCES, conference

FRONTEND = Path(__file__).parents[2] / "frontend" / "src" / "components" / "team_list.js"


class TestConferenceMap:
    def test_covers_every_team_the_frontend_offers(self):
        source = FRONTEND.read_text()
        listed = re.search(r"const NBA_TEAMS = \[(.*?)\]", source, re.S).group(1)
        teams = set(json.loads("[" + listed.replace("\n", " ") + "]"))
        assert teams <= set(CONFERENCES), teams - set(CONFERENCES)


class TestConference:
    def test_the_frontend_no_longer_holds_a_copy(self):
        """A second copy would drift, and would mean the client had the answer."""
        assert "const CONFERENCE" not in FRONTEND.read_text()

    def test_looks_up_a_known_team(self):
        assert conference("boston celtics") == "East"
        assert conference("utah jazz") == "West"

    def test_is_case_and_whitespace_insensitive(self):
        assert conference("  Boston Celtics ") == "East"

    def test_unknown_teams_return_none(self):
        assert conference("springfield isotopes") is None

    def test_empty_input_returns_none(self):
        assert conference("") is None
        assert conference(None) is None

    def test_relocated_franchises_are_all_present(self):
        # The pairs most likely to be missed when the map is edited by hand.
        for team in (
            "seattle supersonics",
            "oklahoma city thunder",
            "vancouver grizzlies",
            "memphis grizzlies",
            "new jersey nets",
            "brooklyn nets",
            "washington bullets",
            "washington wizards",
            "charlotte bobcats",
            "charlotte hornets",
            "new orleans hornets",
        ):
            assert conference(team) is not None, team
