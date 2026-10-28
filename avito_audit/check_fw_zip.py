#!/usr/bin/env python3
"""Reproducible verification of ``Attachments-Fw_ 27.10 avito.zip`` (8th source ZIP).

Safety mirrors the earlier ZIP checkers: entries are listed and hashed, Apple
binary plists (``NSKeyedArchiver`` pasteboard items) are decoded with the
stdlib ``plistlib`` only, images are never executed, no HTML/JS from the
archive is parsed or copied. The ZIP itself is NOT committed — only decoded
texts, three JPEG photos and a machine-readable manifest.

Usage:
    python avito_audit/check_fw_zip.py /path/to/"Attachments-Fw_ 27.10 avito.zip"

Writes/refreshes ``avito_audit/attachments_fw_2026_10_28/`` and verifies it
against the expected SHA-256 of the archive.
"""
from __future__ import annotations

import hashlib
import io
import json
import plistlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "avito_audit" / "attachments_fw_2026_10_28"
MANIFEST = OUT_DIR / "manifest.json"

EXPECTED_SHA256 = "216adc3cb760c13c5ea85da0a8cf0a5baf9ecb51748ec4619ad4c456bcbc349c"
EXPECTED_BYTES = 669505
SOURCE_COMMIT = "68d7c1f7cb99d3f47a4159bf3ff93d80b194e8fe"
SOURCE_COMMIT_DATE_UTC = "2026-10-28T13:03:40Z"

# Original entry -> (saved file, human note)
TEXT_ENTRIES = [
    ("text.txt", "message_01.txt"),
    ("text-1.txt", "message_02.txt"),
    ("text-2.txt", "message_03.txt"),
    ("text-3.txt", "message_04.txt"),
    ("text-4.txt", "message_05.txt"),
    ("text-5.txt", "message_06.txt"),
    ("text-6.txt", "message_07.txt"),
]
PHOTO_ENTRIES = [
    ("image.", "seller_photo_01.jpg"),
    ("image-1.", "seller_photo_02.jpg"),
    ("image-2.", "seller_photo_03.jpg"),
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def jpeg_dimensions(data: bytes) -> list[int]:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        return list(image.size)


def decode_message(data: bytes) -> str:
    plist = plistlib.loads(data)  # NSKeyedArchiver container
    objects = plist["$objects"]
    text = objects[1]
    if not isinstance(text, str):
        raise ValueError("Unexpected plist payload")
    return text


def main() -> int:
    zip_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("Attachments-Fw_ 27.10 avito.zip")
    if not zip_path.is_file():
        print(f"ZIP not found: {zip_path}", file=sys.stderr)
        return 2
    raw = zip_path.read_bytes()
    digest = sha256(raw)
    if digest != EXPECTED_SHA256 or len(raw) != EXPECTED_BYTES:
        print(f"SHA-256 mismatch: {digest}", file=sys.stderr)
        return 3
    if zipfile.ZipFile(zip_path).testzip() is not None:
        print("Corrupt entry inside ZIP", file=sys.stderr)
        return 4

    archive = zipfile.ZipFile(zip_path)
    names = archive.namelist()
    if len(names) != 10 or set(names) != {e for e, _ in TEXT_ENTRIES + PHOTO_ENTRIES}:
        print(f"Unexpected entry set: {sorted(names)}", file=sys.stderr)
        return 5

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    messages, photos = [], []
    for entry, saved in TEXT_ENTRIES:
        data = archive.read(entry)
        text = decode_message(data)
        (OUT_DIR / saved).write_text(text, encoding="utf-8")
        header, _, body = text.partition("\n")
        messages.append(
            {
                "source_entry": entry,
                "sha256": sha256(data),
                "bytes": len(data),
                "format": "apple_binary_plist_nskeyedarchiver",
                "decoded_file": saved,
                "sender_line": header,
                "text": text,
            }
        )
    for entry, saved in PHOTO_ENTRIES:
        data = archive.read(entry)
        if not data.startswith(b"\xff\xd8"):
            print(f"{entry}: not a JPEG", file=sys.stderr)
            return 6
        (OUT_DIR / saved).write_bytes(data)
        photos.append(
            {
                "source_entry": entry,
                "sha256": sha256(data),
                "bytes": len(data),
                "dimensions": jpeg_dimensions(data),
                "format": "jpeg",
                "saved_file": saved,
                "classification": "seller_chat_photo",
            }
        )

    manifest = {
        "schema_version": 1,
        "archive_name": "Attachments-Fw_ 27.10 avito.zip",
        "source_repository": "usaforyou/MANUS1",
        "source_commit": SOURCE_COMMIT,
        "source_commit_date_utc": SOURCE_COMMIT_DATE_UTC,
        "archive_sha256": EXPECTED_SHA256,
        "archive_bytes": EXPECTED_BYTES,
        "entries_count": 10,
        "verified_at": "2026-10-28",
        "safety": {
            "nested_archives": 0,
            "html_or_js_entries": 0,
            "pdf_entries": 0,
            "notes": "Seven Apple binary plists decoded with stdlib plistlib; three JPEG photos copied byte-for-byte; nothing executed.",
        },
        "messages": messages,
        "photos": photos,
        "status": "seller_claims_2026_10_28_not_verified_live",
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK: {len(messages)} messages, {len(photos)} photos -> {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
