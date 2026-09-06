"""The daily puzzle cache.

What matters here is not the hit rate -- that part is easy -- but the two ways a
cache serves something wrong: past the date rollover, and after an operator has
deliberately changed the puzzle. Both are tested with a controlled clock rather
than by sleeping.
"""

import threading

import pytest
from daily_cache import DEFAULT_TTL_SECONDS, PuzzleCache


class FakeClock:
    """A monotonic clock that only moves when told to."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def cache(clock):
    return PuzzleCache(ttl_seconds=60, clock=clock)


PUZZLE = ("Bob Lanier", ["Detroit Pistons", "Milwaukee Bucks"], "laniebo01")


class TestHitsAndMisses:
    def test_an_empty_cache_misses(self, cache):
        assert cache.get("2026-09-05") is None

    def test_a_stored_puzzle_comes_back(self, cache):
        cache.put("2026-09-05", PUZZLE)
        assert cache.get("2026-09-05") == PUZZLE

    def test_the_same_puzzle_serves_many_reads(self, cache):
        cache.put("2026-09-05", PUZZLE)
        for _ in range(100):
            assert cache.get("2026-09-05") == PUZZLE
        assert cache.stats()["hits"] == 100
        # One database read served a hundred requests, which is the point.
        assert cache.stats()["misses"] == 0


class TestExpiry:
    def test_it_holds_the_puzzle_up_to_the_ttl(self, cache, clock):
        cache.put("2026-09-05", PUZZLE)
        clock.advance(59)
        assert cache.get("2026-09-05") == PUZZLE

    def test_it_misses_once_the_ttl_has_passed(self, cache, clock):
        cache.put("2026-09-05", PUZZLE)
        clock.advance(60)
        assert cache.get("2026-09-05") is None

    def test_an_expired_entry_is_dropped_not_merely_ignored(self, cache, clock):
        # Otherwise a long-idle instance holds a day-old puzzle in memory and
        # the next stats read reports it as cached.
        cache.put("2026-09-05", PUZZLE)
        clock.advance(120)
        cache.get("2026-09-05")
        assert cache.stats()["cached_date"] is None


class TestTheDateRollover:
    def test_a_new_date_misses_even_within_the_ttl(self, cache, clock):
        # Midnight ET is the case this exists for: the TTL has not expired, but
        # yesterday's puzzle must not be served today.
        cache.put("2026-09-05", PUZZLE)
        clock.advance(1)
        assert cache.get("2026-09-06") is None

    def test_storing_a_new_date_replaces_the_old_one(self, cache):
        cache.put("2026-09-05", PUZZLE)
        cache.put("2026-09-06", ("Dwight Jones", ["Atlanta Hawks", "Chicago Bulls"], "jonesdw01"))
        assert cache.get("2026-09-05") is None
        assert cache.get("2026-09-06")[0] == "Dwight Jones"


class TestInvalidation:
    def test_invalidate_forgets_the_puzzle(self, cache):
        cache.put("2026-09-05", PUZZLE)
        cache.invalidate()
        assert cache.get("2026-09-05") is None

    def test_a_swapped_puzzle_is_picked_up_after_the_ttl(self, cache, clock):
        # This is the bound that lets an admin swap work without distributed
        # invalidation: an instance that did not perform the swap is wrong for
        # at most one TTL.
        cache.put("2026-09-05", PUZZLE)
        clock.advance(DEFAULT_TTL_SECONDS)
        assert cache.get("2026-09-05") is None


class TestConcurrency:
    def test_parallel_readers_agree(self, cache):
        cache.put("2026-09-05", PUZZLE)
        seen = []
        barrier = threading.Barrier(16)

        def read():
            barrier.wait()
            seen.append(cache.get("2026-09-05"))

        threads = [threading.Thread(target=read) for _ in range(16)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert seen == [PUZZLE] * 16
        assert cache.stats()["hits"] == 16

    def test_counters_are_not_lost_under_contention(self, cache):
        # Unlocked += on two counters from many threads loses increments, and a
        # hit rate that undercounts is worse than none: it reads as a cache that
        # is not working.
        barrier = threading.Barrier(8)

        def churn():
            barrier.wait()
            for _ in range(200):
                cache.get("2026-09-05")

        threads = [threading.Thread(target=churn) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        stats = cache.stats()
        assert stats["hits"] + stats["misses"] == 8 * 200


class TestStats:
    def test_hit_rate_is_none_before_any_read(self, cache):
        assert cache.stats()["hit_rate"] is None

    def test_hit_rate_reports_the_proportion_served_from_memory(self, cache):
        cache.get("2026-09-05")
        cache.put("2026-09-05", PUZZLE)
        cache.get("2026-09-05")
        cache.get("2026-09-05")
        cache.get("2026-09-05")
        assert cache.stats() == {
            "hits": 3,
            "misses": 1,
            "hit_rate": 0.75,
            "cached_date": "2026-09-05",
            "ttl_seconds": 60,
        }


class TestReset:
    def test_reset_clears_the_counters_as_well_as_the_value(self, cache):
        cache.put("2026-09-05", PUZZLE)
        cache.get("2026-09-05")
        cache.reset()
        assert cache.stats() == {
            "hits": 0,
            "misses": 0,
            "hit_rate": None,
            "cached_date": None,
            "ttl_seconds": 60,
        }

    def test_invalidate_leaves_the_counters_alone(self, cache):
        # An operator swapping a puzzle should not also zero the hit rate
        # somebody may be watching.
        cache.put("2026-09-05", PUZZLE)
        cache.get("2026-09-05")
        cache.invalidate()
        assert cache.stats()["hits"] == 1
