"""Minimal, dependency-free IPP/2.0 message encoder and decoder (RFC 8010/8011).

Supports every value syntax used by IPP Everywhere / AirPrint printers including
collections (media-col, media-col-database), resolutions, ranges and dateTime.
"""
from __future__ import annotations

import datetime as _dt
import struct
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class Op(IntEnum):
    PRINT_JOB = 0x0002
    VALIDATE_JOB = 0x0004
    CREATE_JOB = 0x0005
    SEND_DOCUMENT = 0x0006
    CANCEL_JOB = 0x0008
    GET_JOB_ATTRIBUTES = 0x0009
    GET_JOBS = 0x000A
    GET_PRINTER_ATTRIBUTES = 0x000B
    IDENTIFY_PRINTER = 0x003C


class Tag(IntEnum):
    # delimiters
    OPERATION = 0x01
    JOB = 0x02
    END = 0x03
    PRINTER = 0x04
    UNSUPPORTED_GROUP = 0x05
    # out-of-band
    UNSUPPORTED = 0x10
    UNKNOWN = 0x12
    NO_VALUE = 0x13
    NOT_SETTABLE = 0x15
    DELETE_ATTRIBUTE = 0x16
    ADMIN_DEFINE = 0x17
    # integer
    INTEGER = 0x21
    BOOLEAN = 0x22
    ENUM = 0x23
    # octet
    OCTET_STRING = 0x30
    DATETIME = 0x31
    RESOLUTION = 0x32
    RANGE = 0x33
    BEGIN_COLLECTION = 0x34
    TEXT_LANG = 0x35
    NAME_LANG = 0x36
    END_COLLECTION = 0x37
    # character string
    TEXT = 0x41
    NAME = 0x42
    KEYWORD = 0x44
    URI = 0x45
    URI_SCHEME = 0x46
    CHARSET = 0x47
    LANGUAGE = 0x48
    MIME_TYPE = 0x49
    MEMBER_NAME = 0x4A


STRING_TAGS = {
    Tag.TEXT, Tag.NAME, Tag.KEYWORD, Tag.URI, Tag.URI_SCHEME, Tag.CHARSET,
    Tag.LANGUAGE, Tag.MIME_TYPE, Tag.MEMBER_NAME,
}

STATUS_NAMES = {
    0x0000: "successful-ok",
    0x0001: "successful-ok-ignored-or-substituted-attributes",
    0x0002: "successful-ok-conflicting-attributes",
    0x0400: "client-error-bad-request",
    0x0401: "client-error-forbidden",
    0x0402: "client-error-not-authenticated",
    0x0403: "client-error-not-authorized",
    0x0404: "client-error-not-possible",
    0x0405: "client-error-timeout",
    0x0406: "client-error-not-found",
    0x0407: "client-error-gone",
    0x0408: "client-error-request-entity-too-large",
    0x0409: "client-error-request-value-too-long",
    0x040A: "client-error-document-format-not-supported",
    0x040B: "client-error-attributes-or-values-not-supported",
    0x040C: "client-error-uri-scheme-not-supported",
    0x040D: "client-error-charset-not-supported",
    0x040E: "client-error-conflicting-attributes",
    0x040F: "client-error-compression-not-supported",
    0x0410: "client-error-compression-error",
    0x0411: "client-error-document-format-error",
    0x0412: "client-error-document-access-error",
    0x0500: "server-error-internal-error",
    0x0501: "server-error-operation-not-supported",
    0x0502: "server-error-service-unavailable",
    0x0503: "server-error-version-not-supported",
    0x0504: "server-error-device-error",
    0x0505: "server-error-temporary-error",
    0x0506: "server-error-not-accepting-jobs",
    0x0507: "server-error-busy",
    0x0508: "server-error-job-canceled",
    0x0509: "server-error-multiple-document-jobs-not-supported",
}


def status_name(code: int) -> str:
    return STATUS_NAMES.get(code, f"status-0x{code:04x}")


