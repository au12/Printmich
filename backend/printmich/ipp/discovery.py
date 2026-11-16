"""Find IPP printers on the LAN (mDNS/DNS-SD) or probe an address directly."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from .client import IppClient, IppError, normalize_uri

log = logging.getLogger("printmich.discovery")

SERVICE_TYPES = ["_ipp._tcp.local.", "_ipps._tcp.local."]
COMMON_PATHS = ["/ipp/print", "/ipp/printer", "/ipp", "/printers/printer", "/"]


async def discover(timeout: float = 3.5) -> list[dict[str, Any]]:
    try:
        from zeroconf import ServiceStateChange
        from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf
    except Exception:  # pragma: no cover - zeroconf missing
        return []

    names: set[tuple[str, str]] = set()

    def on_change(zeroconf: Any, service_type: str, name: str, state_change: Any) -> None:
        if state_change is ServiceStateChange.Added:
            names.add((service_type, name))

    azc = AsyncZeroconf()
    results: dict[str, dict[str, Any]] = {}
    try:
        browser = AsyncServiceBrowser(azc.zeroconf, SERVICE_TYPES, handlers=[on_change])
        await asyncio.sleep(timeout)
        for stype, name in sorted(names):
            info = AsyncServiceInfo(stype, name)
            if not await info.async_request(azc.zeroconf, 2000):
                continue
            props: dict[str, str] = {}
            for k, v in (info.properties or {}).items():
                try:
                    props[k.decode()] = v.decode() if isinstance(v, bytes) else (v or "")
                except Exception:
                    continue
            addrs = info.parsed_addresses()
            host = next((a for a in addrs if ":" not in a), addrs[0] if addrs else (info.server or "").rstrip("."))
            secure = stype.startswith("_ipps")
            rp = props.get("rp", "ipp/print").lstrip("/")
            scheme = "ipps" if secure else "ipp"
            uri = normalize_uri(f"{scheme}://{host}:{info.port}/{rp}")
            key = props.get("UUID") or host
            entry = {
                "name": name.split("._")[0],
                "uri": uri,
                "host": host,
                "port": info.port,
                "secure": secure,
                "model": props.get("ty") or props.get("product", "").strip("()"),
                "uuid": props.get("UUID"),
                "admin_url": props.get("adminurl"),
                "formats": [p for p in props.get("pdl", "").split(",") if p],
                "color": props.get("Color") == "T",
            }
            # Prefer plain IPP for maximum compatibility when both are advertised.
            if key not in results or (results[key]["secure"] and not secure):
                results[key] = entry
        await browser.async_cancel()
    except Exception as e:  # pragma: no cover - network dependent
        log.warning("mDNS discovery failed: %s", e)
    finally:
        await azc.async_close()
    return sorted(results.values(), key=lambda r: r["name"].lower())


async def probe(address: str) -> dict[str, Any]:
    """Try common IPP paths on an address and return the first that answers."""
    address = address.strip()
    if "://" in address and not address.rstrip("/").endswith(":631") and address.count("/") > 2:
        candidates = [normalize_uri(address)]
    else:
        base = address.split("://", 1)[-1].rstrip("/")
        candidates = []
        for scheme in ("ipp", "ipps"):
            for path in COMMON_PATHS:
                candidates.append(normalize_uri(f"{scheme}://{base}{path}"))
    last_error = "no response"
    unreachable: set[str] = set()
    for cand in candidates:
        scheme = cand.split("://", 1)[0]
        if scheme in unreachable:
            continue
        client = IppClient(cand, timeout=6.0)
        try:
            attrs = await client.get_printer_attributes(["printer-make-and-model", "printer-name",
                                                         "document-format-supported", "printer-uuid"])
            return {
                "uri": cand,
                "model": (attrs.get("printer-make-and-model") or [""])[0],
                "name": (attrs.get("printer-name") or [""])[0],
                "formats": [str(f) for f in attrs.get("document-format-supported", [])],
            }
        except IppError as e:
            last_error = str(e)
            if "reach" in last_error or "in time" in last_error:
                # host/port unreachable — no point trying other paths on the same scheme
                unreachable.add(scheme)
    raise IppError(f"No IPP printer answered at {address}: {last_error}")
