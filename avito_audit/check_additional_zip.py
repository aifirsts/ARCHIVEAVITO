"""Audit the later ДОЗАГРУЗКА.zip against the already archived item pages.

Usage: python avito_audit/check_additional_zip.py /path/to/ДОЗАГРУЗКА.zip
This audit DOES NOT assign unrelated image assets to missing gallery positions.
"""
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
EXPECTED_SHA256 = "2a6904ac34d8db42e6bf9f1c07f33d2d366180f1e3fa01c0db420c69dd522a8f"
EXPECTED_IDS = {"8102096652", "8296456393"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main(archive):
    if archive.name != "ДОЗАГРУЗКА.zip" or sha(archive.read_bytes()) != EXPECTED_SHA256:
        raise ValueError("Unexpected ZIP name or SHA-256")
    old = json.loads((ROOT / "item_pages/data.json").read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in old["items"]}
    with zipfile.ZipFile(archive) as z:
        names = set(z.namelist())
        pages = [name for name in names if name.endswith(".html")]
        ids = set()
        photos = 0
        for name in sorted(pages):
            match = re.search(r"\((\d{10})\)\.html$", name)
            if not match or match.group(1) not in EXPECTED_IDS:
                raise ValueError(f"Unexpected HTML page: {name}")
            item_id = match.group(1)
            ids.add(item_id)
            soup = BeautifulSoup(z.read(name), "html.parser")
            gallery = soup.select_one('[data-marker="item-view/main-gallery"]')
            price = soup.select_one('[data-marker="item-view/item-price"]')
            schema = soup.find("script", type="application/ld+json")
            seller = soup.select_one('[data-marker="item-view/seller-info"]')
            if not (gallery and price and schema and seller):
                raise ValueError(f"Missing product page content: {item_id}")
            item = by_id[item_id]
            if not any(item["seller_profile_id"] in a.get("href", "") for a in seller.find_all("a")):
                raise ValueError(f"Seller mismatch: {item_id}")
            product = next(x for x in json.loads(schema.string)["@graph"] if x.get("@type") == "Product")
            if (product.get("sku") != item_id or product.get("image") !=
                    [g["avito_share_url"] for g in item["gallery"]]):
                raise ValueError(f"Product/ordered gallery mismatch: {item_id}")
            if int(re.sub(r"\D", "", price.get_text(" ", strip=True))) != item["display_price_rub"]:
                raise ValueError(f"Visible price mismatch: {item_id}")
            positions = gallery.select('li[role="option"]')
            if len(positions) != len(item["gallery"]):
                raise ValueError(f"Gallery length mismatch: {item_id}")
            for position, (li, existing) in enumerate(zip(positions, item["gallery"]), 1):
                sources = [im.get("src") for im in li.find_all("img") if im.get("src")]
                if len(sources) != 1:
                    raise ValueError(f"Ambiguous gallery position: {item_id}/{position}")
                src = sources[0]
                if existing["thumbnail"]:
                    if not src.startswith("./") or src[2:] not in names:
                        raise ValueError(f"Gallery thumbnail missing from new ZIP: {item_id}/{position}")
                    if sha(z.read(src[2:])) != existing["thumbnail"]["sha256"]:
                        raise ValueError(f"Gallery thumbnail bytes changed: {item_id}/{position}")
                    photos += 1
                elif src != existing.get("missing_thumbnail_url") or src[2:] in names:
                    raise ValueError(f"Remote-only position changed: {item_id}/{position}")
            large = set()
            for img in gallery.find_all("img"):
                src = img.get("src", "")
                if src.startswith("./") and not img.find_parent("li", role="option") and src[2:] in names:
                    large.add(sha(z.read(src[2:])))
            expected_large = {g["large"]["sha256"] for g in item["gallery"] if g["large"]}
            if large != expected_large:
                raise ValueError(f"Large gallery bytes changed: {item_id}")
            photos += len(large)
        if ids != EXPECTED_IDS or "8350792227" in " ".join(pages):
            raise ValueError("Unexpected set of item pages")
    print(f"{len(ids)} previously known HTML pages; {photos} already-saved gallery JPEGs match byte-for-byte")
    print("8350792227: no individual HTML page; 8296456393 position 4: still remote URL only")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python avito_audit/check_additional_zip.py /path/to/ДОЗАГРУЗКА.zip")
    main(Path(sys.argv[1]))
