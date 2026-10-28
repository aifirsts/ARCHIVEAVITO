"""End-to-end offline checks across the legacy archive, new pages and static site."""
import csv
import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))



class RepositoryIntegrityTest(unittest.TestCase):
    def test_profile_snapshot_csv_and_catalog_agree(self):
        snapshot = load("avito_audit/snapshot.json")
        catalog = load("catalog.json")
        items = {item["id"]: item for item in catalog["products"]}
        with (ROOT / "avito_audit/products.csv").open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 14)
        self.assertEqual({row["id"] for row in rows}, set(items))
        self.assertEqual({item["id"] for item in snapshot["items"]}, set(items))
        for original in snapshot["items"]:
            item = items[original["id"]]
            for source_key, catalog_key in (
                ("title", "title"), ("url", "avito_url"),
                ("price_rub", "price_rub_snapshot"),
                ("old_price_text", "old_price_text_snapshot"),
                ("discount_text", "discount_text_snapshot"),
                ("location", "location_snapshot"),
                ("date_display", "date_display_snapshot"),
            ):
                self.assertEqual(original[source_key], item[catalog_key], original["id"])

    def test_every_old_profile_preview_matches_manifest(self):
        manifest = load("avito_audit/images_manifest.json")
        items = {item["id"]: item for item in load("catalog.json")["products"]}
        self.assertEqual(len(manifest), 55)
        expected_paths = set()
        missing = 0
        for entry in manifest:
            local = entry["local_path"]
            if not local:
                missing += 1
                self.assertEqual(entry["listing_id"], "8296456393")
                continue
            path = ROOT / "avito_audit" / local
            expected_paths.add(path)
            self.assertTrue(path.is_file(), path)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry["sha256"])
            self.assertEqual(
                items[entry["listing_id"]]["photos"][entry["position_in_saved_html"] - 1],
                str(path.relative_to(ROOT)),
            )
        self.assertEqual((len(expected_paths), missing), (53, 2))
        self.assertEqual(expected_paths, set((ROOT / "avito_audit/images").glob("*/*.jpg")))

    def test_all_local_documentation_links_resolve(self):
        for file in ROOT.rglob("*.md"):
            if ".git" in file.parts:
                continue
            for target in re.findall(r"(?<!\[)\[[^\]]+\]\(([^)]+)\)", file.read_text(encoding="utf-8")):
                if not target.startswith(("http:", "https:", "mailto:", "#")):
                    self.assertTrue((file.parent / target.split("#")[0]).exists(), f"{file}: {target}")



if __name__ == "__main__":
    unittest.main()
