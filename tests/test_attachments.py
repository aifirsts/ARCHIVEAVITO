"""Offline checks for the Attachments-Avitos.zip layer.

The archive itself is not stored in the repository, so these tests validate the
recorded manifest, the extracted crops and their provenance links.
"""

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads(
    (ROOT / "avito_audit/attachments_avitos/manifest.json").read_text(encoding="utf-8")
)
CATALOG = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
FEED = json.loads((ROOT / "handoff/storefront.json").read_text(encoding="utf-8"))
BY_ID = {p["id"]: p for p in CATALOG["products"]}
FEED_BY_ID = {p["id"]: p for p in FEED["products"]}


class AttachmentsManifestTest(unittest.TestCase):
    def test_archive_fingerprint_is_pinned(self):
        self.assertEqual(MANIFEST["archive_file"], "Attachments-Avitos.zip")
        self.assertEqual(
            MANIFEST["archive_sha256"],
            "7d1eca79385ba06d702f0812eca8b5ee70990295295ec2b06442a28e33b5d6d0",
        )
        self.assertEqual(MANIFEST["archive_bytes"], 16396636)
        self.assertEqual(MANIFEST["source_commit"], "cf1c74b4a623ad22e7cedd5180aee98571261b1b")
        self.assertEqual(MANIFEST["status"], "archival_research_only_not_live_inventory")

    def test_entries_are_listed_and_safe(self):
        entries = MANIFEST["entries"]
        self.assertEqual(len(entries), MANIFEST["entries_count"])
        self.assertEqual(MANIFEST["entries_count"], 10)
        names = {entry["name"] for entry in entries}
        self.assertEqual(len(names), len(entries), "duplicate ZIP entry names")
        for entry in entries:
            self.assertFalse(entry["name"].startswith("/"))
            self.assertNotIn("..", Path(entry["name"]).parts)
            self.assertIn(entry["kind"], {"image", "pdf"})
            self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
        kinds = sorted(entry["kind"] for entry in entries)
        self.assertEqual(kinds, ["image"] * 8 + ["pdf"] * 2)
        self.assertEqual(MANIFEST["safety"]["nested_archives"], [])
        self.assertEqual(MANIFEST["safety"]["html_or_js_entries"], [])
        self.assertFalse(MANIFEST["safety"]["pdf_javascript"])
        self.assertFalse(MANIFEST["safety"]["pdf_embedded_files"])
        self.assertTrue(MANIFEST["safety"]["nothing_executed"])
        self.assertEqual(MANIFEST["safety"]["problems"], [])
        self.assertEqual(MANIFEST["expected_entries_missing"], [])
        self.assertEqual(MANIFEST["unexpected_entries"], [])

    def test_entry_hashes_unique_and_unseen_before(self):
        entries = MANIFEST["entries"]
        hashes = [entry["sha256"] for entry in entries]
        self.assertEqual(len(set(hashes)), len(hashes))
        self.assertTrue(MANIFEST["duplicate_report"]["zip_entry_hashes_unique"])
        self.assertEqual(MANIFEST["duplicate_report"]["entry_hashes_found_in_other_manus1_zips"], [])

    def test_screenshots_cover_positions_1_to_8_of_the_watch_gallery(self):
        shots = MANIFEST["mobile_screenshots"]
        self.assertEqual(len(shots), 8)
        self.assertEqual([s["gallery_position_in_badge"] for s in shots], list(range(1, 9)))
        for shot in shots:
            self.assertEqual(shot["listing_id"], 8296456393)
            self.assertEqual(shot["entry_sha256"], next(
                e["sha256"] for e in MANIFEST["entries"] if e["name"] == shot["entry"]
            ))
            header = ROOT / shot["header_evidence_crop"]["path"]
            self.assertTrue(header.is_file(), header)
            self.assertEqual(
                hashlib.sha256(header.read_bytes()).hexdigest(),
                shot["header_evidence_crop"]["sha256"],
            )
            self.assertEqual(shot["header_evidence_crop"]["dimensions"], [1170, 117])
            crop = shot["photo_crop"]
            if crop["stored"]:
                path = ROOT / crop["path"]
                self.assertTrue(path.is_file(), path)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), crop["derived_sha256"])
                self.assertEqual(crop["dimensions"], [1170, 1644])
            else:
                self.assertIsNone(crop["path"])
                self.assertIn("дубликат", crop["not_stored_reason_ru"])
        # positions 3,5,6,7 only had 150x110 thumbnails; 4 had no file at all
        self.assertEqual([s["photo_crop"]["stored"] for s in shots],
                         [False, False, True, True, True, True, True, False])
        fourth = shots[3]
        self.assertIsNone(fourth["visually_confirmed_saved_slot"])
        self.assertEqual(fourth["entry"], "IMG_1181.png")
        self.assertTrue(fourth["photo_crop"]["path"].endswith("mobile_gallery_04.png"))

    def test_page_print_facts_are_asserted_against_extracted_text(self):
        listings = {item["id"]: item for item in MANIFEST["listings"]}
        self.assertEqual(set(listings), {8296456393, 8350792227})
        self.assertGreaterEqual(listings[8350792227]["evidence_assertions_checked"], 10)
        self.assertGreaterEqual(listings[8296456393]["evidence_assertions_checked"], 5)
        case = listings[8350792227]
        self.assertEqual(case["display_price_text"], "1 116 ₽")
        self.assertEqual(case["stock_status_text"], "Товар зарезервирован")
        self.assertEqual(case["description_text"], "Для Дениса")
        self.assertEqual(case["gallery_photos_saved_in_print"], 1)
        self.assertEqual(case["page_print_creation_date_utc"], "2026-10-25T22:15:26Z")
        watches = listings[8296456393]
        self.assertEqual(watches["gallery_badge_text"], "1 из 9")
        self.assertEqual(watches["gallery_position_count"], 9)
        self.assertEqual(watches["page_print_creation_date_utc"], "2026-10-25T22:11:16Z")

    def test_pdf_images_classified_and_ads_excluded(self):
        records = MANIFEST["pdf_embedded_images"]
        roles = [r["role"] for r in records]
        self.assertIn("advertisement", roles)
        self.assertIn("avatar", roles)
        self.assertIn("recommendation", roles)
        self.assertIn("interface_glyph", roles)
        gallery = [r for r in records if r["role"] == "gallery"]
        self.assertTrue(gallery)
        for record in records:
            self.assertIn("reason_ru", record)
            if record["role"] in {"advertisement", "avatar", "recommendation", "ui", "interface_glyph"}:
                self.assertIsNone(record.get("stored_path"))
        stored = [r for r in records if r.get("stored_path")]
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["pdf_entry"].endswith("(8350792227).pdf"), True)
        path = ROOT / stored[0]["stored_path"]
        self.assertTrue(path.is_file())
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), stored[0]["stored_sha256"])
        self.assertEqual(stored[0]["dimensions"], [550, 960])

    def test_published_assets_listed(self):
        published = MANIFEST["web_publication"]["published_from_this_archive"]
        self.assertEqual(len(published), MANIFEST["kept_files"] - 8)  # 8 badge crops are evidence, not published photos
        for rel in published:
            self.assertTrue((ROOT / rel).is_file(), rel)
        excluded = MANIFEST["web_publication"]["excluded_from_publication"]
        self.assertGreater(len(excluded), 10)
        self.assertNotIn("not_classified", {e["role"] for e in excluded if e.get("role") == "gallery"})


