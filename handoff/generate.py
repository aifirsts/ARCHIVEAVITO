"""Build a deterministic, source-labeled storefront handoff from the canonical archive.

Run from any directory: python handoff/generate.py
The output is generated; edit catalog.json and source manifests instead of editing it.
"""
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "handoff/storefront.json"


def read_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def asset(path, sha256, expected_size=None, dimensions=None):
    """Only explicitly indexed local assets, never arbitrary ZIP paths or remote URLs."""
    relative = Path(path)
    require(not relative.is_absolute() and ".." not in relative.parts, f"Unsafe asset path: {path}")
    require(relative.parts[0] in {"avito_audit", "official_assets"}, f"Unknown asset root: {path}")
    file = ROOT / relative
    require(file.is_file(), f"Missing asset: {path}")
    data = file.read_bytes()
    require(hashlib.sha256(data).hexdigest() == sha256, f"Asset hash mismatch: {path}")
    if expected_size is not None:
        require(len(data) == expected_size, f"Asset size mismatch: {path}")
    record = {"path": path, "sha256": sha256, "bytes": len(data)}
    if dimensions is not None:
        record["dimensions"] = dimensions
    return record


def build_document():
    catalog = read_json("catalog.json")
    profile = read_json("avito_audit/snapshot.json")
    profile_images = read_json("avito_audit/images_manifest.json")
    pages = read_json("avito_audit/item_pages/data.json")
    official = read_json("official_assets/manifest.json")
    by_page = {p["id"]: p for p in pages["items"]}
    by_profile = {p["id"]: p for p in profile["items"]}
    by_official = {p["avito_id"]: p for p in official["items"]}
    previews = defaultdict(list)
    for record in profile_images:
        previews[record["listing_id"]].append(record)
    ids = [p["id"] for p in catalog["products"]]
    require(len(ids) == 14 and len(set(ids)) == 14, "Expected 14 unique product IDs")
    require(set(ids) == set(by_profile) == set(previews), "Profile IDs mismatch")
    require(len(by_page) == 13 and set(ids) - set(by_page) == {"8350792227"}, "Individual page coverage changed")
    require(set(ids) - set(by_official) == {"8296456393"}, "Manufacturer image coverage changed")
    products = []
    for item in catalog["products"]:
        id_ = item["id"]
        old = by_profile[id_]
        require(item["avito_url"] == old["url"] and item["price_rub_snapshot"] == old["price_rub"],
                f"Profile/catalog mismatch: {id_}")
        require(urlparse(item["avito_url"]).hostname == "www.avito.ru", f"Unexpected product URL: {id_}")
        require(item["official"]["url"].startswith("https://"), f"Invalid manufacturer URL: {id_}")
        profile_gallery = []
        for p in previews[id_]:
            if not p["local_path"]:
                continue
            path = "avito_audit/" + p["local_path"]
            profile_gallery.append({"position": p["position_in_saved_html"],
                                    "asset": asset(path, p["sha256"])})
        require([g["asset"]["path"] for g in profile_gallery] == item["photos"],
                f"Profile gallery mismatch: {id_}")
        page = by_page.get(id_)
        listing_gallery = []
        if page:
            require(page["item_url"] == item["avito_url"] and
                    page["display_price_rub"] == item["price_rub_snapshot"],
                    f"Item page/catalog mismatch: {id_}")
            require(item["avito_item_page"]["description_ru_as_seller_claim"] ==
                    page["seller_description_schema_ru"], f"Seller description mismatch: {id_}")
            for g in page["gallery"]:
                thumb = g["thumbnail"]
                large = g["large"]
                listing_gallery.append({
                    "position": g["position"],
                    "thumbnail": asset(thumb["local_path"], thumb["sha256"], thumb["bytes"], thumb["dimensions"]) if thumb else None,
                    "large": asset(large["local_path"], large["sha256"], large["bytes"], large["dimensions"]) if large else None,
                    "remote_url_only": not bool(g["best_path"]),
                    "missing_remote_url_for_audit": g.get("missing_thumbnail_url"),
                    "avito_share_url_for_audit": g["avito_share_url"],
                })
            require([g["position"] for g in listing_gallery] == list(range(1, len(listing_gallery) + 1)),
                    f"Gallery order changed: {id_}")
        else:
            require(item["avito_item_page"] is None, f"Unmatched item page in catalog: {id_}")
        manufacturer_asset = None
        if id_ in by_official:
            entry = by_official[id_]
            manufacturer_asset = asset(entry["local_path"], entry["sha256"], entry["bytes"], entry["dimensions"])
            require(item["official"]["photos"] == [entry["local_path"]],
                    f"Manufacturer/gallery mismatch: {id_}")
        else:
            require(not item["official"]["photos"], f"Unindexed official asset: {id_}")
        products.append({
            "id": id_, "title_from_seller": item["title"], "category_from_snapshot": item["category"],
            "avito_url": item["avito_url"],
            "archived_listing": {
                "price_rub": item["price_rub_snapshot"],
                "old_price_text": item["old_price_text_snapshot"],
                "discount_text": item["discount_text_snapshot"],
                "location_text": item["location_snapshot"],
                "profile_date_text": item["date_display_snapshot"],
                "description_profile_excerpt": item["avito_profile_excerpt"],
                "individual_page_saved": page is not None,
                "item_page_date_text": page["listing_date_display"] if page else None,
                "seller_description_normalized": page["seller_description_schema_ru"] if page else None,
                "seller_description_html_transcription": page["seller_description_html_ru"] if page else None,
                "attributes_from_seller": page["attributes_as_saved"] if page else None,
                "item_page_views_text": page["total_views_display"] if page else None,
                "item_page_today_views_text": page["today_views_display"] if page else None,
                "stock_badge_text": page["stock_badge_display"] if page else None,
                "schema_offer_price_rub": page["schema_offer_price_rub"] if page else None,
                "item_page_source": page["source"] if page else None,
            },
            "media": {
                "listing_gallery": listing_gallery,
                "profile_previews": profile_gallery,
                "manufacturer_illustration": manufacturer_asset,
            },
            "manufacturer_research": item["official"],
        })
    require(sum(len(p["media"]["listing_gallery"]) for p in products) == 75, "Gallery count changed")
    require(sum(len(p["media"]["profile_previews"]) for p in products) == 53, "Profile image count changed")
    return {
        "schema_version": 1,
        "status": "archived_research_not_live_inventory",
        "archive_date": catalog["as_of"],
        "source_repository": pages["source_repository"],
        "source_commit_item_pages": pages["source_commit"],
        "source_archives_sha256": {
            profile["source"]["archive_path"]: profile["source"]["archive_sha256"],
            **pages["archive_sha256"],
        },
        "seller_profile_from_archive": {
            "id": profile["profile"]["seller_id"],
            "display_name": profile["profile"]["display_name"],
            "url": profile["profile"]["profile_url"],
        },
        "owner_note": "Store owner confirmed ownership in conversation; inventory, prices, authenticity, and image rights not independently reverified.",
        "paths_relative_to": "repository_root",
        "products": products,
    }


def render(document):
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def main():
    OUTPUT.write_text(render(build_document()), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
