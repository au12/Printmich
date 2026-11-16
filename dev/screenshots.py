"""Capture README screenshots from a running Printmich.

    python dev/screenshots.py http://localhost:8080 docs/images
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/images")
ONLY = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None
OUT.mkdir(parents=True, exist_ok=True)

DESKTOP = {"width": 1440, "height": 900}
MOBILE = {"width": 390, "height": 844}


def shoot(page, name: str, settle: int = 1600, full: bool = False) -> None:
    page.wait_for_timeout(settle)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
    print("saved", name)


def run() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        ctx = browser.new_context(viewport=DESKTOP, device_scale_factor=2, color_scheme="dark")
        page = ctx.new_page()

        def want(n: str) -> bool:
            return ONLY is None or n in ONLY

        if want("today"):
            page.goto(f"{BASE}/")
            page.wait_for_selector(".upnext-title, .empty", timeout=20000)
            shoot(page, "desktop-today", 2600)
        if want("wall"):
            page.goto(f"{BASE}/wall")
            page.wait_for_selector(".tile img", timeout=20000)
            shoot(page, "desktop-wall", 2600)
        if want("viewer"):
            page.goto(f"{BASE}/wall")
            page.wait_for_selector(".tile", timeout=20000)
            page.locator(".tile").nth(3).click()
            page.wait_for_selector(".viewer-stage img", timeout=20000)
            shoot(page, "desktop-viewer", 2600)
            page.get_by_role("radio", name="As printed").click()
            shoot(page, "desktop-viewer-printed", 2200)
        if want("library"):
            page.goto(f"{BASE}/library")
            page.wait_for_selector(".asset img", timeout=20000)
            shoot(page, "desktop-library", 2200)
            page.locator(".asset").nth(2).click()
            page.wait_for_selector(".print-stage .sheet img", timeout=20000)
            shoot(page, "desktop-print-dialog", 2600)
        if want("presets"):
            page.goto(f"{BASE}/presets")
            page.wait_for_selector(".preset-card", timeout=20000)
            page.locator(".preset-card").nth(3).click()
            page.wait_for_selector(".editor-preview .sheet img", timeout=20000)
            shoot(page, "desktop-preset-editor", 2600)
        if want("papers"):
            page.goto(f"{BASE}/papers")
            page.wait_for_selector(".paper-card", timeout=20000)
            shoot(page, "desktop-papers", 1800)
        if want("schedules"):
            page.goto(f"{BASE}/schedules")
            page.wait_for_selector(".schedule-card", timeout=20000)
            page.get_by_role("button", name="Edit").first.click()
            shoot(page, "desktop-schedule-editor", 2000)
        if want("printer"):
            page.goto(f"{BASE}/printer")
            page.wait_for_selector(".ink-row", timeout=20000)
            shoot(page, "desktop-printer", 1800)
        if want("settings"):
            page.goto(f"{BASE}/settings")
            page.wait_for_selector(".panel", timeout=20000)
            page.get_by_role("button", name="Test only").click()
            page.wait_for_selector(".grid-3", timeout=20000)
            shoot(page, "desktop-settings", 1200)
        if want("light"):
            lctx = browser.new_context(viewport=DESKTOP, device_scale_factor=2, color_scheme="light")
            lp = lctx.new_page()
            lp.goto(f"{BASE}/")
            lp.wait_for_selector(".upnext-title", timeout=20000)
            shoot(lp, "desktop-today-light", 2600)
            lctx.close()

        if want("mobile"):
            m = browser.new_context(viewport=MOBILE, device_scale_factor=3, color_scheme="dark", is_mobile=True,
                                    has_touch=True)
            mp = m.new_page()
            mp.goto(f"{BASE}/")
            mp.wait_for_selector(".upnext-title", timeout=20000)
            shoot(mp, "mobile-today", 2600)
            mp.goto(f"{BASE}/wall")
            mp.wait_for_selector(".tile img", timeout=20000)
            shoot(mp, "mobile-wall", 2400)
            mp.locator(".tile").nth(1).click()
            mp.wait_for_selector(".viewer-stage img", timeout=20000)
            shoot(mp, "mobile-viewer", 2400)
            mp.goto(f"{BASE}/library")
            mp.wait_for_selector(".asset img", timeout=20000)
            mp.locator(".asset").nth(0).click()
            mp.wait_for_selector(".print-stage .sheet img", timeout=20000)
            shoot(mp, "mobile-print-dialog", 2600)
            m.close()
        browser.close()


if __name__ == "__main__":
    run()
