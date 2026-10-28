"""Offline checks for the generated public storefront (``site/public``).

These tests do not need a browser: they verify structure, links, accessibility
contracts in markup, image integrity, and that nothing from the research layer
(reviews, research JSON, source ZIPs) leaked into the web root.
"""

import hashlib
import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "site" / "public"
FEED = json.loads((ROOT / "handoff/storefront.json").read_text(encoding="utf-8"))
IMAGES = json.loads((PUBLIC / "assets" / "images.json").read_text(encoding="utf-8"))
PRODUCT_IDS = sorted(p["id"] for p in FEED["products"])
PAGES = IMAGES["product_pages"]


def page_of(product_id: str) -> Path:
    """Public page path for a listing id (SEO slugs live in the build manifest)."""
    return PUBLIC / PAGES[product_id]


def product_page_text(product_id: str) -> str:
    return page_text(page_of(product_id))


class Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []
        self.srcs = []
        self.imgs = []
        self.ids = set()
        self.lang = None
        self.labels = 0
        self.title = None
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "html":
            self.lang = attrs.get("lang")
        if tag == "label":
            self.labels += 1
        if tag == "a" and attrs.get("href"):
            self.hrefs.append(attrs["href"])
        if tag == "img":
            self.imgs.append(attrs)
            if attrs.get("src"):
                self.srcs.append(attrs["src"])
        if tag in {"script", "link"} and attrs.get("src"):
            self.srcs.append(attrs["src"])
        if tag in {"script", "link"} and attrs.get("href"):
            self.srcs.append(attrs["href"])
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title = data.strip()


def parse(path: Path) -> Refs:
    parser = Refs()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def page_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return re.sub(r"\s+", " ", text.replace("\u00a0", " "))


