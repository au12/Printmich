"""A simulated PRO-310-class IPP printer for demos, testing and dry runs.

Jobs are rendered exactly as they would be for a real printer, then "printed" to
``/config/virtual-printer`` as JPEG previews so you can check layout, color and
borders without spending paper or ink.
"""
from __future__ import annotations

import asyncio
import json
import random
import time
from pathlib import Path
from typing import Any

from .protocol import Attr, IppResponse, Range, Resolution, Tag

INKS = [
    ("MBK · Matte Black", "#232323"), ("PBK · Photo Black", "#000000"), ("GY · Gray", "#8E8E8E"),
    ("C · Cyan", "#00A3E0"), ("PC · Photo Cyan", "#73CDEB"), ("M · Magenta", "#E2007A"),
    ("PM · Photo Magenta", "#F28DC0"), ("Y · Yellow", "#FFDD00"), ("R · Red", "#E4002B"),
    ("CO · Chroma Optimizer", "#D9D9D9"),
]

SIZES_HMM = [
    ("na_index-4x6_4x6in", 10160, 15240), ("na_5x7_5x7in", 12700, 17780), ("oe_photo-l_3.5x5in", 8890, 12700),
    ("oe_square-photo_5x5in", 12700, 12700), ("na_govt-letter_8x10in", 20320, 25400),
    ("na_letter_8.5x11in", 21590, 27940), ("na_legal_8.5x14in", 21590, 35560), ("na_10x12_10x12in", 25400, 30480),
    ("na_11x14_11x14in", 27940, 35560), ("na_ledger_11x17in", 27940, 43180), ("na_super-b_13x19in", 33020, 48260),
    ("iso_a5_148x210mm", 14800, 21000), ("iso_a4_210x297mm", 21000, 29700), ("iso_a3_297x420mm", 29700, 42000),
    ("jis_b5_182x257mm", 18200, 25700), ("jis_b4_257x364mm", 25700, 36400), ("jpn_hagaki_100x148mm", 10000, 14800),
]
MEDIA_TYPES = ["stationery", "photographic-high-gloss", "photographic-glossy", "photographic-satin",
               "photographic-semi-gloss", "photographic-matte", "photographic", "cardstock"]
SOURCES = ["top", "manual"]


def _size(x: int, y: int) -> dict[str, list[Any]]:
    return {"x-dimension": [x], "y-dimension": [y]}


def _margins(top: int, bottom: int, left: int, right: int) -> dict[str, list[Any]]:
    return {"media-top-margin": [top], "media-bottom-margin": [bottom], "media-left-margin": [left],
            "media-right-margin": [right]}


def _attr_json(a: Attr) -> Any:
    if a.tag == Tag.BEGIN_COLLECTION:
        vals = [{m.name: _attr_json(m) for m in members} for members in a.values]
    else:
        vals = [str(v) for v in a.values]
    return vals[0] if len(vals) == 1 else vals


