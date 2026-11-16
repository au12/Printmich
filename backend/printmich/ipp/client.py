"""Async IPP client speaking directly to driverless (IPP Everywhere / AirPrint / Mopria)
printers such as the Canon imagePROGRAF PRO-310 — no CUPS, no vendor driver."""
from __future__ import annotations

import asyncio
import itertools
import logging
import os
import ssl
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from .protocol import (
    Attr,
    IppResponse,
    Op,
    Tag,
    charset,
    decode_message,
    encode_request,
    integer,
    keyword,
    language,
    mime,
    name_attr,
    uri,
)

log = logging.getLogger("printmich.ipp")

_request_ids = itertools.count(1)

JOB_STATES = {3: "pending", 4: "pending-held", 5: "processing", 6: "processing-stopped",
              7: "canceled", 8: "aborted", 9: "completed"}
PRINTER_STATES = {3: "idle", 4: "processing", 5: "stopped"}


class IppError(Exception):
    def __init__(self, message: str, status: int | None = None, response: IppResponse | None = None):
        super().__init__(message)
        self.status = status
        self.response = response


def normalize_uri(raw: str) -> str:
    """Accept '10.0.10.42', 'printer.local', 'ipp://host', 'http://host:631/ipp/print' …
    and return a canonical ipp(s):// URI."""
    raw = raw.strip()
    if not raw:
        raise ValueError("empty printer address")
    if "://" not in raw:
        raw = "ipp://" + raw
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme in ("http",):
        scheme = "ipp"
    elif scheme in ("https",):
        scheme = "ipps"
    if scheme not in ("ipp", "ipps", "virtual"):
        raise ValueError(f"unsupported printer URI scheme '{parts.scheme}'")
    if scheme == "virtual":
        return f"virtual://{parts.netloc or 'pro-310'}"
    host = parts.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = parts.port or 631
    path = parts.path or "/ipp/print"
    return f"{scheme}://{host}:{port}{path}"


def http_url_for(ipp_uri: str) -> str:
    parts = urlsplit(ipp_uri)
    scheme = "https" if parts.scheme == "ipps" else "http"
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    port = parts.port or 631
    return f"{scheme}://{host}:{port}{parts.path or '/ipp/print'}"


