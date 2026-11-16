"""Ink estimates, the refill ledger, calibration, reminders and holds."""
from __future__ import annotations

import asyncio
import datetime as dt
import itertools

import numpy as np
import pytest
from fastapi.testclient import TestClient

from printmich.config import load_config
from printmich.ink import INK_KEYS, coverage, estimate_ml, marker_ink
from printmich.main import create_app
from printmich.store import now_utc


def page(color, size=(8, 8)):
    return np.full((*size, 3), color, np.uint8)


def test_white_paper_only_costs_cleaning():
    ml = estimate_ml(page((255, 255, 255)), 101.6, 152.4, matte=False)
    assert len(set(ml.values())) == 1  # every tank shares the cleaning
    assert 0.005 < ml["C"] < 0.015


def test_black_uses_the_right_black_for_the_paper():
    glossy = coverage(page((0, 0, 0)), matte=False)
    matte = coverage(page((0, 0, 0)), matte=True)
    assert glossy["PBK"] > 0.9 and glossy["MBK"] == 0 and glossy["CO"] > 0
    assert matte["MBK"] > 0.9 and matte["PBK"] == 0 and matte["CO"] == 0


def test_light_and_saturated_colors_pick_sensible_inks():
    pale_cyan = coverage(page((215, 245, 252)), matte=False)
    assert pale_cyan["PC"] > pale_cyan["C"]
    red = coverage(page((230, 20, 20)), matte=False)
    assert red["R"] > 0.3 and red["C"] < 0.05


def test_typical_4x6_matches_canon_yields():
    rng = np.random.default_rng(3)
    photo = rng.integers(40, 220, size=(120, 80, 3), dtype=np.uint8)
    total = sum(estimate_ml(photo, 101.6, 152.4, matte=False).values())
    assert 0.15 < total < 0.6  # Canon's yields work out to about 0.3 ml per 4×6
    assert sum(estimate_ml(photo, 101.6, 152.4, matte=False, copies=3).values()) == pytest.approx(total * 3, rel=1e-3)


@pytest.mark.parametrize(("name", "ink"), [("PBK", "PBK"), ("Photo Black", "PBK"), ("MBK · Matte Black", "MBK"),
                                           ("Photo Magenta", "PM"), ("Magenta", "M"), ("Chroma Optimizer", "CO"),
                                           ("Grey ink", "GY"), ("Red", "R")])
def test_marker_names(name, ink):
    assert marker_ink(name) == ink


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("PRINTMICH_DATA", str(tmp_path / "config"))
    monkeypatch.setenv("PRINTMICH_STATIC", str(tmp_path / "no-ui"))
    monkeypatch.setenv("PRINTER_URI", "virtual://pro-310")
    for var in ("IMMICH_URL", "IMMICH_API_KEY", "PRINTMICH_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    with TestClient(create_app(load_config())) as c:
        yield c


_seconds = itertools.count(1)


def _backdate_ledger(pm, hours: float = 1) -> None:
    """Move every ink log entry back in time, so test prints can land between entries."""
    for e in pm.store.ink_events(1000):
        at = (dt.datetime.fromisoformat(e["at"]) - dt.timedelta(hours=hours)).isoformat(timespec="seconds")
        pm.db.execute("UPDATE ink_events SET at = ? WHERE id = ?", (at, e["id"]))


def _fake_print(pm, ml_each: float, *, ago_minutes: float = 30) -> None:
    """A completed print, ago_minutes before now (negative = in the future), each one a second apart."""
    when = (now_utc() - dt.timedelta(minutes=ago_minutes) + dt.timedelta(seconds=next(_seconds)))
    when = when.isoformat(timespec="seconds")
    pm.store.add_print({"id": f"p{pm.db.scalar('SELECT COUNT(*) FROM prints')}", "status": "completed",
                        "printer": "virtual://pro-310", "completed_at": when,
                        "ink": dict.fromkeys(INK_KEYS, ml_each), "source": "manual"})


def test_ledger_refill_and_calibration(app):
    pm = app.app.state.pm
    app.put("/api/settings", json={"ink": {"levels": "estimate", "remind_below": 20, "hold_below": 5}})
    state = app.post("/api/ink/start", json={"from": "full"}).json()
    assert all(t["percent"] == 100 for t in state["tanks"])
    _backdate_ledger(pm)

    for _ in range(4):
        _fake_print(pm, 1.0)  # 4 ml estimated from each tank
    cyan = next(t for t in app.get("/api/ink").json()["tanks"] if t["ink"] == "C")
    assert cyan["level_ml"] == pytest.approx(10.4, abs=0.01)
    assert cyan["prints"] == 4

    # Refilling cyan took 6 ml, so the estimate was 1.5× too low.
    state = app.post("/api/ink/refill", json={"inks": ["C"], "added_ml": {"C": 6}}).json()
    cyan = next(t for t in state["tanks"] if t["ink"] == "C")
    assert cyan["percent"] == 100
    assert cyan["factor"] == pytest.approx(1.5, abs=0.01)
    _fake_print(pm, 1.0, ago_minutes=-1)  # printed after the refill
    cyan = next(t for t in app.get("/api/ink").json()["tanks"] if t["ink"] == "C")
    assert cyan["level_ml"] == pytest.approx(14.4 - 1.5, abs=0.01)


def test_reminders_and_holds(app):
    pm = app.app.state.pm
    sent = []

    async def fake_send(title, body, **kw):
        sent.append(title)
        return True

    pm.notifier.send = fake_send
    app.put("/api/settings", json={"ink": {"levels": "estimate", "remind_below": 25, "hold_below": 5}})
    app.post("/api/ink/start", json={"from": "full"})
    _backdate_ledger(pm)
    for _ in range(11):
        _fake_print(pm, 1.0)  # 3.4 ml left, about 24%
    asyncio.run(pm.ink.check(force=True))
    assert sent == ["Printmich: refill ink soon"]
    asyncio.run(pm.ink.check(force=True))
    assert len(sent) == 1  # only once per refill

    assert pm.ink.hold_reason(dict.fromkeys(INK_KEYS, 0.1)) is None
    reason = pm.ink.hold_reason(dict.fromkeys(INK_KEYS, 3.0))
    assert reason and "Cyan" in reason

    # Printer-reported ink warnings are hidden while estimating; the estimate is attached instead.
    st = pm.ink.decorate({"configured": True, "reasons": [
        {"base": "marker-supply-low", "severity": "warning"}, {"base": "media-empty", "severity": "error"}]})
    assert [r["base"] for r in st["reasons"]] == ["media-empty"]
    assert st["ink"]["tracking"] is True


def test_print_records_its_ink(app):
    pid = app.post("/api/tools/chart", json={"preset_id": "p-daily-4x6"}).json()["id"]
    import time
    for _ in range(120):
        p = app.get(f"/api/prints/{pid}").json()
        if p["status"] in ("completed", "failed"):
            break
        time.sleep(0.5)
    assert p["status"] == "completed"
    assert set(p["ink"]) == set(INK_KEYS)
    assert 0.1 < sum(p["ink"].values()) < 1.0
