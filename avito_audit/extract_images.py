"""Extract only listing preview JPEGs referenced by snapshot.json from a local ZIP.

Usage: python avito_audit/extract_images.py '/path/to/Авито 14.zip'
Does not execute or unpack HTML/JavaScript. Original ZIP is not committed.
"""
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main(archive: Path) -> None:
    snapshot = json.loads((ROOT / "snapshot.json").read_text(encoding="utf-8"))
    expected_sha = snapshot["source"]["archive_sha256"]
    actual_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual_sha != expected_sha:
        raise ValueError(f"Unexpected ZIP SHA-256: {actual_sha}")

    manifest = []
    with zipfile.ZipFile(archive) as z:
        for item in snapshot["items"]:
            # The id is the numeric listing id, not a ZIP-supplied path.
            item_id = item["id"]
            if not item_id.isdecimal():
                raise ValueError("Non-numeric listing id")
            for position, photo in enumerate(item["visible_photo_previews"], 1):
                source = photo["archive_entry"]
                record = {
                    "listing_id": item_id,
                    "position_in_saved_html": position,
                    "avito_thumbnail_url": photo["thumbnail_url"],
                    "zip_entry": source,
                    "local_path": None,
                    "sha256": None,
                }
                if source:
                    if source not in z.namelist():
                        raise ValueError(f"Missing ZIP entry: {source}")
                    data = z.read(source)
                    if not (data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9")):
                        raise ValueError(f"Not a complete JPEG: {source}")
                    relative_path = f"images/{item_id}/{position:02}.jpg"
                    target = ROOT / relative_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    record["local_path"] = relative_path
                    record["sha256"] = hashlib.sha256(data).hexdigest()
                manifest.append(record)

    (ROOT / "images_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Saved {sum(bool(x['local_path']) for x in manifest)} previews; "
          f"{sum(not x['local_path'] for x in manifest)} HTML-only references")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python avito_audit/extract_images.py /path/to/archive.zip")
    main(Path(sys.argv[1]))
