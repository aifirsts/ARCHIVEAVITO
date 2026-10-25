"""Offline checks for the archival catalog and manufacturer-image provenance."""
import hashlib
import json
from pathlib import Path
import unittest
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
MANIFEST = json.loads((ROOT / "official_assets/manifest.json").read_text(encoding="utf-8"))


class CatalogTest(unittest.TestCase):
    def test_all_archived_products_and_photos(self):
        products = CATALOG["products"]
        self.assertEqual(len(products), 14)
        self.assertEqual(len({p["id"] for p in products}), 14)
        self.assertEqual(sum(len(p["photos"]) for p in products), 53)
        for product in products:
            self.assertTrue(product["photos"])
            for photo in product["photos"]:
                self.assertTrue((ROOT / photo).is_file(), photo)
            official = product["official"]
            self.assertEqual(official["url"], official["details"]["source_url"])
            self.assertEqual(urlparse(official["url"]).scheme, "https")
            self.assertTrue(official["details"]["specifications_ru"])
            self.assertTrue(official["details"]["use_ru"])
            self.assertTrue(official["verification_note_ru"])

    def test_images_verified_and_separate_from_archive(self):
        by_id = {p["id"]: p for p in CATALOG["products"]}
        items = MANIFEST["items"]
        self.assertEqual(len(items), 13)
        self.assertEqual(len({i["avito_id"] for i in items}), 13)
        for item in items:
            image = ROOT / item["local_path"]
            self.assertTrue(image.is_file(), image)
            self.assertTrue(item["local_path"].startswith("official_assets/"))
            self.assertEqual(image.stat().st_size, item["bytes"])
            self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(), item["sha256"])
            self.assertEqual(by_id[item["avito_id"]]["official"]["photos"], [item["local_path"]])
            self.assertEqual(by_id[item["avito_id"]]["official"]["url"], item["official_product_page"])
            self.assertIn(urlparse(item["official_asset_example_url"]).hostname,
                          {"www.hourglasscosmetics.com", "images.ctfassets.net",
                           "speckproducts.com", "imageskincare.com"})
        watch = by_id["8296456393"]["official"]
        self.assertEqual(watch["photos"], [])
        self.assertTrue(watch["image_unavailable_note_ru"])


if __name__ == "__main__":
    unittest.main()