class SiteStructureTest(unittest.TestCase):
    def test_pages_exist_for_every_listing(self):
        self.assertTrue((PUBLIC / "index.html").is_file())
        self.assertTrue((PUBLIC / "sources.html").is_file())
        pages = sorted(p.name for p in (PUBLIC / "item").glob("*.html"))
        self.assertEqual(pages, sorted(p.split("/")[-1] for p in PAGES.values()))
        self.assertEqual(IMAGES["products"], 14)
        self.assertEqual(len(IMAGES["pages"]), 18)
        for required in ("podbor.html", "404.html", "robots.txt", "sitemap.xml", "CNAME"):
            self.assertTrue((PUBLIC / required).is_file(), required)
        # every slug must be unique and ASCII-only so the URLs stay shareable
        for product_id, page in PAGES.items():
            self.assertTrue(product_id in page)
            self.assertEqual(page, page.encode("ascii", "ignore").decode())

    def test_catalogue_lists_all_cards_once(self):
        html = (PUBLIC / "index.html").read_text(encoding="utf-8")
        cards = re.findall(r'data-card data-id="(\d+)"', html)
        self.assertEqual(sorted(cards), PRODUCT_IDS)
        self.assertEqual(len(cards), len(set(cards)))

    def test_local_links_and_assets_resolve(self):
        for page in sorted(PUBLIC.rglob("*.html")):
            refs = parse(page)
            self.assertEqual(refs.lang, "ru", page.name)
            self.assertTrue(refs.title, f"{page.name}: нет <title>")
            targets = refs.hrefs + refs.srcs
            text = page.read_text(encoding="utf-8")
            targets += re.findall(r'data-src="([^"]+)"', text)
            for target in targets:
                if not target or target.startswith(("http://", "https://", "mailto:", "data:", "#")):
                    continue
                base = target.split("#")[0].split("?")[0]
                self.assertTrue((page.parent / base).resolve().exists(), f"{page.name}: {target}")

    def test_images_have_alt_text(self):
        for page in sorted(PUBLIC.rglob("*.html")):
            for img in parse(page).imgs:
                self.assertIn("alt", img, f"{page.name}: <img> без alt — {img.get('src')}")
            # decorative gallery thumbnails may use empty alt, real photos may not
        product = parse(page_of("8296456393"))
        alts = [img.get("alt", "") for img in product.imgs]
        self.assertTrue(any("Оригинальные часы" in alt for alt in alts))

    def test_accessibility_contracts_in_markup(self):
        index = (PUBLIC / "index.html").read_text(encoding="utf-8")
        self.assertIn('class="skip-link" href="#main"', index)
        self.assertIn('id="main"', index)
        self.assertIn('role="status" aria-live="polite"', index)
        self.assertIn('role="search"', index)
        self.assertIn('aria-pressed="true"', index)
        self.assertIn("<legend>Категория</legend>", index)
        item = page_of("8296456393").read_text(encoding="utf-8")
        self.assertIn('aria-roledescription="галерея"', item)
        self.assertIn("<dialog", item)
        self.assertIn('data-gallery-thumb', item)
        self.assertIn("visually-hidden", item)

    def test_no_research_layer_in_web_root(self):
        published = {p.name for p in PUBLIC.iterdir()}
        self.assertEqual(published, {"index.html", "podbor.html", "sources.html", "404.html", "item",
                                     "assets", "favicon.svg", "favicon.ico", ".nojekyll",
                                     "robots.txt", "sitemap.xml", "site.webmanifest", "CNAME"})
        for pattern in ("*.json", "*.zip", "*.md", "*.py"):
            for path in PUBLIC.rglob(pattern):
                self.assertEqual(path.relative_to(PUBLIC).as_posix(), "assets/images.json")
        for forbidden in ("snapshot.json", "data.json", "storefront.json", "products.csv"):
            self.assertFalse((PUBLIC / forbidden).exists(), forbidden)
        # reviews from the profile snapshot must not appear on the site
        snapshot = json.loads((ROOT / "avito_audit/snapshot.json").read_text(encoding="utf-8"))
        reviews = snapshot.get("reviews") or []
        texts = [page_text(p) for p in (PUBLIC / "item").glob("*.html")] + [
            page_text(PUBLIC / "index.html"),
            page_text(PUBLIC / "podbor.html"),
        ]
        for review in reviews:
            author = (review.get("author") or "").strip() if isinstance(review, dict) else ""
            if len(author) > 3:
                for text in texts:
                    self.assertNotIn(author, text)

    def test_prices_are_labelled_as_archive(self):
        for pid in PRODUCT_IDS:
            text = product_page_text(pid)
            self.assertIn("архив", text.lower(), pid)
            self.assertIn("не текущая", text, pid)
            feed_product = next(p for p in FEED["products"] if p["id"] == pid)
            self.assertIn(feed_product["avito_url"], page_of(pid).read_text(encoding="utf-8"))
            self.assertNotIn("<form action", page_of(pid).read_text(encoding="utf-8").lower())
        for pid in PRODUCT_IDS:
            text = product_page_text(pid)
            for promise in ("оплатить картой", "оформить заказ", "доставка за", "в наличии — да"):
                self.assertNotIn(promise, text.lower())

    def test_watch_missing_slot_and_case_limits_are_visible(self):
        watches = product_page_text("8296456393")
        self.assertIn("позиции № 9", watches)
        self.assertIn("9 фотографий", watches)
        self.assertIn("кадр 4", watches.lower())
        case = product_page_text("8350792227")
        self.assertIn("Второй чехол", case)
        self.assertIn("8102096652", case)
        self.assertNotIn("Speck Presidio2 Pro — iPhone 15 Pro Max (2 шт)", page_of("8350792227").read_text(encoding="utf-8"))


