"""Offline provenance and completeness checks for the three additional item-page ZIPs."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ITEM_PAGES = json.loads((ROOT / "avito_audit/item_pages/data.json").read_text(encoding="utf-8"))
CATALOG = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))


class ItemPageTest(unittest.TestCase):
    def test_all_14_listings_with_13_separate_html_pages(self):
        pages = {p["id"]: p for p in ITEM_PAGES["items"]}
        catalog = {p["id"]: p for p in CATALOG["products"]}
        self.assertEqual(len(pages), 13)
        self.assertEqual(len(catalog), 14)
        self.assertEqual(ITEM_PAGES["missing_item_page_ids"], ["8350792227"])
        self.assertEqual(set(catalog) - set(pages), {"8350792227"})
        self.assertIsNone(catalog["8350792227"]["avito_item_page"])
        self.assertEqual(catalog["8350792227"]["avito_profile_excerpt"]["text"], "Для Дениса.")
        self.assertEqual(len(catalog["8350792227"]["photos"]), 1)
        self.assertEqual(set(ITEM_PAGES["archive_sha256"]), {"PART1_HTMLS.zip", "PART_2.zip", "PART3.zip"})
        for id_, page in pages.items():
            item = catalog[id_]
            summary = item["avito_item_page"]
            self.assertEqual(page["seller_profile_id"], "b2165ff5492372c90fab55f7223f9d3b")
            self.assertEqual(page["display_price_rub"], item["price_rub_snapshot"])
            self.assertEqual(page["item_url"], item["avito_url"])
            self.assertEqual(page["source"]["zip_file"], "PART1_HTMLS.zip")
            self.assertEqual(summary["description_ru_as_seller_claim"], page["seller_description_schema_ru"])
            self.assertEqual(summary["attributes_as_seller_claim"], page["attributes_as_saved"])
            self.assertEqual(summary["old_price_display_rub_snapshot"], page["old_price_display_rub"])
            self.assertEqual(summary["gallery_count"], len(page["gallery"]))
            self.assertEqual(len(summary["gallery"]), len(page["gallery"]))
            self.assertTrue(page["seller_description_schema_ru"])
            self.assertTrue(page["seller_description_html_ru"])

    def test_gallery_files_unmodified_and_source_scoped(self):
        positions = thumbs = large = missing = 0
        source_names = set()
        image_paths = set()
        for page in ITEM_PAGES["items"]:
            for expected_position, photo in enumerate(page["gallery"], 1):
                self.assertEqual(photo["position"], expected_position)
                self.assertTrue(photo["avito_share_url"].startswith("https://www.avito.ru/img/share/"))
                positions += 1
                if not photo["best_path"]:
                    missing += 1
                    self.assertIsNone(photo["thumbnail"])
                    self.assertIsNone(photo["large"])
                    self.assertEqual(page["id"], "8296456393")
                    self.assertTrue(photo["missing_thumbnail_url"].startswith("https://"))
                    continue
                self.assertEqual(photo["best_path"], (photo["large"] or photo["thumbnail"])["local_path"])
                for kind in ("thumbnail", "large"):
                    asset = photo[kind]
                    if asset is None:
                        continue
                    if kind == "thumbnail":
                        thumbs += 1
                    else:
                        large += 1
                    path = asset["local_path"]
                    self.assertNotIn(path, image_paths)
                    image_paths.add(path)
                    self.assertTrue(path.startswith(f"avito_audit/item_pages/images/{page['id']}/"))
                    self.assertEqual(asset["zip_file"] in {"PART_2.zip", "PART3.zip"}, True)
                    source_names.add(asset["zip_file"])
                    raw = (ROOT / path).read_bytes()
                    self.assertTrue(raw.startswith(b"\xff\xd8\xff") and raw.endswith(b"\xff\xd9"))
                    self.assertEqual(len(raw), asset["bytes"])
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), asset["sha256"])
                    self.assertTrue(all(x > 0 for x in asset["dimensions"]))
        self.assertEqual((positions, thumbs, large, missing), (75, 74, 38, 1))
        self.assertEqual(source_names, {"PART_2.zip", "PART3.zip"})
        on_disk = {str(p.relative_to(ROOT)) for p in (ROOT / "avito_audit/item_pages/images").rglob("*.jpg")}
        self.assertEqual(image_paths, on_disk)

    def test_visible_price_not_overwritten_by_schema_offer(self):
        mismatches = {p["id"] for p in ITEM_PAGES["items"]
                      if p["display_price_rub"] != p["schema_offer_price_rub"]}
        self.assertEqual(mismatches, {"7942160038", "7942010246", "7942405497",
                                      "8296456393", "7942108985", "8102096652"})
        for p in ITEM_PAGES["items"]:
            self.assertEqual(p["schema_offer_price_rub"], p["old_price_display_rub"] or p["display_price_rub"])
        # Do not treat four photographed Mission boxes as one identified SKU.
        self.assertEqual(next(p for p in CATALOG["products"] if p["id"] == "8296456393")["official"]["match_level"], "collection")
        self.assertEqual(next(p for p in CATALOG["products"] if p["id"] == "7942405497")["official"]["match_level"], "photo_variant")


if __name__ == "__main__":
    unittest.main()
