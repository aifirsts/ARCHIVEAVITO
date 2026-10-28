"""Checks for the GitHub Pages mirror committed in ``docs/``.

GitHub Pages serves this repository from the ``docs`` folder of the publishing
branch (Actions are unavailable on this account, so the Pages artefact has to
live in the repository). The mirror is built by ``python site/build.py`` and
must therefore obey three rules:

* it contains the same files as ``site/public`` — minus ``CNAME``, which would
  otherwise make Pages claim the Porkbun domain;
* every URL in metadata (canonical, Open Graph, JSON-LD, sitemap, robots)
  points at the Pages origin, not at the shop domain;
* every internal link resolves, including the absolute ones on ``404.html``,
  which Pages serves for unknown deep URLs.
"""

import hashlib
import importlib.util
import json
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "site" / "public"
DOCS = ROOT / "docs"
CONFIG = json.loads((ROOT / "site" / "site_config.json").read_text(encoding="utf-8"))
PAGES_URL = CONFIG["pages_url"].rstrip("/")
PREFIX = urlparse(PAGES_URL).path.rstrip("/")
SHOP_URL = CONFIG["site_url"].rstrip("/")
# Files whose bytes legitimately differ between the shop build and the mirror:
# they embed the canonical origin or carry the Pages-only provenance note.
ORIGIN_DEPENDENT = {"sitemap.xml", "robots.txt", "assets/images.json"}


def relative_files(directory: Path) -> dict:
    return {
        path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.rglob("*")
        if path.is_file()
    }


class Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for key in ("href", "src"):
            if attrs.get(key):
                self.targets.append(attrs[key])
        if attrs.get("data-src"):
            self.targets.append(attrs["data-src"])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


def refs_of(page: Path) -> list:
    parser = Refs()
    parser.feed(page.read_text(encoding="utf-8"))
    return parser.targets


def load_build_module():
    spec = importlib.util.spec_from_file_location("beauty_supply_build_pages", ROOT / "site" / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PagesMirrorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = sorted(DOCS.rglob("*.html"))
        cls.public_files = relative_files(PUBLIC)
        cls.docs_files = relative_files(DOCS)

    def test_mirror_mirrors_the_public_tree_without_cname(self):
        self.assertTrue(DOCS.is_dir(), "docs/ не собран: python site/build.py")
        self.assertEqual(set(self.docs_files), set(self.public_files) - {"CNAME"})
        self.assertFalse((DOCS / "CNAME").exists())
        self.assertTrue((DOCS / ".nojekyll").is_file(), ".nojekyll обязателен для GitHub Pages")
        self.assertEqual(len(self.pages), 18)
        self.assertTrue((DOCS / "404.html").is_file())
        self.assertTrue((DOCS / "item").is_dir())

    def test_binary_assets_are_byte_identical_to_the_shop_build(self):
        for name, digest in self.docs_files.items():
            if name in ORIGIN_DEPENDENT or name.endswith(".html"):
                continue
            self.assertEqual(digest, self.public_files[name], name)

    def test_canonical_origin_is_the_pages_url(self):
        for page in self.pages:
            markup = page.read_text(encoding="utf-8")
            canonical = f'<link rel="canonical" href="{PAGES_URL}/'
            self.assertIn(canonical, markup, page.name)
            self.assertIn(f'<meta property="og:url" content="{PAGES_URL}/', markup, page.name)
            self.assertNotIn(f'{SHOP_URL}/assets/og-cover.jpg', markup, page.name)

    def test_sitemap_and_robots_describe_the_mirror(self):
        sitemap = (DOCS / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn(f"<loc>{PAGES_URL}/</loc>", sitemap)
        self.assertNotIn(SHOP_URL, sitemap)
        robots = (DOCS / "robots.txt").read_text(encoding="utf-8")
        self.assertIn(f"Sitemap: {PAGES_URL}/sitemap.xml", robots)

    def test_manifest_and_icons_work_in_a_subdirectory(self):
        manifest = json.loads((DOCS / "site.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(manifest["start_url"], "./")
        self.assertEqual(manifest["icons"][0]["src"], "favicon.svg")
        self.assertFalse(manifest["start_url"].startswith("/"))

    def test_every_internal_reference_resolves(self):
        for page in self.pages:
            for target in refs_of(page):
                if not target or target.startswith(("http://", "https://", "mailto:", "data:", "#", "//")):
                    continue
                base = target.split("#")[0].split("?")[0]
                if base.startswith(PREFIX + "/"):
                    resolved = DOCS / base[len(PREFIX) + 1:]
                elif base.startswith("/"):
                    self.fail(f"{page.name}: ссылка мимо каталога сайта — {target}")
                else:
                    resolved = page.parent / base
                self.assertTrue(resolved.resolve().exists(), f"{page.name}: {target}")

    def test_404_references_are_absolute_for_deep_urls(self):
        markup = (DOCS / "404.html").read_text(encoding="utf-8")
        self.assertIn(f'<link rel="stylesheet" href="{PREFIX}/assets/site.css', markup)
        self.assertIn(f'href="{PREFIX}/index.html"', markup)
        self.assertIn(f'src="{PREFIX}/assets/', markup)
        # the shop build is served from the domain root, so its prefix is empty
        shop = (PUBLIC / "404.html").read_text(encoding="utf-8")
        self.assertIn('<link rel="stylesheet" href="/assets/site.css', shop)

    def test_mirror_matches_a_fresh_build(self):
        module = load_build_module()
        with tempfile.TemporaryDirectory() as tmp:
            module.build_pages_mirror(Path(tmp) / "docs")
            fresh = relative_files(Path(tmp) / "docs")
        self.assertEqual(fresh, self.docs_files, "docs/ устарел: python site/build.py")


if __name__ == "__main__":
    unittest.main()