class VirtualPrinter:
    """Duck-types :class:`printmich.ipp.client.IppClient`."""

    def __init__(self, out_dir: Path, uri: str = "virtual://pro-310"):
        self.printer_uri = uri
        self.http_url = uri
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = out_dir / "state.json"
        self._jobs: dict[int, dict[str, Any]] = {}
        self._load_state()

    # ------------------------------------------------------------ state
    def _load_state(self) -> None:
        try:
            st = json.loads(self._state_file.read_text())
        except Exception:
            st = {}
        self.levels: list[int] = st.get("levels") or [random.randint(42, 96) for _ in INKS]
        self.next_job: int = st.get("next_job", 100)
        self.loaded: dict[str, Any] = st.get("loaded") or {"size": "na_index-4x6_4x6in", "type": "photographic-satin",
                                                          "source": "top"}

    def _save_state(self) -> None:
        self._state_file.write_text(json.dumps({"levels": self.levels, "next_job": self.next_job,
                                                "loaded": self.loaded}))

    # ------------------------------------------------------------ attributes
    def _attrs(self) -> dict[str, list[Any]]:
        db = []
        for _kw, x, y in SIZES_HMM:
            for src in SOURCES:
                if src == "manual" and x < 20000:
                    continue  # manual feed only takes 8" wide and up
                db.append({"media-size": [_size(x, y)], "media-source": [src], **_margins(300, 500, 340, 340)})
                db.append({"media-size": [_size(x, y)], "media-source": [src], **_margins(0, 0, 0, 0)})
        loaded = self.loaded
        ready_dims = next(((x, y) for kw, x, y in SIZES_HMM if kw == loaded["size"]), (10160, 15240))
        jobs_active = any(j["state"] in (3, 5) for j in self._jobs.values())
        return {
            "printer-make-and-model": ["Printmich Virtual PRO-310"],
            "printer-name": ["virtual-pro-310"],
            "printer-info": ["Virtual printer (saves prints as images)"],
            "printer-location": ["Printmich"],
            "printer-uuid": ["urn:uuid:7072696e-746d-6963-6800-000000000310"],
            "printer-firmware-string-version": ["simulated"],
            "printer-state": [4 if jobs_active else 3],
            "printer-state-reasons": ["none"],
            "printer-is-accepting-jobs": [True],
            "document-format-supported": ["application/octet-stream", "image/pwg-raster", "image/jpeg", "image/urf"],
            "document-format-default": ["application/octet-stream"],
            "pwg-raster-document-resolution-supported": [Resolution(300, 300), Resolution(600, 600)],
            "pwg-raster-document-type-supported": ["sgray_8", "sgray_16", "srgb_8", "srgb_16", "adobe-rgb_8",
                                                   "adobe-rgb_16"],
            "urf-supported": ["V1.4", "CP1", "PQ3-4-5", "RS300-600", "SRGB24", "ADOBERGB24", "ADOBERGB48", "W8"],
            "jpeg-k-octets-supported": [Range(0, 64000)],
            "jpeg-x-dimension-supported": [Range(0, 16384)],
            "jpeg-y-dimension-supported": [Range(1, 16384)],
            "media-supported": [kw for kw, _, _ in SIZES_HMM],
            "media-default": ["na_index-4x6_4x6in"],
            "media-size-supported": [_size(x, y) for _, x, y in SIZES_HMM],
            "media-type-supported": MEDIA_TYPES,
            "media-source-supported": SOURCES,
            "media-top-margin-supported": [0, 300],
            "media-bottom-margin-supported": [0, 500],
            "media-left-margin-supported": [0, 340],
            "media-right-margin-supported": [0, 340],
            "media-col-database": db,
            "media-col-default": [{"media-size": [_size(10160, 15240)], "media-type": ["photographic-satin"],
                                   "media-source": ["top"], **_margins(300, 500, 340, 340)}],
            "media-col-ready": [{"media-size": [_size(*ready_dims)], "media-type": [loaded["type"]],
                                 "media-source": [loaded["source"]], **_margins(0, 0, 0, 0)}],
            "print-quality-supported": [3, 4, 5],
            "print-quality-default": [4],
            "printer-resolution-supported": [Resolution(300, 300), Resolution(600, 600)],
            "print-color-mode-supported": ["auto", "color", "monochrome"],
            "print-color-mode-default": ["color"],
            "print-scaling-supported": ["auto", "auto-fit", "fill", "fit", "none"],
            "print-content-optimize-supported": ["auto", "photo", "graphic", "text"],
            "print-rendering-intent-supported": ["auto", "perceptual", "relative", "relative-bpc", "saturation",
                                                 "absolute"],
            "copies-supported": [Range(1, 99)],
            "orientation-requested-supported": [3, 4, 5, 6],
            "job-creation-attributes-supported": ["copies", "media", "media-col", "orientation-requested",
                                                  "print-color-mode", "print-quality", "printer-resolution",
                                                  "print-scaling", "print-content-optimize",
                                                  "print-rendering-intent", "sides"],
            "marker-names": [n for n, _ in INKS],
            "marker-colors": [c for _, c in INKS],
            "marker-levels": list(self.levels),
            "marker-low-levels": [15] * len(INKS),
            "marker-high-levels": [100] * len(INKS),
            "marker-types": ["ink-cartridge"] * len(INKS),
        }

    async def get_printer_attributes(self, requested: list[str] | None = None) -> dict[str, list[Any]]:
        self._tick()
        return self._attrs()

    async def get_state(self) -> dict[str, list[Any]]:
        self._tick()
        a = self._attrs()
        return {k: v for k, v in a.items() if k.startswith(("printer-state", "marker-", "media-col-ready",
                                                             "printer-is-accepting"))}

    def set_loaded(self, size: str, media_type: str, source: str = "top") -> None:
        self.loaded = {"size": size, "type": media_type, "source": source}
        self._save_state()

    # ------------------------------------------------------------ jobs
    def _tick(self) -> None:
        now = time.time()
        for j in self._jobs.values():
            if j["state"] in (3, 5) and now - j["created"] > 3.5:
                j["state"] = 9
                j["reasons"] = ["job-completed-successfully"]
            elif j["state"] == 3 and now - j["created"] > 0.8:
                j["state"] = 5
                j["reasons"] = ["job-printing"]

    def _resp(self, job: dict[str, list[Any]] | None = None, status: int = 0) -> IppResponse:
        groups: list[tuple[int, dict[str, list[Any]]]] = [(Tag.OPERATION, {"status-message": ["successful-ok"]})]
        if job:
            groups.append((Tag.JOB, job))
        return IppResponse((2, 0), status, 1, groups)

    async def validate_job(self, document_format: str, job_attrs: list[Attr]) -> IppResponse:
        return self._resp()

    async def print_job(self, document: Path | bytes, document_format: str, job_attrs: list[Attr], *,
                        job_name: str, document_name: str | None = None) -> IppResponse:
        job_id = self.next_job
        self.next_job += 1
        data = document if isinstance(document, (bytes, bytearray)) else Path(document).read_bytes()
        await asyncio.get_running_loop().run_in_executor(None, self._save_output, job_id, bytes(data),
                                                         document_format, job_name, job_attrs)
        # ink usage simulation
        for i in range(len(self.levels)):
            self.levels[i] = max(3, self.levels[i] - random.choice((0, 0, 1)))
        self._save_state()
        self._jobs[job_id] = {"state": 3, "created": time.time(), "name": job_name, "reasons": ["none"]}
        return self._resp({"job-id": [job_id], "job-state": [3], "job-state-reasons": ["none"],
                           "job-uri": [f"{self.printer_uri}/jobs/{job_id}"]})

    def _save_output(self, job_id: int, data: bytes, fmt: str, job_name: str, job_attrs: list[Attr]) -> None:
        import pyvips

        from . import pwg

        stem = self.out_dir / f"job-{job_id:05d}"
        meta: dict[str, Any] = {"job_id": job_id, "name": job_name, "format": fmt, "bytes": len(data),
                                "created": time.time(),
                                "attributes": {a.name: _attr_json(a) for a in job_attrs}}
        try:
            if fmt == "image/pwg-raster":
                pages = pwg.read_document(data)
                hdr, arr = pages[0]
                meta["pwg"] = {k: v for k, v in hdr.items() if k != "magic"}
                if arr.dtype != "uint8":
                    arr = (arr >> 8).astype("uint8")
                img = pyvips.Image.new_from_memory(arr.tobytes(), arr.shape[1], arr.shape[0], arr.shape[2], "uchar")
            else:
                img = pyvips.Image.new_from_buffer(data, "")
            img.thumbnail_image(1600).jpegsave(str(stem) + ".jpg", Q=90)
        except Exception as e:  # pragma: no cover - diagnostics only
            meta["error"] = str(e)
        (stem.with_suffix(".json")).write_text(json.dumps(meta, indent=2, default=str))

    async def get_job(self, job_id: int) -> dict[str, list[Any]]:
        self._tick()
        j = self._jobs.get(job_id)
        if not j:
            return {"job-id": [job_id], "job-state": [9], "job-state-reasons": ["job-completed-successfully"]}
        return {"job-id": [job_id], "job-state": [j["state"]], "job-state-reasons": j["reasons"],
                "job-name": [j["name"]]}

    async def get_jobs(self, which: str = "not-completed", limit: int = 20) -> list[dict[str, list[Any]]]:
        self._tick()
        out = []
        for jid, j in sorted(self._jobs.items(), reverse=True):
            done = j["state"] >= 7
            if (which == "completed") == done:
                out.append({"job-id": [jid], "job-state": [j["state"]], "job-name": [j["name"]]})
        return out[:limit]

    async def cancel_job(self, job_id: int) -> IppResponse:
        if job_id in self._jobs and self._jobs[job_id]["state"] < 7:
            self._jobs[job_id]["state"] = 7
            self._jobs[job_id]["reasons"] = ["job-canceled-by-user"]
        return self._resp()

    async def identify(self) -> IppResponse:
        return self._resp()

    async def fetch(self, url: str, max_bytes: int = 2_000_000) -> bytes:
        raise FileNotFoundError(url)

    def outputs(self, limit: int = 50) -> list[dict[str, Any]]:
        out = []
        for meta_file in sorted(self.out_dir.glob("job-*.json"), reverse=True)[:limit]:
            try:
                meta = json.loads(meta_file.read_text())
            except Exception:
                continue
            meta["image"] = meta_file.with_suffix(".jpg").name if meta_file.with_suffix(".jpg").exists() else None
            out.append(meta)
        return out
