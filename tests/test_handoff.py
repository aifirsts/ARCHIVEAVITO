"""The next-site data feed is deterministic, complete, and keeps sources separate."""
import hashlib
import json
import unittest
from pathlib import Path

from handoff.generate import build_document, render

ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / "handoff/storefront.json"


class HandoffTest(unittest.TestCase):
    def test_feed_reproducible_and_archival(self):
        saved = FEED.read_text(encoding="utf-8")
        self.assertEqual(saved, render(build_document()))
        data = json.loads(saved)
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["status"], "archived_research_not_live_inventory")
        self.assertEqual(data["archive_date"], "2026-10-26")
        self.assertEqual(data["paths_relative_to"], "repository_root")
        self.assertEqual(set(data["source_archives_sha256"]),
                         {"Авито 14.zip", "PART1_HTMLS.zip", "PART_2.zip", "PART3.zip",
                          "ДОЗАГРУЗКА.zip", "Чехол_ЧАСЫ _ Авито (8102096652)_files.zip",
                          "Attachments-Avitos.zip", "Attachments-Fw_ 27.10 avito.zip"})
        self.assertEqual(data["seller_profile_from_archive"]["id"],
                         "b2165ff5492372c90fab55f7223f9d3b")
        products = {p["id"]: p for p in data["products"]}
        self.assertEqual(len(products), 14)
        self.assertFalse(products["8350792227"]["archived_listing"]["individual_page_saved"])
        self.assertIsNone(products["8350792227"]["archived_listing"]["seller_description_normalized"])
        self.assertEqual(len(products["8350792227"]["media"]["profile_previews"]), 1)
        self.assertTrue(products["8102096652"]["archived_listing"]["individual_page_saved"])
        watch = products["8296456393"]["media"]["listing_gallery"]
        self.assertEqual([g["position"] for g in watch], list(range(1, 9)))
        self.assertTrue(watch[3]["remote_url_only"])
        self.assertIsNone(watch[3]["thumbnail"])
        self.assertIsNone(watch[3]["large"])
        self.assertTrue(watch[3]["missing_remote_url_for_audit"].startswith("https://"))
        self.assertIsNone(products["8296456393"]["media"]["manufacturer_illustration"])
        supplemental = data["supplemental_sources"]["Attachments-Avitos.zip"]
        self.assertEqual(supplemental["sha256"],
                         "7d1eca79385ba06d702f0812eca8b5ee70990295295ec2b06442a28e33b5d6d0")
        self.assertEqual(supplemental["source_commit"], "cf1c74b4a623ad22e7cedd5180aee98571261b1b")
        self.assertEqual(supplemental["entries"], 10)
        fw = data["seller_messages_2026_10_28"]
        self.assertEqual(fw["sha256"],
                         "216adc3cb760c13c5ea85da0a8cf0a5baf9ecb51748ec4619ad4c456bcbc349c")
        self.assertEqual(fw["source_commit"], "68d7c1f7cb99d3f47a4159bf3ff93d80b194e8fe")
        self.assertEqual(fw["entries"], 10)
        self.assertEqual(fw["status"], "seller_claims_2026_10_28_not_verified_live")
        self.assertEqual(len(fw["offers"]), 5)
        self.assertEqual(len(fw["photos"]), 3)
        self.assertEqual(set(fw["price_updates_for_catalog"]),
                         {"8166255881", "8230842563"})
        self.assertEqual(fw["price_updates_for_catalog"]["8166255881"],
                         {"price_rub_claimed": 4900, "archived_price_rub": 5900})
        self.assertEqual(fw["price_updates_for_catalog"]["8230842563"],
                         {"price_rub_claimed": 10400, "archived_price_rub": 12999})
        for product in data["products"]:
            note = product.get("seller_message_2026_10_28")
            if note:
                self.assertIn(product["id"], fw["price_updates_for_catalog"])
                self.assertTrue(note["photo_path"].startswith(
                    "avito_audit/attachments_fw_2026_10_28/"))
        # The Power-C serum must not be merged with the archived Restoring Youth listing.
        serum = next(o for o in fw["offers"] if o["offer_id"] == "md-restoring-power-c-serum-30ml")
        self.assertIsNone(serum["matches_catalog_id"])
        self.assertIn("8165960870", serum["note_ru"])

    def test_new_layer_fills_watch_slot_4_and_case_photo(self):
        data = json.loads(FEED.read_text(encoding="utf-8"))
        products = {p["id"]: p for p in data["products"]}
        crops = products["8296456393"]["media"]["mobile_gallery_crops_2026_10_25"]
        self.assertEqual([c["gallery_position_in_badge"] for c in crops], list(range(1, 9)))
        fourth = crops[3]
        self.assertIsNone(fourth["visually_confirmed_saved_slot"])
        self.assertTrue(fourth["asset"]["path"].endswith("mobile_gallery_04.png"))
        self.assertEqual(fourth["asset"]["dimensions"], [1170, 1644])
        self.assertTrue(fourth["badge_evidence"]["path"].endswith("mobile_gallery_04_header.png"))
        self.assertTrue(fourth["badge_evidence"]["sha256"])
        # Positions that already had a 720x960 copy are not duplicated on disk.
        for index in (0, 1, 7):
            self.assertIsNone(crops[index]["asset"])
            self.assertIn("дубликат", crops[index]["not_stored_reason_ru"])
        case = products["8350792227"]
        photo = case["media"]["page_print_photo_2026_10_25"]
        self.assertEqual(photo["dimensions"], [550, 960])
        self.assertEqual(photo["embedded_name"], "Im6.png")
        self.assertEqual(case["media"]["listing_gallery"], [])
        self.assertFalse(case["archived_listing"]["individual_page_saved"])
        self.assertEqual(case["archived_listing"]["price_rub"], 1116)
        print_note = case["supplemental_2026_10_25"]["page_print_snapshot"]
        self.assertEqual(print_note["stock_status_text"], "Товар зарезервирован")
        self.assertEqual(print_note["gallery_photos_on_page"], 1)
        self.assertEqual(set(case["supplemental_2026_10_25"]["do_not_merge_with"]),
                         {"id", "reason_ru"})
        self.assertFalse(products["8102096652"]["archived_listing"]["individual_page_saved"] is None)

    def test_media_paths_local_and_complete(self):
        data = json.loads(FEED.read_text(encoding="utf-8"))
        positions = thumbnails = large = profile = official = 0
        paths = []
        for product in data["products"]:
            media = product["media"]
            for g in media["listing_gallery"]:
                positions += 1
                for field in ("thumbnail", "large"):
                    image = g[field]
                    if image is not None:
                        thumbnails += field == "thumbnail"
                        large += field == "large"
                        paths.append(image)
            for g in media["profile_previews"]:
                profile += 1
                paths.append(g["asset"])
            if media["manufacturer_illustration"] is not None:
                official += 1
                paths.append(media["manufacturer_illustration"])
            for crop in media["mobile_gallery_crops_2026_10_25"]:
                if crop["asset"] is not None:
                    paths.append(crop["asset"])
                paths.append(crop["badge_evidence"])
            if media["page_print_photo_2026_10_25"] is not None:
                paths.append(media["page_print_photo_2026_10_25"])
        self.assertEqual((positions, thumbnails, large, profile, official), (75, 74, 38, 53, 13))
        # 178 archive assets + 8 badge crops + 5 stored new frames + 1 page-print photo
        self.assertEqual(len(paths), 192)
        self.assertEqual(len({entry["path"] for entry in paths}), 192)
        for entry in paths:
            self.assertFalse(entry["path"].startswith(("http:", "https:", "/")))
            self.assertNotIn("..", Path(entry["path"]).parts)
            blob = (ROOT / entry["path"]).read_bytes()
            self.assertEqual(len(blob), entry["bytes"])
            self.assertEqual(hashlib.sha256(blob).hexdigest(), entry["sha256"])


if __name__ == "__main__":
    unittest.main()
