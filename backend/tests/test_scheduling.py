from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from printmich.models import Schedule, Timing
from printmich.scheduler import cron_for, describe_timing, next_runs

NY = ZoneInfo("America/New_York")


def local(runs):
    return [r.astimezone(NY) for r in runs]


def test_daily_runs_at_local_time_across_dst():
    s = Schedule(timing=Timing(frequency="daily", time="08:00"))
    after = dt.datetime(2026, 10, 31, 12, 0, tzinfo=dt.UTC)  # DST ends Nov 1 in New York
    runs = local(next_runs(s, after, NY, 3))
    assert [r.day for r in runs] == [1, 2, 3]
    assert all((r.hour, r.minute) == (8, 0) for r in runs)
    assert runs[0].utcoffset() != dt.datetime(2026, 10, 31, 8, tzinfo=NY).utcoffset()


def test_weekly_uses_monday_based_weekdays():
    s = Schedule(timing=Timing(frequency="weekly", weekdays=[5], time="09:30"))  # Saturday
    assert cron_for(s) == "30 9 * * 6"
    after = dt.datetime(2026, 11, 16, 0, 0, tzinfo=dt.UTC)
    run = local(next_runs(s, after, NY))[0]
    assert run.weekday() == 5 and (run.hour, run.minute) == (9, 30)


def test_monthly_and_every_n_days():
    s = Schedule(timing=Timing(frequency="monthly", day_of_month=15, time="07:00"))
    run = local(next_runs(s, dt.datetime(2026, 11, 16, tzinfo=dt.UTC), NY))[0]
    assert (run.month, run.day, run.hour) == (12, 15, 7)

    s = Schedule(timing=Timing(frequency="every_n_days", every_n_days=3, time="20:00"),
                 last_run_at="2026-11-14T01:00:00+00:00")  # Nov 13, 8 pm New York
    runs = local(next_runs(s, dt.datetime(2026, 11, 16, 12, tzinfo=dt.UTC), NY, 2))
    assert [(r.month, r.day, r.hour) for r in runs] == [(11, 16, 20), (11, 19, 20)]


def test_invalid_cron_yields_no_runs():
    s = Schedule(timing=Timing(frequency="cron", cron="not a cron"))
    assert next_runs(s, dt.datetime.now(dt.UTC), NY) == []


def test_descriptions_read_naturally():
    assert describe_timing(Schedule(timing=Timing(frequency="daily", time="08:00"))).startswith("Every day")