class SiteAssetsTest(unittest.TestCase):
    def test_every_published_image_hash_matches(self):
        self.assertEqual(len(IMAGES["images"]), 150)
        for record in IMAGES["images"]:
            path = PUBLIC / record["public_path"]
            self.assertTrue(path.is_file(), record["public_path"])
            data = path.read_bytes()
            self.assertEqual(len(data), record["bytes"], record["public_path"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), record["published_sha256"],
                             record["public_path"])

    def test_images_are_valid_files(self):
        """Structure check that runs without third-party packages."""
        for record in IMAGES["images"]:
            data = (PUBLIC / record["public_path"]).read_bytes()
            if record["public_path"].endswith(".png"):
                self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n", record["public_path"])
                self.assertIn(b"IEND", data[-32:], record["public_path"])
            else:
                self.assertEqual(data[:3], b"\xff\xd8\xff", record["public_path"])
                self.assertEqual(data[-2:], b"\xff\xd9", record["public_path"])

    @unittest.skipUnless(__import__("importlib").util.find_spec("PIL"), "Pillow не установлен")
    def test_images_decode(self):
        from PIL import Image

        for record in IMAGES["images"]:
            with Image.open(PUBLIC / record["public_path"]) as image:
                image.verify()

    def test_published_images_come_from_audited_sources(self):
        allowed_roots = ("avito_audit/", "official_assets/")
        transforms = {}
        for record in IMAGES["images"]:
            self.assertTrue(record["source_path"].startswith(allowed_roots), record["source_path"])
            self.assertNotIn("..", Path(record["source_path"]).parts)
            source = ROOT / record["source_path"]
            self.assertTrue(source.is_file(), record["source_path"])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), record["source_sha256"],
                             record["source_path"])
            transforms[record["transform"]] = transforms.get(record["transform"], 0) + 1
            if record["transform"] == "copy":
                self.assertEqual(record["bytes"], record["source_bytes"])
                self.assertEqual(record["published_sha256"], record["source_sha256"])
            else:
                self.assertTrue(record["public_path"].endswith(".jpg"))
                self.assertLessEqual(record["bytes"], record["source_bytes"])
        # 5 screenshot frames and the page-print photo are re-encoded for the web,
        # every other published image is a byte-identical copy of its source
        self.assertEqual(transforms, {"copy": 144, "png->jpeg q82": 6})

    def test_no_duplicate_images_in_public_tree(self):
        hashes = {}
        for record in IMAGES["images"]:
            hashes.setdefault(record["published_sha256"], []).append(record["public_path"])
        duplicates = {h: sorted(paths) for h, paths in hashes.items() if len(paths) > 1}
        # The single Speck illustration is shared by two listings (8102096652 and the
        # "2 шт" bundle 8350792227); this duplication is documented in the manifest and
        # must stay the only one.
        self.assertEqual(
            duplicates,
            {
                "647a95fd8d36d78b995156abea3cf7e2b48d1cec173f8d4241c1b68bcc3a411c": [
                    "assets/img/8102096652/maker-01.jpg",
                    "assets/img/8350792227/maker-01.jpg",
                ]
            },
        )
        on_disk = sorted(p.relative_to(PUBLIC).as_posix() for p in (PUBLIC / "assets/img").rglob("*") if p.is_file())
        self.assertEqual(on_disk, sorted(r["public_path"] for r in IMAGES["images"]))

    def test_new_layer_assets_are_published(self):
        paths = {r["public_path"] for r in IMAGES["images"]}
        self.assertIn("assets/img/8296456393/crop-04.jpg", paths)
        self.assertIn("assets/img/8296456393/badge-04.png", paths)
        self.assertIn("assets/img/8350792227/pageprint-01.jpg", paths)
        # frames that duplicate a 720x960 archive copy are not re-published
        self.assertNotIn("assets/img/8296456393/crop-01.jpg", paths)
        self.assertNotIn("assets/img/8296456393/crop-08.jpg", paths)
        crop = next(r for r in IMAGES["images"] if r["public_path"].endswith("crop-04.jpg"))
        self.assertEqual(crop["source_path"],
                         "avito_audit/attachments_avitos/images/8296456393/mobile_gallery_04.png")
        self.assertEqual(crop["dimensions"], [1170, 1644])


