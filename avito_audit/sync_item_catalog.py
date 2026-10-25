"""Update catalog.json with extracted product-page details, preserving profile and official data.

Run after extract_item_pages.py; all item-page claims remain labeled as archived.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    catalog_path = ROOT / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    item_pages = json.loads((ROOT / "avito_audit/item_pages/data.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in item_pages["items"]}
    profile_snapshot = json.loads((ROOT / "avito_audit/snapshot.json").read_text(encoding="utf-8"))
    profile_by_id = {p["id"]: p for p in profile_snapshot["items"]}
    if len(catalog["products"]) != 14 or len(by_id) != 13 or len(profile_by_id) != 14:
        raise ValueError("Unexpected number of catalog listings or individual item pages")
    for item in catalog["products"]:
        item_id = item["id"]
        profile_item = profile_by_id[item_id]
        item["avito_profile_excerpt"] = {
            "text": profile_item["description_excerpt"],
            "truncated": profile_item["description_truncated"],
            "source": profile_item["source_html"],
        }
        if item_id not in by_id:
            if item_id != "8350792227":
                raise ValueError(f"Unexpected item without a saved page: {item_id}")
            item["avito_item_page"] = None
            continue
        page = by_id[item_id]
        if page["display_price_rub"] != item["price_rub_snapshot"] or page["item_url"] != item["avito_url"]:
            raise ValueError(f"Profile/page price or URL mismatch: {item_id}; review manually")
        item["avito_item_page"] = {
            "description_ru_as_seller_claim": page["seller_description_schema_ru"],
            "attributes_as_seller_claim": page["attributes_as_saved"],
            "date_display_snapshot": page["listing_date_display"],
            "display_price_rub_snapshot": page["display_price_rub"],
            "old_price_display_rub_snapshot": page["old_price_display_rub"],
            "discount_display_snapshot": page["discount_display"],
            "total_views_display_snapshot": page["total_views_display"],
            "stock_badge_display_snapshot": page["stock_badge_display"],
            "source_html_entry": page["source"]["html_entry"],
            "gallery_count": len(page["gallery"]),
            "gallery_missing_count": sum(not g["best_path"] for g in page["gallery"]),
            "gallery": [{"position": g["position"], "path": g["best_path"],
                         "resolution": "large" if g["large"] else "thumbnail" if g["thumbnail"] else "missing"}
                        for g in page["gallery"]],
        }
    catalog["item_page_research"] = {
        "source_repository": item_pages["source_repository"],
        "source_commit": item_pages["source_commit"],
        "source_zips": list(item_pages["archive_sha256"]),
        "individual_page_count": len(by_id),
        "missing_individual_page_ids": item_pages["missing_item_page_ids"],
        "status": "archived seller statements and images; live availability, authenticity and pricing not verified",
    }
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {len(by_id)} individual item pages + 1 profile-only listing")


if __name__ == "__main__":
    main()
