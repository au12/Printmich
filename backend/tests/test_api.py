"""End-to-end API checks against the built-in virtual printer (no Immich needed)."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from printmich.config import load_config
from printmich.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PRINTMICH_DATA", str(tmp_path / "config"))
    monkeypatch.setenv("PRINTMICH_STATIC", str(tmp_path / "no-ui"))
    monkeypatch.setenv("PRINTER_URI", "virtual://pro-310")
    monkeypatch.setenv("TZ", "America/New_York")
    for var in ("IMMICH_URL", "IMMICH_API_KEY", "PRINTMICH_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    with TestClient(create_app(load_config())) as c:
        yield c


def test_health_and_defaults(client):
    assert client.get("/api/health").json()["ok"] is True
    presets = client.get("/api/presets").json()
    assert len(presets) >= 6
    assert all("·" not in p["name"] for p in presets)
    papers = {p["id"] for p in client.get("/api/papers").json()}
    assert {"canon-pt-101", "canon-pp-201", "canon-lu-101", "canon-mp-101"} <= papers


def test_printer_is_reachable_and_validates_a_preset(client):
    status = client.get("/api/printer/status").json()
    assert status["online"] is True
    res = client.post("/api/presets/validate", json={"preset": client.get("/api/presets").json()[0]})
    assert res.status_code == 200, res.text
    assert res.json()["ok"] is True


def test_calibration_chart_prints_to_the_virtual_printer(client):
    preset_id = next(p["id"] for p in client.get("/api/presets").json() if p["id"] == "p-daily-4x6")
    pid = client.post("/api/tools/chart", json={"preset_id": preset_id}).json()["id"]
    deadline = time.time() + 90
    status = None
    while time.time() < deadline:
        status = client.get(f"/api/prints/{pid}").json()["status"]
        if status in ("completed", "failed", "canceled"):
            break
        time.sleep(0.5)
    assert status == "completed"
    outputs = client.get("/api/printer/virtual/outputs").json()
    assert outputs and outputs[0]["format"] in ("image/pwg-raster", "image/jpeg")


def test_render_preview_of_a_test_chart(client):
    res = client.post("/api/render/preview", json={"preset_id": "p-gallery-letter", "test": {"kind": "chart"},
                                                   "max_px": 600})
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "image/jpeg"
    assert res.content[:2] == b"\xff\xd8"


def test_password_protects_the_api(tmp_path, monkeypatch):
    monkeypatch.setenv("PRINTMICH_DATA", str(tmp_path / "config"))
    monkeypatch.setenv("PRINTMICH_STATIC", str(tmp_path / "no-ui"))
    monkeypatch.setenv("PRINTMICH_PASSWORD", "correct horse")
    with TestClient(create_app(load_config())) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/presets").status_code == 401
        assert c.post("/api/auth/login", json={"password": "wrong"}).status_code in (401, 403)
        assert c.post("/api/auth/login", json={"password": "correct horse"}).status_code == 200
        assert c.get("/api/presets").status_code == 200
