"""The next-site data feed is deterministic, complete, and keeps sources separate."""
import hashlib
import json
from pathlib import Path
import unittest

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
                         {"Авито 14.zip", "PART1_HTMLS.zip", "PART_2.zip", "PART3.zip"})
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
        self.assertEqual((positions, thumbnails, large, profile, official), (75, 74, 38, 53, 13))
        self.assertEqual(len(paths), 178)
        self.assertEqual(len({entry["path"] for entry in paths}), 178)
        for entry in paths:
            self.assertFalse(entry["path"].startswith(("http:", "https:", "/")))
            self.assertNotIn("..", Path(entry["path"]).parts)
            blob = (ROOT / entry["path"]).read_bytes()
            self.assertEqual(len(blob), entry["bytes"])
            self.assertEqual(hashlib.sha256(blob).hexdigest(), entry["sha256"])


if __name__ == "__main__":
    unittest.main()
