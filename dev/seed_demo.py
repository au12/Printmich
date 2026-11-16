"""Seed a running Printmich (pointed at dev/mock_immich.py) with a believable print history.

    python dev/seed_demo.py http://localhost:8080 /config/printmich.db

Uses the virtual printer, then back-dates the prints so the wall and stats look lived-in.
"""
from __future__ import annotations

import datetime as dt
import random
import sqlite3
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
DB = sys.argv[2] if len(sys.argv) > 2 else "/tmp/pmdata/printmich.db"
IMMICH = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:2283"

c = httpx.Client(base_url=BASE, timeout=120)
c.put("/api/settings", json={"immich_url": IMMICH, "immich_api_key": "demo-key", "printer_uri": "virtual://pro-310",
                             "onboarded": True, "cost": {"currency": "$", "ink_per_sq_in": 0.018}}).raise_for_status()

costs = {"canon-pt-101": {"na_index-4x6_4x6in": 0.55, "na_letter_8.5x11in": 2.1},
         "canon-pp-201": {"na_index-4x6_4x6in": 0.32}, "canon-lu-101": {"na_letter_8.5x11in": 1.85},
         "canon-sg-201": {"na_5x7_5x7in": 0.7}, "canon-mp-101": {"na_letter_8.5x11in": 0.62}}
for pid, cps in costs.items():
    c.put(f"/api/papers/{pid}", json={"cost_per_sheet": cps}).raise_for_status()

fav = c.get("/api/immich/browse", params={"source": "recent"}).json()["items"]
fav += c.get("/api/immich/browse", params={"source": "recent", "page": 2}).json()["items"]
random.seed(7)
random.shuffle(fav)
presets = ["p-daily-4x6"] * 6 + ["p-gallery-letter", "p-instant", "p-5x7", "p-bw-matte"]
ids = []
for a in fav[:30]:
    pid = c.post("/api/prints", json={"asset_id": a["id"], "preset_id": random.choice(presets)}).json()["id"]
    ids.append(pid)
print("queued", len(ids))
while True:
    rows = [c.get(f"/api/prints/{i}").json()["status"] for i in ids]
    done = sum(r in ("completed", "failed") for r in rows)
    print(f"\r{done}/{len(ids)} done", end="", flush=True)
    if done == len(ids):
        break
    time.sleep(3)
print()

con = sqlite3.connect(DB)
now = dt.datetime.now(dt.UTC).replace(hour=13, minute=4, second=0, microsecond=0)
rows = con.execute("SELECT id FROM prints ORDER BY created_at").fetchall()
for i, (pid,) in enumerate(rows):
    days = (len(rows) - i) * 2 - 1 if i < len(rows) - 12 else len(rows) - i
    t = now - dt.timedelta(days=days, minutes=random.randint(0, 50))
    con.execute("UPDATE prints SET created_at=?, started_at=?, completed_at=?, source=? WHERE id=?",
                (t.isoformat(timespec="seconds"), t.isoformat(timespec="seconds"),
                 (t + dt.timedelta(minutes=2)).isoformat(timespec="seconds"),
                 "schedule" if i % 3 else "manual", pid))
con.commit()
con.close()

sch = c.get("/api/schedules").json()[0]
sch["enabled"] = True
c.put(f"/api/schedules/{sch['id']}", json=sch).raise_for_status()
r = c.post(f"/api/schedules/{sch['id']}/pick")
print("pick", r.status_code, r.json().get("asset", {}).get("filename"))