@dataclass(frozen=True)
class Resolution:
    x: int
    y: int
    units: int = 3  # 3 = dots per inch, 4 = dots per centimeter

    @property
    def dpi(self) -> tuple[int, int]:
        if self.units == 4:
            return round(self.x * 2.54), round(self.y * 2.54)
        return self.x, self.y

    def __str__(self) -> str:
        unit = "dpi" if self.units == 3 else "dpcm"
        return f"{self.x}x{self.y}{unit}" if self.x != self.y else f"{self.x}{unit}"


@dataclass(frozen=True)
class Range:
    lower: int
    upper: int

    def __contains__(self, item: int) -> bool:  # pragma: no cover - trivial
        return self.lower <= item <= self.upper

    def __str__(self) -> str:
        return f"{self.lower}-{self.upper}"


@dataclass(frozen=True)
class OutOfBand:
    tag: int

    def __str__(self) -> str:
        return {0x10: "unsupported", 0x12: "unknown", 0x13: "no-value"}.get(self.tag, f"oob-0x{self.tag:02x}")


@dataclass
class Attr:
    """An attribute ready to be encoded. For collections, ``values`` holds a list of
    member lists (each member list is a list[Attr])."""

    name: str
    tag: int
    values: list[Any] = field(default_factory=list)


# ---------------------------------------------------------------- builders

def _vals(v: Any) -> list[Any]:
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v]


def keyword(name: str, value: Any) -> Attr:
    return Attr(name, Tag.KEYWORD, _vals(value))


def integer(name: str, value: Any) -> Attr:
    return Attr(name, Tag.INTEGER, _vals(value))


def enum(name: str, value: Any) -> Attr:
    return Attr(name, Tag.ENUM, _vals(value))


def boolean(name: str, value: bool) -> Attr:
    return Attr(name, Tag.BOOLEAN, [bool(value)])


def name_attr(name: str, value: str) -> Attr:
    return Attr(name, Tag.NAME, _vals(value))


def text(name: str, value: str) -> Attr:
    return Attr(name, Tag.TEXT, _vals(value))


def uri(name: str, value: str) -> Attr:
    return Attr(name, Tag.URI, _vals(value))


def charset(name: str, value: str) -> Attr:
    return Attr(name, Tag.CHARSET, _vals(value))


def language(name: str, value: str) -> Attr:
    return Attr(name, Tag.LANGUAGE, _vals(value))


def mime(name: str, value: str) -> Attr:
    return Attr(name, Tag.MIME_TYPE, _vals(value))


def resolution(name: str, x: int, y: int | None = None, units: int = 3) -> Attr:
    return Attr(name, Tag.RESOLUTION, [Resolution(x, y if y is not None else x, units)])


def collection(name: str, *members: list[Attr]) -> Attr:
    """collection("media-col", [member attrs...]) — each positional arg is one value."""
    return Attr(name, Tag.BEGIN_COLLECTION, [list(m) for m in members])


# ---------------------------------------------------------------- encoding

