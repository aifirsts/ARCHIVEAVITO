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


def catalog_supplemental(catalog):
    """Curated, human-written notes for the 2026-10-25 layer."""
    for item in catalog["products"]:
        note = item.get("supplemental_2026_10_25")
        if note:
            yield {"id": int(item["id"]), **note}


def fw_photo_assets(layer, fw):
    """Validated photo records for the 2026-10-28 seller-message layer.

    Every photo path/hash in the curated catalog layer must match the
    mechanical manifest produced by ``avito_audit/check_fw_zip.py``.
    """
    by_entry = {photo["source_entry"]: photo for photo in fw["photos"]}
    photos = []
    for photo in layer["photos"]:
        mech = by_entry.get(photo["source_entry"])
        require(mech is not None, f"FW layer photo not in manifest: {photo['source_entry']}")
        record = asset(photo["path"], mech["sha256"], mech["bytes"], mech["dimensions"])
        record.update(
            {
                "source_entry": photo["source_entry"],
                "alt_ru": photo["alt_ru"],
                "ocr_labels": photo["ocr_labels"],
                "linked_offer_ids": photo["linked_offer_ids"],
                "ocr_note_ru": photo["ocr_note_ru"],
            }
        )
        photos.append(record)
    by_entry = {m["source_entry"]: m for m in fw["messages"]}
    for offer in layer["offers"]:
        for photo_path in offer["photo_paths"]:
            require(any(p["path"] == photo_path for p in photos), f"Offer photo missing: {photo_path}")
        for key in ("price_message_file", "description_message_file"):
            require(offer[key] in by_entry, f"Offer message file missing: {offer.get(key)}")
            require(by_entry[offer[key]]["sha256"] is not None, f"Offer message not hashed: {offer.get(key)}")
    return photos


def supplemental_media(attachments, listing_id):
    """New dated layer from Attachments-Avitos.zip (mobile screenshots + page prints).

    Every path/size/dimension is validated against the audit manifest, and the
    assets themselves are re-hashed, so the layer cannot drift from the archive.
    """
    crops = []
    for shot in attachments["mobile_screenshots"]:
        if shot["listing_id"] != listing_id:
            continue
        crop = shot["photo_crop"]
        entry = {
            "gallery_position_in_badge": shot["gallery_position_in_badge"],
            "visually_confirmed_saved_slot": shot["visually_confirmed_saved_slot"],
            "note_ru": shot["note_ru"],
            "source_entry": shot["entry"],
            "source_entry_sha256": shot["entry_sha256"],
            "badge_evidence": asset(
                shot["header_evidence_crop"]["path"],
                shot["header_evidence_crop"]["sha256"],
                shot["header_evidence_crop"]["bytes"],
                shot["header_evidence_crop"]["dimensions"],
            ),
            "asset": None,
            "captured_from": "mobile_screenshot_2026_10_25",
        }
        if crop["stored"]:
            entry["asset"] = asset(crop["path"], crop["derived_sha256"], crop["derived_bytes"], crop["dimensions"])
        else:
            entry["not_stored_reason_ru"] = crop["not_stored_reason_ru"]
        crops.append(entry)
    page_photo = None
    for record in attachments["pdf_embedded_images"]:
        if record.get("pdf_entry", "").endswith(f"({listing_id}).pdf") and record.get("stored_path"):
            page_photo = asset(
                record["stored_path"],
                record["stored_sha256"],
                record["stored_bytes"],
                record["dimensions"],
            )
            page_photo["source_embedded_sha256"] = record["sha256"]
            page_photo["embedded_name"] = record["embedded_name"]
            page_photo["reason_ru"] = record["reason_ru"]
    return crops, page_photo


