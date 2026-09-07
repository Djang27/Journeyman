"""The archive query, which grows by one row a day.

PostgREST caps a response at 1000 rows and says nothing about it. The scheduler
only ever asks for ninety days, so this was invisible -- but the archive asks
for launch-to-yesterday, and would have started silently losing its oldest
puzzles somewhere in the third year, with no error anywhere.
"""

from puzzles_repo import PuzzlesRepo


class FakeTable:
    """Enough PostgREST to answer a paged range query."""

    def __init__(self, rows, page_size):
        self._rows = rows
        self._page_size = page_size
        self.ranges = []
        self._start = None
        self._end = None

    def select(self, *_):
        return self

    def eq(self, *_):
        return self

    def gte(self, _, value):
        self._start = value
        return self

    def lte(self, _, value):
        self._end = value
        return self

    def order(self, *_, **__):
        return self

    def range(self, start, end):
        self.ranges.append((start, end))
        self._slice = (start, end)
        return self

    def execute(self):
        start, end = self._slice
        window = [r for r in self._rows if self._start <= r["puzzle_date"] <= self._end]
        page = window[start : end + 1]
        # A real response never exceeds the cap, however wide the range asked.
        return type("R", (), {"data": page[: self._page_size]})()


class FakeClient:
    def __init__(self, rows, page_size=1000):
        self.table_obj = FakeTable(rows, page_size)

    def table(self, _):
        return self.table_obj


def dated_rows(n, first_day=1):
    """n consecutive daily puzzles, as dates PostgREST would return."""
    from datetime import date, timedelta

    start = date(2020, 1, 1)
    return [
        {
            "puzzle_date": (start + timedelta(days=first_day + i)).isoformat(),
            "player_id": f"p{i}",
            "payload": {"player_name": f"Player {i}"},
        }
        for i in range(n)
    ]


class TestPaging:
    def test_a_small_range_takes_one_request(self):
        client = FakeClient(dated_rows(90))
        repo = PuzzlesRepo(client)
        rows = repo.scheduled_between("2020-01-01", "2030-01-01")
        assert len(rows) == 90
        assert len(client.table_obj.ranges) == 1

    def test_exactly_one_page_does_not_ask_for_a_second(self):
        # The boundary: a full page could mean "there is more" or "that is all",
        # and asking again for nothing is a wasted round trip on every call.
        client = FakeClient(dated_rows(999))
        repo = PuzzlesRepo(client)
        assert len(repo.scheduled_between("2020-01-01", "2030-01-01")) == 999
        assert len(client.table_obj.ranges) == 1

    def test_a_full_page_is_followed_up(self):
        client = FakeClient(dated_rows(1000))
        repo = PuzzlesRepo(client)
        assert len(repo.scheduled_between("2020-01-01", "2030-01-01")) == 1000
        assert len(client.table_obj.ranges) == 2

    def test_more_than_the_cap_is_not_silently_truncated(self):
        """The failure this exists for.

        Unpaged, this returned 1000 and looked like the whole answer -- so the
        oldest puzzles would have vanished from the archive with nothing
        reporting anything.
        """
        client = FakeClient(dated_rows(2400))
        repo = PuzzlesRepo(client)
        rows = repo.scheduled_between("2020-01-01", "2030-01-01")
        assert len(rows) == 2400
        assert len(client.table_obj.ranges) == 3

    def test_the_oldest_puzzle_survives_paging(self):
        # Losing rows off either end would still pass a count check on a fake
        # that returned duplicates, so this names the row that used to vanish.
        rows = dated_rows(2400)
        repo = PuzzlesRepo(FakeClient(rows))
        result = repo.scheduled_between("2020-01-01", "2030-01-01")
        assert rows[0]["puzzle_date"] in result
        assert rows[-1]["puzzle_date"] in result

    def test_the_range_is_still_honoured(self):
        repo = PuzzlesRepo(FakeClient(dated_rows(2400)))
        result = repo.scheduled_between("2020-06-01", "2020-06-30")
        assert len(result) == 30
        assert all(d.startswith("2020-06") for d in result)

    def test_an_empty_range_is_no_rows_rather_than_an_error(self):
        repo = PuzzlesRepo(FakeClient(dated_rows(100)))
        assert repo.scheduled_between("2030-01-01", "2030-12-31") == {}