def _ssl_context() -> ssl.SSLContext:
    # Printers ship self-signed certificates; IPPS is used for privacy on the LAN only.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class IppClient:
    def __init__(self, printer_uri: str, *, user: str = "printmich", timeout: float = 20.0):
        self.printer_uri = normalize_uri(printer_uri)
        self.http_url = http_url_for(self.printer_uri)
        self.user = user
        self.timeout = timeout
        self._version: tuple[int, int] = (2, 0)

    # ------------------------------------------------------------ transport
    def _client(self, long: bool = False) -> httpx.AsyncClient:
        t = httpx.Timeout(connect=10.0, read=900.0 if long else self.timeout,
                          write=900.0 if long else self.timeout, pool=10.0)
        verify: Any = _ssl_context() if self.http_url.startswith("https") else True
        return httpx.AsyncClient(timeout=t, verify=verify, follow_redirects=False,
                                 headers={"User-Agent": "Printmich/1.0 IPP/2.0"})

    def _operation_attrs(self, extra: list[Attr] | None = None) -> list[Attr]:
        attrs = [
            charset("attributes-charset", "utf-8"),
            language("attributes-natural-language", "en"),
            uri("printer-uri", self.printer_uri),
            name_attr("requesting-user-name", self.user),
        ]
        if extra:
            attrs.extend(extra)
        return attrs

    async def request(self, op: Op, groups: list[tuple[int, list[Attr]]], *,
                      document: Path | bytes | None = None, long: bool = False) -> IppResponse:
        version = self._version
        for attempt in range(2):
            req_id = next(_request_ids) & 0x7FFFFFFF
            header = encode_request(op, req_id, groups, version)
            resp = await self._post(header, document, long=long)
            if resp.status == 0x0503 and version == (2, 0) and attempt == 0:
                log.info("printer rejected IPP/2.0, retrying with IPP/1.1")
                version = (1, 1)
                continue
            self._version = version
            return resp
        return resp  # pragma: no cover

    async def _post(self, header: bytes, document: Path | bytes | None, *, long: bool) -> IppResponse:
        headers = {"Content-Type": "application/ipp", "Accept": "application/ipp"}
        if document is None:
            content: Any = header
        elif isinstance(document, (bytes, bytearray)):
            content = header + bytes(document)
        else:
            size = os.path.getsize(document)
            headers["Content-Length"] = str(len(header) + size)

            async def stream() -> AsyncIterator[bytes]:
                yield header
                loop = asyncio.get_running_loop()
                with open(document, "rb") as fh:
                    while True:
                        chunk = await loop.run_in_executor(None, fh.read, 1 << 20)
                        if not chunk:
                            break
                        yield chunk

            content = stream()
        try:
            async with self._client(long) as client:
                r = await client.post(self.http_url, content=content, headers=headers)
        except httpx.ConnectError as e:
            raise IppError(f"Can't reach the printer at {self.http_url} ({e.__class__.__name__}). "
                           "Is it powered on and on the same network?") from e
        except httpx.TimeoutException as e:
            raise IppError(f"The printer at {self.http_url} did not answer in time.") from e
        except httpx.HTTPError as e:
            raise IppError(f"HTTP error talking to printer: {e}") from e
        if r.status_code != 200:
            raise IppError(f"Printer answered HTTP {r.status_code} for {self.http_url}")
        try:
            return decode_message(r.content)
        except Exception as e:  # pragma: no cover - defensive
            raise IppError(f"Could not decode IPP response: {e}") from e

    # ------------------------------------------------------------ operations
    async def get_printer_attributes(self, requested: list[str] | None = None) -> dict[str, list[Any]]:
        requested = requested or ["all", "media-col-database"]
        resp = await self.request(Op.GET_PRINTER_ATTRIBUTES, [
            (Tag.OPERATION, self._operation_attrs([keyword("requested-attributes", requested)])),
        ])
        if not resp.ok:
            # Some printers choke on media-col-database; retry with "all" only.
            if "media-col-database" in requested:
                return await self.get_printer_attributes(["all"])
            raise IppError(f"Get-Printer-Attributes failed: {resp.status_text} {resp.message}",
                           resp.status, resp)
        attrs = resp.printer
        if "media-col-database" not in attrs and requested == ["all", "media-col-database"]:
            try:
                extra = await self.request(Op.GET_PRINTER_ATTRIBUTES, [
                    (Tag.OPERATION, self._operation_attrs([keyword("requested-attributes", ["media-col-database"])])),
                ])
                if extra.ok:
                    attrs.update(extra.printer)
            except IppError:
                pass
        return attrs

    async def get_state(self) -> dict[str, list[Any]]:
        resp = await self.request(Op.GET_PRINTER_ATTRIBUTES, [
            (Tag.OPERATION, self._operation_attrs([keyword("requested-attributes", [
                "printer-state", "printer-state-reasons", "printer-state-message", "printer-is-accepting-jobs",
                "marker-names", "marker-colors", "marker-levels", "marker-low-levels", "marker-high-levels",
                "marker-types", "media-col-ready", "media-ready", "printer-alert", "printer-alert-description",
                "queued-job-count",
            ])])),
        ])
        if not resp.ok:
            raise IppError(f"Get-Printer-Attributes failed: {resp.status_text}", resp.status, resp)
        return resp.printer

    async def validate_job(self, document_format: str, job_attrs: list[Attr]) -> IppResponse:
        return await self.request(Op.VALIDATE_JOB, [
            (Tag.OPERATION, self._operation_attrs([mime("document-format", document_format),
                                                   name_attr("job-name", "Printmich validation")])),
            (Tag.JOB, job_attrs),
        ])

    async def print_job(self, document: Path | bytes, document_format: str, job_attrs: list[Attr], *,
                        job_name: str, document_name: str | None = None) -> IppResponse:
        op_extra = [
            name_attr("job-name", job_name[:255]),
            mime("document-format", document_format),
        ]
        if document_name:
            op_extra.append(name_attr("document-name", document_name[:255]))
        resp = await self.request(Op.PRINT_JOB, [
            (Tag.OPERATION, self._operation_attrs(op_extra)),
            (Tag.JOB, job_attrs),
        ], document=document, long=True)
        if not resp.ok:
            detail = resp.message or resp.status_text
            unsupported = resp.unsupported
            if unsupported:
                detail += " (unsupported: " + ", ".join(sorted(unsupported)) + ")"
            raise IppError(f"Printer refused the job: {detail}", resp.status, resp)
        return resp

    async def get_job(self, job_id: int) -> dict[str, list[Any]]:
        resp = await self.request(Op.GET_JOB_ATTRIBUTES, [
            (Tag.OPERATION, self._operation_attrs([
                integer("job-id", job_id),
                keyword("requested-attributes", [
                    "job-id", "job-state", "job-state-reasons", "job-state-message", "job-name",
                    "job-impressions-completed", "job-media-sheets-completed", "time-at-completed",
                    "date-time-at-completed", "job-printer-state-message", "job-printer-state-reasons",
                ]),
            ])),
        ])
        if not resp.ok:
            raise IppError(f"Get-Job-Attributes failed: {resp.status_text}", resp.status, resp)
        return resp.job

    async def get_jobs(self, which: str = "not-completed", limit: int = 20) -> list[dict[str, list[Any]]]:
        resp = await self.request(Op.GET_JOBS, [
            (Tag.OPERATION, self._operation_attrs([
                keyword("which-jobs", which),
                integer("limit", limit),
                keyword("requested-attributes", ["job-id", "job-state", "job-name", "job-state-reasons",
                                                 "job-originating-user-name", "time-at-creation"]),
            ])),
        ])
        if not resp.ok:
            raise IppError(f"Get-Jobs failed: {resp.status_text}", resp.status, resp)
        return resp.groups_of(Tag.JOB)

    async def cancel_job(self, job_id: int) -> IppResponse:
        return await self.request(Op.CANCEL_JOB, [
            (Tag.OPERATION, self._operation_attrs([integer("job-id", job_id)])),
        ])

    async def identify(self) -> IppResponse:
        return await self.request(Op.IDENTIFY_PRINTER, [
            (Tag.OPERATION, self._operation_attrs([keyword("identify-actions", ["flash", "sound"])])),
        ])

    async def fetch(self, url: str, max_bytes: int = 2_000_000) -> bytes:
        """Fetch an auxiliary resource from the printer (icons, strings files)."""
        async with self._client() as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.content[:max_bytes]
