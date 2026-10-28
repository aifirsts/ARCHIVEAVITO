"""Extract product-only facts and gallery JPEGs from the three MANUS1 item-page ZIPs.

Usage:
    pip install -r avito_audit/requirements.txt
    python avito_audit/extract_item_pages.py \
      /path/to/PART1_HTMLS.zip /path/to/PART_2.zip /path/to/PART3.zip

The ZIPs/HTML/JS are not published: only item facts and gallery image bytes are
written. All seller statements are ARCHIVED CLAIMS, never verified product facts.
"""
import hashlib
import json
import re
import sys
import zipfile
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "item_pages"
EXPECTED = {
    "PART1_HTMLS.zip": "c32f4ba9e5955c0e7111e31d474b99152ab28d12ac0dce6bf32f810640f69795",
    "PART_2.zip": "e33e25c5d3df1d212584b74575d21baffa261d6edf4b782419b8e3b17d4bc677",
    "PART3.zip": "6d02edbd36bb96f4f1f68bc79543e51e520c97ccf91ec861dabce83aa2ae1477",
}
PROFILE_ID = "b2165ff5492372c90fab55f7223f9d3b"
EXPECTED_ITEM_IDS = {
    "7942160038", "7942010246", "7942405497", "8296456393",
    "8165960870", "7942108985", "8230842563", "8166674710",
    "8166335454", "8166255881", "8166119490", "8165981546",
    "8102096652",
}


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def marker(soup, name):
    return soup.select_one(f'[data-marker="item-view/{name}"]')


def file_key(zip_entry):
    # Avito saved a1 (thumbnail) and a4 (large) forms of the same image.
    # E.g. 1.nDqmQLa1... and 1.nDqmQLa4... have the same six-char key.
    base = Path(zip_entry).name
    if not re.match(r"^1\.[A-Za-z0-9_-]{6}a[14]", base):
        raise ValueError(f"Unrecognized gallery image key: {base}")
    return base[2:8]


def load_assets(archive_files):
    assets = {}
    for name in ("PART_2.zip", "PART3.zip"):
        with zipfile.ZipFile(archive_files[name]) as z:
            for member in z.infolist():
                if not member.is_dir() and "_files/" in member.filename:
                    assets[member.filename] = (name, z.read(member.filename))
    return assets


def save_gallery_image(assets, entry, item_id, position, kind):
    if entry not in assets:
        raise ValueError(f"Referenced gallery image missing from ZIPs: {entry}")
    source_zip, raw = assets[entry]
    if not (raw.startswith(b"\xff\xd8\xff") and raw.endswith(b"\xff\xd9")):
        raise ValueError(f"Gallery image is not a complete JPEG: {entry}")
    with Image.open(BytesIO(raw)) as im:
        if im.format != "JPEG":
            raise ValueError(f"Unexpected image type: {entry}")
        width, height = im.size
        im.verify()
    rel = f"item_pages/images/{item_id}/{position:02d}_{kind}.jpg"
    target = ROOT / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return {
        "zip_file": source_zip, "zip_entry": entry, "local_path": "avito_audit/" + rel,
        "sha256": sha(raw), "bytes": len(raw), "dimensions": [width, height],
    }


