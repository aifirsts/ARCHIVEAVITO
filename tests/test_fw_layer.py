"""Checks for the 2026-10-28 seller-message layer (8th source ZIP).

The layer must stay traceable: every decoded text and photo on disk matches the
mechanical manifest, the curated catalog layer matches that manifest, and the
built site renders the fresh prices as a clearly separated layer that is never
mixed with archived prices.
"""

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FW_DIR = ROOT / "avito_audit" / "attachments_fw_2026_10_28"
MANIFEST = json.loads((FW_DIR / "manifest.json").read_text(encoding="utf-8"))
CATALOG = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
LAYER = CATALOG["seller_messages_2026_10_28"]
FEED = json.loads((ROOT / "handoff/storefront.json").read_text(encoding="utf-8"))
PUBLIC = ROOT / "site" / "public"

EXPECTED_OFFERS = {
    "the-max-creme-48g": 11500,
    "the-max-eye-creme-15ml": 6800,
    "daily-prevention-spf30": 4900,
    "md-biotech-longevity-creme-50g": 10400,
    "md-restoring-power-c-serum-30ml": 11500,
}


class FwManifestTest(unittest.TestCase):
    def test_zip_identity(self):
        self.assertEqual(MANIFEST["archive_sha256"], LAYER["zip_sha256"])
        self.assertEqual(MANIFEST["archive_bytes"], LAYER["zip_bytes"])
        self.assertEqual(MANIFEST["source_commit"], LAYER["source_commit"])
        self.assertEqual(MANIFEST["entries_count"], 10)
        self.assertEqual(len(MANIFEST["messages"]) + len(MANIFEST["photos"]), 10)

    def test_decoded_files_match_manifest(self):
        for message in MANIFEST["messages"]:
            path = FW_DIR / message["decoded_file"]
            self.assertTrue(path.is_file(), message["decoded_file"])
            self.assertEqual(path.read_text(encoding="utf-8"), message["text"])
            self.assertIn("Алина Зуева", message["text"])
        for photo in MANIFEST["photos"]:
            path = FW_DIR / photo["saved_file"]
            self.assertTrue(path.is_file(), photo["saved_file"])
            data = path.read_bytes()
            self.assertEqual(len(data), photo["bytes"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), photo["sha256"])
            self.assertEqual(data[:3], b"\xff\xd8\xff")

    def test_catalog_layer_photos_are_audited(self):
        by_entry = {p["source_entry"]: p for p in MANIFEST["photos"]}
        for photo in LAYER["photos"]:
            mech = by_entry[photo["source_entry"]]
            path = ROOT / photo["path"]
            self.assertTrue(path.is_file(), photo["path"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), mech["sha256"])
            self.assertEqual(photo["dimensions"], mech["dimensions"])

    def test_offers_quote_real_messages(self):
        entries = {m["source_entry"] for m in MANIFEST["messages"]}
        for offer in LAYER["offers"]:
            self.assertIn(offer["offer_id"], EXPECTED_OFFERS)
            self.assertEqual(offer["price_rub_claimed"], EXPECTED_OFFERS[offer["offer_id"]])
            self.assertIn(offer["price_message_file"], entries)
            self.assertIn(offer["description_message_file"], entries)
            for photo_path in offer["photo_paths"]:
                self.assertTrue((ROOT / photo_path).is_file(), photo_path)
        matched = {o["matches_catalog_id"] for o in LAYER["offers"] if o["matches_catalog_id"]}
        self.assertEqual(matched, {"8166255881", "8230842563"})

    def test_per_product_notes_match_offers(self):
        products = {p["id"]: p for p in CATALOG["products"]}
        for pid, note in (
            ("8166255881", products["8166255881"]["seller_message_2026_10_28"]),
            ("8230842563", products["8230842563"]["seller_message_2026_10_28"]),
        ):
            offer = [o for o in LAYER["offers"] if o["matches_catalog_id"] == pid][0]
            self.assertEqual(note["price_rub_claimed"], offer["price_rub_claimed"])
            self.assertEqual(note["price_quote_ru"], offer["price_quote_ru"])
        # No other product may carry the layer.
        for product in CATALOG["products"]:
            if product["id"] not in {"8166255881", "8230842563"}:
                self.assertNotIn("seller_message_2026_10_28", product)


class FwSiteTest(unittest.TestCase):
    def test_feed_carries_layer(self):
        fw = FEED["seller_messages_2026_10_28"]
        self.assertEqual(len(fw["offers"]), 5)
        for photo in fw["photos"]:
            self.assertTrue((ROOT / photo["path"]).is_file(), photo["path"])

    def test_index_renders_offers_layer(self):
        index = (PUBLIC / "index.html").read_text(encoding="utf-8")
        self.assertIn("Предложения продавца из сообщений от 28.10.2026", index)
        self.assertIn("Это не архивные объявления", index)
        for price in ("11\u202f500\u00a0₽", "6\u202f800\u00a0₽", "4\u202f900\u00a0₽",
                      "10\u202f400\u00a0₽"):
            self.assertIn(price, index)
        self.assertIn("assets/img/seller-2026-10-28/sellermsg-01.jpg", index)
        self.assertIn("assets/img/seller-2026-10-28/sellermsg-03.jpg", index)
        self.assertIn('href="item/8166255881.html"', index)
        self.assertIn('href="item/8230842563.html"', index)

    def test_matched_products_show_fresh_price(self):
        for pid, fresh, archived in (("8166255881", "4\u202f900\u00a0₽", "5\u202f900\u00a0₽"),
                                     ("8230842563", "10\u202f400\u00a0₽", "12\u202f999\u00a0₽")):
            page = (PUBLIC / "item" / f"{pid}.html").read_text(encoding="utf-8")
            self.assertIn("Сообщение продавца · 28.10.2026", page)
            self.assertIn(fresh, page)
            self.assertIn(archived, page)
            self.assertIn("к архивной", page)
        untouched = (PUBLIC / "item" / "7942405497.html").read_text(encoding="utf-8")
        self.assertNotIn("Сообщение продавца · 28.10.2026", untouched)

    def test_fresh_photos_published(self):
        images = json.loads((PUBLIC / "assets" / "images.json").read_text(encoding="utf-8"))
        published = {record["public_path"] for record in images["images"]}
        for number in (1, 2, 3):
            self.assertIn(f"assets/img/seller-2026-10-28/sellermsg-0{number}.jpg", published)
        for record in images["images"]:
            if record["public_path"].startswith("assets/img/seller-2026-10-28/"):
                self.assertEqual(record["transform"], "copy")
                self.assertEqual(record["published_sha256"], record["source_sha256"])
                self.assertTrue(record["source_path"].startswith(
                    "avito_audit/attachments_fw_2026_10_28/"))

    def test_sources_page_documents_the_layer(self):
        sources = (PUBLIC / "sources.html").read_text(encoding="utf-8")
        self.assertIn("Attachments-Fw_ 27.10 avito.zip", sources)
        self.assertIn("216adc3cb760c13c5ea85da0a8cf0a5baf9ecb51748ec4619ad4c456bcbc349c", sources)
        self.assertIn("Сообщения 28.10.2026", sources)
        self.assertIn("не объединяется", sources)


if __name__ == "__main__":
    unittest.main()