def build_document():
    catalog = read_json("catalog.json")
    profile = read_json("avito_audit/snapshot.json")
    profile_images = read_json("avito_audit/images_manifest.json")
    pages = read_json("avito_audit/item_pages/data.json")
    official = read_json("official_assets/manifest.json")
    attachments = read_json("avito_audit/attachments_avitos/manifest.json")
    annotations = read_json("avito_audit/attachments_avitos/manifest.json")
    fw = read_json("avito_audit/attachments_fw_2026_10_28/manifest.json")
    fw_layer = catalog["seller_messages_2026_10_28"]
    require(fw_layer["zip_sha256"] == fw["archive_sha256"] and fw_layer["zip_bytes"] == fw["archive_bytes"],
            "FW layer does not match the audited ZIP")
    require(fw_layer["source_commit"] == fw["source_commit"], "FW layer commit mismatch")
    fw_photos = fw_photo_assets(fw_layer, fw)
    by_page = {p["id"]: p for p in pages["items"]}
    by_profile = {p["id"]: p for p in profile["items"]}
    by_official = {p["avito_id"]: p for p in official["items"]}
    previews = defaultdict(list)
    for record in profile_images:
        previews[record["listing_id"]].append(record)
    supplemental = {item["id"]: item for item in catalog_supplemental(catalog)}
    require(set(supplemental) == {8296456393, 8350792227}, "Supplemental layer must cover exactly two listings")
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
        crops, page_photo = supplemental_media(attachments, int(id_))
        if id_ == "8296456393":
            require(len(crops) == 8, "Watches: expected eight mobile gallery frames")
            require([c["gallery_position_in_badge"] for c in crops] == list(range(1, 9)),
                    "Watches: screenshot order changed")
            require(crops[3]["asset"] is not None, "Watches: frame 4 must be stored")
            require(page_photo is None, "Watches: unexpected page-print photo")
        elif id_ == "8350792227":
            require(crops == [], "Case: unexpected mobile screenshots")
            require(page_photo is not None, "Case: page-print photo missing")
        else:
            require(crops == [] and page_photo is None, f"Supplemental media leaked into {id_}")
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
                "mobile_gallery_crops_2026_10_25": crops,
                "page_print_photo_2026_10_25": page_photo,
            },
            "supplemental_2026_10_25": supplemental.get(int(id_)) if id_.isdigit() else supplemental.get(id_),
            "seller_message_2026_10_28": item.get("seller_message_2026_10_28"),
            "manufacturer_research": item["official"],
        })
    require(sum(len(p["media"]["listing_gallery"]) for p in products) == 75, "Gallery count changed")
    require(sum(len(p["media"]["profile_previews"]) for p in products) == 53, "Profile image count changed")
    fw_price_updates = {}
    for product in products:
        note = product.get("seller_message_2026_10_28")
        if not note:
            continue
        offer = [o for o in fw_layer["offers"] if o["matches_catalog_id"] == product["id"]]
        require(len(offer) == 1, f"FW offer must match exactly one listing: {product['id']}")
        require(offer[0]["price_rub_claimed"] == note["price_rub_claimed"] and
                offer[0]["price_quote_ru"] == note["price_quote_ru"],
                f"FW price mismatch between layer and product: {product['id']}")
        require(any(p["path"] == note["photo_path"] for p in fw_photos), "FW product photo missing")
        fw_price_updates[product["id"]] = {
            "price_rub_claimed": note["price_rub_claimed"],
            "archived_price_rub": product["archived_listing"]["price_rub"],
        }
    require(set(fw_price_updates) == {"8166255881", "8230842563"}, "FW price updates must cover exactly two listings")
    return {
        "schema_version": 1,
        "status": "archived_research_not_live_inventory",
        "archive_date": catalog["as_of"],
        "source_repository": pages["source_repository"],
        "source_commit_item_pages": pages["source_commit"],
        "source_archives_sha256": {
            profile["source"]["archive_path"]: profile["source"]["archive_sha256"],
            **pages["archive_sha256"],
            **catalog["supplemental_zips_sha256"],
        },
        "seller_profile_from_archive": {
            "id": profile["profile"]["seller_id"],
            "display_name": profile["profile"]["display_name"],
            "url": profile["profile"]["profile_url"],
        },
        "supplemental_sources": {
            "Attachments-Avitos.zip": {
                "sha256": annotations["archive_sha256"],
                "bytes": annotations["archive_bytes"],
                "source_commit": annotations["source_commit"],
                "source_commit_date": annotations["source_commit_date"],
                "manifest": "avito_audit/attachments_avitos/manifest.json",
                "entries": annotations["entries_count"],
                "captured_at_utc": [item["page_print_creation_date_utc"] for item in annotations["listings"]],
                "status": annotations["status"],
            }
        },
        "owner_note": "Store owner confirmed ownership in conversation; inventory, prices, authenticity, and image rights not independently reverified.",
        "seller_messages_2026_10_28": {
            "source_zip": fw_layer["source_zip"],
            "sha256": fw["archive_sha256"],
            "bytes": fw["archive_bytes"],
            "source_commit": fw["source_commit"],
            "source_commit_date_utc": fw["source_commit_date_utc"],
            "manifest": "avito_audit/attachments_fw_2026_10_28/manifest.json",
            "entries": fw["entries_count"],
            "status": fw["status"],
            "what_it_is_ru": fw_layer["what_it_is_ru"],
            "photos": fw_photos,
            "offers": fw_layer["offers"],
            "price_updates_for_catalog": fw_price_updates,
        },
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