def extract_item(name, html_bytes, zip_date, assets):
    item_id = re.search(r"\((\d{10})\)\.html$", name)
    if not item_id or item_id.group(1) not in EXPECTED_ITEM_IDS:
        raise ValueError(f"Unknown item-page file: {name}")
    item_id = item_id.group(1)
    soup = BeautifulSoup(html_bytes, "html.parser")
    seller = marker(soup, "seller-info")
    seller_links = [a.get("href", "") for a in seller.find_all("a")] if seller else []
    if not any(PROFILE_ID in link for link in seller_links):
        raise ValueError(f"Seller does not match the profile snapshot: {item_id}")
    item_title = marker(soup, "title-info")
    description = marker(soup, "item-description")
    attrs = marker(soup, "item-params")
    price = marker(soup, "item-price")
    gallery = marker(soup, "main-gallery")
    schema = soup.find("script", type="application/ld+json")
    if not (item_title and description and attrs and price and gallery and schema):
        raise ValueError(f"Missing product content: {item_id}")
    graph = json.loads(schema.string)["@graph"]
    product = next(p for p in graph if p.get("@type") == "Product")
    if product.get("sku") != item_id:
        raise ValueError(f"Product schema SKU mismatch: {item_id}")
    offer = product.get("offers", {})
    if offer.get("priceCurrency") != "RUB":
        raise ValueError(f"Currency mismatch: {item_id}")
    params = {}
    for li in attrs.find_all("li"):
        text = clean(li.get_text(" ", strip=True))
        if ":" in text:
            key, value = text.split(":", 1)
            params[clean(key)] = clean(value)
    date = marker(soup, "item-date")
    old_price = soup.select_one('[data-marker="old-ptrice"]')
    discount = soup.select_one('[data-marker="sale-discount"]')
    total_views = marker(soup, "total-views")
    today_views = marker(soup, "today-views")
    contacts = marker(soup, "item-view-contacts")
    availability = re.search(r"В\s*наличии:\s*(последний\s+товар|несколько)", clean(contacts.get_text(" ", strip=True))) if contacts else None
    if not offer.get("url", "").endswith("_" + item_id):
        raise ValueError(f"Offer URL mismatch: {item_id}")
    display_price = int(re.sub(r"\D", "", price.get_text(" ", strip=True)))
    if not display_price:
        raise ValueError(f"Invalid displayed price: {item_id}")

    # Gallery <li role=option> keeps the 1-based order. Other images inside the
    # gallery include larger a4 versions; map by the shared encoded image key.
    large = {}
    for img in gallery.find_all("img"):
        src = img.get("src", "")
        if src.startswith("./") and not img.find_parent("li", role="option"):
            entry = src[2:]
            if entry in assets:
                key = file_key(entry)
                if key in large and large[key] != entry:
                    raise ValueError(f"Conflicting large gallery photos: {item_id}")
                large[key] = entry
    positions = gallery.select('li[role="option"]')
    share_urls = product.get("image", [])
    if len(positions) != len(share_urls):
        raise ValueError(f"Gallery/structured image count mismatch: {item_id}")
    records = []
    seen_keys = set()
    for position, li in enumerate(positions, 1):
        imgs = [img.get("src") for img in li.find_all("img") if img.get("src")]
        if len(imgs) != 1:
            raise ValueError(f"Expected one thumbnail at gallery position {position}, item {item_id}")
        img_src = imgs[0]
        record = {"position": position, "avito_share_url": share_urls[position-1],
                  "thumbnail": None, "large": None, "best_path": None}
        if img_src.startswith("./"):
            entry = img_src[2:]
            key = file_key(entry)
            if key in seen_keys:
                raise ValueError(f"Duplicate gallery photo: {item_id}/{position}")
            seen_keys.add(key)
            record["thumbnail"] = save_gallery_image(assets, entry, item_id, position, "thumb")
            if key in large:
                record["large"] = save_gallery_image(assets, large.pop(key), item_id, position, "large")
            record["best_path"] = (record["large"] or record["thumbnail"])["local_path"]
        else:
            # One MoonSwatch thumbnail is referenced remotely but not saved.
            # Do not silently manufacture it from another photo.
            record["missing_thumbnail_url"] = img_src
        records.append(record)
    if large:
        raise ValueError(f"Unmatched large gallery photos: {item_id}: {large}")
    return {
        "id": item_id,
        "source": {"zip_file": "PART1_HTMLS.zip", "html_entry": name,
                   "zip_entry_datetime_no_timezone": "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}".format(*zip_date)},
        "seller_profile_id": PROFILE_ID,
        "title_as_saved": clean(item_title.get_text(" ", strip=True)),
        "item_url": offer["url"],
        "display_price_rub": display_price,
        "old_price_display_rub": int(re.sub(r"\D", "", old_price.get_text(" ", strip=True))) if old_price else None,
        "discount_display": clean(discount.get_text(" ", strip=True)) if discount else None,
        "schema_offer_price_rub": int(offer["price"]),
        "schema_offer_price_warning": "schema.org Offer price differs from the visible discounted price in several pages; use display_price_rub for the saved UI",
        "seller_description_schema_ru": clean(product.get("description")),
        "seller_description_html_ru": clean(description.get_text(" ", strip=True)),
        "attributes_as_saved": params,
        "listing_date_display": clean(date.get_text(" ", strip=True)).removeprefix("· ") if date else None,
        "total_views_display": clean(total_views.get_text(" ", strip=True)) if total_views else None,
        "today_views_display": clean(today_views.get_text(" ", strip=True)) if today_views else None,
        "stock_badge_display": clean(availability.group()) if availability else None,
        "gallery": records,
    }


def main(paths):
    archive_files = {p.name: p for p in paths}
    if set(archive_files) != set(EXPECTED):
        raise ValueError(f"Pass exactly these three ZIPs: {sorted(EXPECTED)}")
    for name, expected in EXPECTED.items():
        actual = sha(archive_files[name].read_bytes())
        if actual != expected:
            raise ValueError(f"SHA-256 mismatch for {name}: {actual}")
    assets = load_assets(archive_files)
    with zipfile.ZipFile(archive_files["PART1_HTMLS.zip"]) as z:
        pages = []
        for info in z.infolist():
            if info.filename.endswith(".html"):
                pages.append(extract_item(info.filename, z.read(info), info.date_time, assets))
    if {p["id"] for p in pages} != EXPECTED_ITEM_IDS:
        raise ValueError("Pages do not cover the expected 13 listing IDs")
    manifest = {
        "source_repository": "https://github.com/usaforyou/MANUS1",
        "source_commit": "696ecf0594bbe0057d293b1f81d23a03d1dd76c6",
        "archive_sha256": EXPECTED,
        "method": "Only item-page gallery JPEG bytes; larger images mapped to thumbnail positions by Avito file key. No recommendation/banner assets, JS or seller PII.",
        "items": pages,
        "missing_item_page_ids": ["8350792227"],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "data.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    thumbs = sum(bool(g["thumbnail"]) for p in pages for g in p["gallery"])
    large = sum(bool(g["large"]) for p in pages for g in p["gallery"])
    missing = sum(not g["best_path"] for p in pages for g in p["gallery"])
    print(f"{len(pages)} item pages; {thumbs} gallery thumbnails + {large} large JPEGs; {missing} gallery URL-only")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Usage: python avito_audit/extract_item_pages.py PART1_HTMLS.zip PART_2.zip PART3.zip")
    main([Path(p) for p in sys.argv[1:]])