class AttachmentsCatalogLinkTest(unittest.TestCase):
    def test_catalog_and_feed_point_to_the_same_new_files(self):
        for pid in ("8296456393", "8350792227"):
            note = BY_ID[pid]["supplemental_2026_10_25"]
            self.assertEqual(note["kind"] in {"mobile_screenshot_gallery", "pdf_page_print"}, True)
            feed_product = FEED_BY_ID[pid]
            self.assertEqual(feed_product["supplemental_2026_10_25"]["kind"], note["kind"])

        watches = FEED_BY_ID["8296456393"]["media"]["mobile_gallery_crops_2026_10_25"]
        self.assertEqual(len(watches), 8)
        new_asset = watches[3]["asset"]
        self.assertEqual(new_asset["path"],
                         "avito_audit/attachments_avitos/images/8296456393/mobile_gallery_04.png")
        self.assertEqual(hashlib.sha256((ROOT / new_asset["path"]).read_bytes()).hexdigest(),
                         new_asset["sha256"])

        case = FEED_BY_ID["8350792227"]["media"]["page_print_photo_2026_10_25"]
        self.assertEqual(case["path"],
                         "avito_audit/attachments_avitos/images/8350792227/page_print_photo_01.png")

    def test_watch_gallery_still_has_one_remote_slot(self):
        gallery = FEED_BY_ID["8296456393"]["media"]["listing_gallery"]
        self.assertEqual([g["position"] for g in gallery], list(range(1, 9)))
        remote = [g for g in gallery if g["remote_url_only"]]
        self.assertEqual([g["position"] for g in remote], [4])
        # the archived HTML slot 4 stays empty: the new evidence is a separate layer,
        # and it never claims to be the original file URL
        self.assertIsNone(remote[0]["thumbnail"])
        self.assertTrue(remote[0]["missing_remote_url_for_audit"].startswith("https://"))

    def test_case_listing_is_not_merged_with_the_single_case(self):
        case = FEED_BY_ID["8350792227"]
        other = FEED_BY_ID["8102096652"]
        self.assertEqual(case["archived_listing"]["price_rub"], 1116)
        self.assertEqual(other["archived_listing"]["price_rub"], 557)
        self.assertFalse(case["archived_listing"]["individual_page_saved"])
        self.assertIsNone(case["archived_listing"]["seller_description_normalized"])
        self.assertEqual(len(case["media"]["profile_previews"]), 1)
        self.assertEqual(case["supplemental_2026_10_25"]["do_not_merge_with"]["id"], "8102096652")
        self.assertNotEqual(case["avito_url"], other["avito_url"])

    @staticmethod
    def norm(text):
        return " ".join(str(text).replace("\u00a0", " ").split())

    def test_archive_values_are_not_overwritten(self):
        case = FEED_BY_ID["8350792227"]
        # archived price/status captured in the HTML snapshot must survive next to the
        # newer PDF print layer
        self.assertEqual(case["archived_listing"]["price_rub"], 1116)
        self.assertEqual(self.norm(case["archived_listing"]["old_price_text"]), "1 200 ₽")
        self.assertEqual(case["archived_listing"]["stock_badge_text"], None)
        print_snapshot = case["supplemental_2026_10_25"]["page_print_snapshot"]
        self.assertEqual(self.norm(print_snapshot["display_price_text"]), "1 116 ₽")
        self.assertEqual(print_snapshot["stock_status_text"], "Товар зарезервирован")
        watches = FEED_BY_ID["8296456393"]
        self.assertIsNone(watches["archived_listing"]["stock_badge_text"])
        self.assertEqual(watches["archived_listing"]["item_page_views_text"], "371 просмотр")
        self.assertEqual(watches["supplemental_2026_10_25"]["page_print_snapshot"]["views_text"],
                         "373 просмотра")


if __name__ == "__main__":
    unittest.main()