def _encode_value(tag: int, value: Any) -> bytes:
    if tag in (Tag.INTEGER, Tag.ENUM):
        return struct.pack(">i", int(value))
    if tag == Tag.BOOLEAN:
        return b"\x01" if value else b"\x00"
    if tag in STRING_TAGS:
        return str(value).encode("utf-8")
    if tag == Tag.RESOLUTION:
        r: Resolution = value
        return struct.pack(">iib", r.x, r.y, r.units)
    if tag == Tag.RANGE:
        rg: Range = value
        return struct.pack(">ii", rg.lower, rg.upper)
    if tag == Tag.OCTET_STRING:
        return value if isinstance(value, (bytes, bytearray)) else str(value).encode("utf-8")
    if tag in (Tag.TEXT_LANG, Tag.NAME_LANG):
        lang, txt = value
        lb, tb = lang.encode(), txt.encode("utf-8")
        return struct.pack(">H", len(lb)) + lb + struct.pack(">H", len(tb)) + tb
    if tag == Tag.DATETIME:
        d: _dt.datetime = value
        off = d.utcoffset() or _dt.timedelta(0)
        sign = b"+" if off >= _dt.timedelta(0) else b"-"
        mins = abs(int(off.total_seconds() // 60))
        return struct.pack(">HBBBBBB", d.year, d.month, d.day, d.hour, d.minute, d.second,
                           d.microsecond // 100000) + sign + bytes([mins // 60, mins % 60])
    if 0x10 <= tag <= 0x1F:
        return b""
    raise ValueError(f"cannot encode tag 0x{tag:02x}")


def _encode_item(tag: int, name: str, value: bytes) -> bytes:
    nb = name.encode("utf-8")
    return bytes([tag]) + struct.pack(">H", len(nb)) + nb + struct.pack(">H", len(value)) + value


def _encode_collection_body(members: list[Attr]) -> bytes:
    out = bytearray()
    for m in members:
        out += _encode_item(Tag.MEMBER_NAME, "", m.name.encode("utf-8"))
        for v in m.values:
            if m.tag == Tag.BEGIN_COLLECTION:
                out += _encode_item(Tag.BEGIN_COLLECTION, "", b"")
                out += _encode_collection_body(v)
                out += _encode_item(Tag.END_COLLECTION, "", b"")
            else:
                out += _encode_item(m.tag, "", _encode_value(m.tag, v))
    return bytes(out)


def encode_attr(attr: Attr) -> bytes:
    out = bytearray()
    for i, v in enumerate(attr.values):
        nm = attr.name if i == 0 else ""
        if attr.tag == Tag.BEGIN_COLLECTION:
            out += _encode_item(Tag.BEGIN_COLLECTION, nm, b"")
            out += _encode_collection_body(v)
            out += _encode_item(Tag.END_COLLECTION, "", b"")
        else:
            out += _encode_item(attr.tag, nm, _encode_value(attr.tag, v))
    if not attr.values:  # encode as no-value
        out += _encode_item(Tag.NO_VALUE, attr.name, b"")
    return bytes(out)


def encode_request(op: int, request_id: int, groups: Iterable[tuple[int, list[Attr]]],
                   version: tuple[int, int] = (2, 0)) -> bytes:
    out = bytearray(bytes(version))
    out += struct.pack(">HI", int(op), request_id)
    for group_tag, attrs in groups:
        out.append(int(group_tag))
        for a in attrs:
            out += encode_attr(a)
    out.append(Tag.END)
    return bytes(out)


# ---------------------------------------------------------------- decoding

def _u16(data: bytes, pos: int) -> int:
    return struct.unpack_from(">H", data, pos)[0]


def _decode_value(tag: int, v: bytes) -> Any:
    if tag in (Tag.INTEGER, Tag.ENUM):
        if len(v) == 4:
            return struct.unpack(">i", v)[0]
        return int.from_bytes(v, "big", signed=True) if v else 0
    if tag == Tag.BOOLEAN:
        return bool(v[0]) if v else False
    if tag in STRING_TAGS:
        return v.decode("utf-8", "replace")
    if tag == Tag.RESOLUTION and len(v) == 9:
        x, y, u = struct.unpack(">iib", v)
        return Resolution(x, y, u)
    if tag == Tag.RANGE and len(v) == 8:
        lo, hi = struct.unpack(">ii", v)
        return Range(lo, hi)
    if tag == Tag.DATETIME and len(v) == 11:
        y, mo, d, h, mi, s, ds = struct.unpack(">HBBBBBB", v[:8])
        sign = -1 if v[8:9] == b"-" else 1
        tz = _dt.timezone(sign * _dt.timedelta(hours=v[9], minutes=v[10]))
        try:
            return _dt.datetime(y, mo, d, h, mi, s, ds * 100000, tzinfo=tz)
        except ValueError:
            return v.hex()
    if tag in (Tag.TEXT_LANG, Tag.NAME_LANG) and len(v) >= 4:
        ll = _u16(v, 0)
        tl = _u16(v, 2 + ll)
        return v[4 + ll:4 + ll + tl].decode("utf-8", "replace")
    if tag == Tag.OCTET_STRING:
        try:
            return v.decode("utf-8")
        except UnicodeDecodeError:
            return v.hex()
    if 0x10 <= tag <= 0x1F:
        return OutOfBand(tag)
    return v.hex()


def _decode_collection(data: bytes, pos: int) -> tuple[dict[str, list[Any]], int]:
    coll: dict[str, list[Any]] = {}
    member: str | None = None
    while pos < len(data):
        tag = data[pos]
        pos += 1
        nl = _u16(data, pos)
        pos += 2 + nl
        vl = _u16(data, pos)
        pos += 2
        value = data[pos:pos + vl]
        pos += vl
        if tag == Tag.END_COLLECTION:
            return coll, pos
        if tag == Tag.MEMBER_NAME:
            member = value.decode("utf-8", "replace")
            coll.setdefault(member, [])
            continue
        if tag == Tag.BEGIN_COLLECTION:
            val, pos = _decode_collection(data, pos)
        else:
            val = _decode_value(tag, value)
        if member is not None:
            coll.setdefault(member, []).append(val)
    return coll, pos


@dataclass
class IppResponse:
    version: tuple[int, int]
    status: int
    request_id: int
    groups: list[tuple[int, dict[str, list[Any]]]]
    body: bytes = b""

    @property
    def ok(self) -> bool:
        return self.status < 0x0100

    @property
    def status_text(self) -> str:
        return status_name(self.status)

    def group(self, tag: int) -> dict[str, list[Any]]:
        merged: dict[str, list[Any]] = {}
        for t, attrs in self.groups:
            if t == tag:
                merged.update(attrs)
        return merged

    def groups_of(self, tag: int) -> list[dict[str, list[Any]]]:
        return [attrs for t, attrs in self.groups if t == tag]

    @property
    def operation(self) -> dict[str, list[Any]]:
        return self.group(Tag.OPERATION)

    @property
    def printer(self) -> dict[str, list[Any]]:
        return self.group(Tag.PRINTER)

    @property
    def job(self) -> dict[str, list[Any]]:
        return self.group(Tag.JOB)

    @property
    def unsupported(self) -> dict[str, list[Any]]:
        return self.group(Tag.UNSUPPORTED_GROUP)

    @property
    def message(self) -> str:
        msg = self.operation.get("status-message")
        return str(msg[0]) if msg else ""


def decode_message(data: bytes) -> IppResponse:
    if len(data) < 8:
        raise ValueError("IPP response too short")
    version = (data[0], data[1])
    status, request_id = struct.unpack_from(">HI", data, 2)
    pos = 8
    groups: list[tuple[int, dict[str, list[Any]]]] = []
    current: dict[str, list[Any]] | None = None
    last_name: str | None = None
    while pos < len(data):
        tag = data[pos]
        pos += 1
        if tag == Tag.END:
            break
        if tag < 0x10:  # begin-attribute-group
            current = {}
            groups.append((tag, current))
            last_name = None
            continue
        nl = _u16(data, pos)
        pos += 2
        name = data[pos:pos + nl].decode("utf-8", "replace")
        pos += nl
        vl = _u16(data, pos)
        pos += 2
        value = data[pos:pos + vl]
        pos += vl
        if tag == Tag.BEGIN_COLLECTION:
            val, pos = _decode_collection(data, pos)
        else:
            val = _decode_value(tag, value)
        if current is None:  # malformed but be lenient
            current = {}
            groups.append((Tag.OPERATION, current))
        if name:
            current[name] = [val]
            last_name = name
        elif last_name is not None:
            current[last_name].append(val)
    return IppResponse(version, status, request_id, groups, data[pos:])


# ---------------------------------------------------------------- helpers

def to_jsonable(value: Any) -> Any:
    """Convert decoded IPP values into JSON-friendly structures."""
    if isinstance(value, dict):
        return {k: to_jsonable(v[0] if isinstance(v, list) and len(v) == 1 else v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, Resolution):
        return str(value)
    if isinstance(value, Range):
        return {"lower": value.lower, "upper": value.upper}
    if isinstance(value, OutOfBand):
        return f"({value})"
    if isinstance(value, _dt.datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def attrs_to_json(attrs: dict[str, list[Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in sorted(attrs):
        vals = attrs[k]
        out[k] = to_jsonable(vals[0]) if len(vals) == 1 else [to_jsonable(v) for v in vals]
    return out
