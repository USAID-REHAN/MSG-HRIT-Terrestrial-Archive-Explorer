"""Minimal unit tests for sample selection time logic."""

from app.sampling.selector import closest_within_tolerance, time_to_minutes


class _T:
    def __init__(self, time: str, id: int = 0):
        self.time = time
        self.id = id


def test_time_to_minutes():
    assert time_to_minutes("09-00") == 9 * 60
    assert time_to_minutes("20:00") == 20 * 60


def test_closest_within_tolerance():
    cands = [_T("08-45", 1), _T("09-15", 2), _T("14-00", 3)]
    pick = closest_within_tolerance(cands, "09-00", 30)
    assert pick is not None
    assert pick.time == "08-45"

    none = closest_within_tolerance(cands, "03-00", 30)
    assert none is None