class SiteBuildTest(unittest.TestCase):
    @unittest.skipUnless(__import__("importlib").util.find_spec("PIL"), "Pillow не установлен")
    def test_build_is_reproducible(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("beauty_supply_build", ROOT / "site" / "build.py")
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        before = {
            p.relative_to(PUBLIC).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in PUBLIC.rglob("*")
            if p.is_file()
        }
        self.assertTrue(before)
        build.build()
        after = {
            p.relative_to(PUBLIC).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in PUBLIC.rglob("*")
            if p.is_file()
        }
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()


class SeoAndTechnicalTest(unittest.TestCase):
    """Guards the publishing contract: SEO metadata, structured data and
    technical files that Porkbun/search engines rely on."""

    @classmethod
    def setUpClass(cls):
        cls.pages = sorted(PUBLIC.rglob("*.html"))

    def test_titles_and_descriptions_fit_search_results(self):
        titles = {}
        for page in self.pages:
            html = page.read_text(encoding="utf-8")
            title = re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()
            description = re.search(r'<meta name="description" content="(.*?)"', html, re.S).group(1)
            self.assertLessEqual(len(title), 62, f"{page.name}: title {len(title)} символов")
            self.assertGreaterEqual(len(title), 20, f"{page.name}: слишком короткий title")
            self.assertLessEqual(len(description), 162, f"{page.name}: description {len(description)}")
            self.assertGreaterEqual(len(description), 70, f"{page.name}: слишком короткое description")
            self.assertNotIn(title, titles, f"{page.name}: title повторяет {titles.get(title)}")
            titles[title] = page.name

    def test_canonical_is_unique_and_absolute(self):
        canonicals = {}
        for page in self.pages:
            html = page.read_text(encoding="utf-8")
            match = re.search(r'<link rel="canonical" href="([^"]+)"', html)
            self.assertIsNotNone(match, f"{page.name}: нет canonical")
            url = match.group(1)
            self.assertTrue(url.startswith("https://usaforru.shop/"), url)
            self.assertNotIn(url, canonicals, f"{page.name} и {canonicals.get(url)} делят canonical")
            canonicals[url] = page.name

    def test_open_graph_and_twitter_cards(self):
        for page in self.pages:
            html = page.read_text(encoding="utf-8")
            for prop in ("og:title", "og:description", "og:url", "og:image", "og:type", "og:locale"):
                self.assertIn(f'property="{prop}"', html, f"{page.name}: нет {prop}")
            self.assertIn('name="twitter:card" content="summary_large_image"', html, page.name)
            image = re.search(r'property="og:image" content="([^"]+)"', html).group(1)
            self.assertTrue(image.startswith("https://usaforru.shop/"), image)
            self.assertTrue((PUBLIC / image.replace("https://usaforru.shop/", "")).is_file(), image)

    def test_structured_data_is_valid_json(self):
        found = 0
        for page in self.pages:
            html = page.read_text(encoding="utf-8")
            for block in re.findall(
                r'<script type="application/ld\+json">(.*?)</script>', html, re.S
            ):
                payload = json.loads(block)
                self.assertEqual(payload["@context"], "https://schema.org", page.name)
                found += 1
        self.assertGreaterEqual(found, 18)

    def test_product_pages_expose_product_schema(self):
        for product_id, page in PAGES.items():
            html = (PUBLIC / page).read_text(encoding="utf-8")
            match = re.search(
                r'<script type="application/ld\+json">(\{"@context":"https://schema.org","@type":"Product".*?)</script>',
                html,
            )
            self.assertIsNotNone(match, product_id)
            payload = json.loads(match.group(1))
            self.assertEqual(payload["sku"], product_id)
            self.assertEqual(payload["offers"]["priceCurrency"], "RUB")
            self.assertTrue(payload["offers"]["price"].isdigit())
            self.assertEqual(payload["offers"]["availability"], "https://schema.org/LimitedAvailability")

    def test_technical_files(self):
        robots = (PUBLIC / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("Sitemap: https://usaforru.shop/sitemap.xml", robots)
        self.assertIn("Allow: /", robots)
        self.assertEqual((PUBLIC / "CNAME").read_text(encoding="utf-8").strip(), "usaforru.shop")
        manifest = json.loads((PUBLIC / "site.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(manifest["start_url"], "/")
        self.assertEqual(manifest["lang"], "ru")
        self.assertTrue((PUBLIC / "assets" / "og-cover.jpg").is_file())
        self.assertTrue((PUBLIC / "assets" / "hero.jpg").is_file())

    def test_sitemap_lists_every_indexable_page(self):
        import xml.etree.ElementTree as ET

        tree = ET.parse(PUBLIC / "sitemap.xml")
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = [node.text for node in tree.getroot().findall("s:url/s:loc", ns)]
        self.assertEqual(len(urls), 17)
        self.assertEqual(len(set(urls)), 17)
        self.assertIn("https://usaforru.shop/", urls)
        self.assertNotIn("https://usaforru.shop/404.html", urls)
        for url in urls:
            relative = url.replace("https://usaforru.shop/", "") or "index.html"
            self.assertTrue((PUBLIC / relative).is_file(), url)

    def test_404_is_noindex(self):
        html = (PUBLIC / "404.html").read_text(encoding="utf-8")
        self.assertIn('name="robots" content="noindex, follow"', html)
        index = (PUBLIC / "index.html").read_text(encoding="utf-8")
        self.assertIn("index, follow, max-image-preview:large", index)

    def test_product_cards_show_price_with_source(self):
        html = (PUBLIC / "index.html").read_text(encoding="utf-8")
        self.assertEqual(html.count("продавец 28.10"), 2)
        self.assertIn("архив 26.10", html)
        self.assertIn("к архивной цене", html)

    def test_inline_styles_are_minimal(self):
        allowed = {"margin-top:0", "margin-top:.65rem;max-width:34rem"}
        for page in self.pages:
            for value in re.findall(r'style="([^"]*)"', page.read_text(encoding="utf-8")):
                self.assertIn(value, allowed, f"{page.name}: inline style {value}")

    def test_no_mixed_content(self):
        for page in self.pages:
            html = page.read_text(encoding="utf-8")
            self.assertNotIn('src="http://', html, page.name)
            self.assertNotIn("href=\"http://", html, page.name)


if __name__ == "__main__":
    unittest.main()


class RoutinePageTest(unittest.TestCase):
    """The routine landing page must cover every listing exactly once."""

    @classmethod
    def setUpClass(cls):
        cls.html = (PUBLIC / "podbor.html").read_text(encoding="utf-8")
        cls.config = json.loads(
            (ROOT / "site" / "site_config.json").read_text(encoding="utf-8")
        )

    def test_every_product_appears_once(self):
        import re as _re

        ids = _re.findall(r'data-card data-id="(\d+)"', self.html)
        self.assertEqual(len(ids), 14)
        self.assertEqual(sorted(ids), PRODUCT_IDS)

    def test_every_configured_routine_has_cards(self):
        sections = self.html.count('class="section routine-section"')
        self.assertEqual(sections, len(self.config["podbor"]))
        for item in self.config["podbor"]:
            self.assertIn(f'id="{item["id"]}"', self.html, item["title"])

    def test_routines_have_their_own_headings(self):
        for item in self.config["podbor"]:
            self.assertIn(f'id="{item["id"]}-title"', self.html, item["title"])

    def test_price_summary_table_lists_all_lots(self):
        self.assertIn("Все лоты, цены и статус", self.html)
        for product_id, page in PAGES.items():
            self.assertIn(f'href="{page}"', self.html, product_id)


class OutputHygieneTest(unittest.TestCase):
    """Generated pages must be clean, deterministic and free of template debris."""

    def test_no_trailing_whitespace(self):
        for page in sorted(PUBLIC.rglob("*.html")):
            for number, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
                self.assertEqual(line, line.rstrip(), f"{page.name}:{number} — пробелы в конце строки")

    def test_no_template_artifacts(self):
        for page in sorted(PUBLIC.rglob("*.html")):
            text = page.read_text(encoding="utf-8")
            for artifact in ("None", "{", "}", "__JS_VERSION__", "{{"):
                if artifact in ("{", "}"):
                    continue  # JSON-LD and inline scripts legitimately contain braces
                self.assertNotIn(artifact, text, f"{page.name}: артефакт шаблона {artifact}")
            self.assertNotIn("__JS_VERSION__", text, page.name)

    def test_no_empty_attributes(self):
        for page in sorted(PUBLIC.rglob("*.html")):
            text = page.read_text(encoding="utf-8")
            self.assertNotIn('href=""', text.replace('data-evidence-href=""', ""), page.name)

    def test_every_page_ends_with_closing_html_tag(self):
        for page in sorted(PUBLIC.rglob("*.html")):
            text = page.read_text(encoding="utf-8").rstrip()
            self.assertTrue(text.endswith("</html>"), page.name)
            self.assertTrue(text.startswith("<!DOCTYPE html>"), page.name)
