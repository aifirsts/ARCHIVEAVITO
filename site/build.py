"""Build the public Beauty Supply shop storefront into ``site/public``.

Presentation is driven by ``site/site_config.json`` (brand, domain, hero, FAQ,
routine landing copy) while every fact about a product comes from
``handoff/storefront.json`` and the audit manifests. The builder:

* copies only whitelisted, already-audited images into a flat public tree,
* renames them to SEO-friendly brand + product slugs,
* renders the catalogue, a routine landing page, 14 product pages, the
  provenance page, a 404 page, robots.txt, sitemap.xml and share cards,
* writes a JSON manifest of every published asset (path, sha256, source),
* keeps archive-level and live-level facts visibly separate.

Run: ``python site/build.py`` (add ``--check`` to fail when the output differs).
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(__file__).resolve().parent / "src"
OUT = Path(__file__).resolve().parent / "public"

CONFIG = json.loads(
    (Path(__file__).resolve().parent / "site_config.json").read_text(encoding="utf-8")
)
BRAND = CONFIG["brand"]
INITIALS = CONFIG["initials"]
DOMAIN = CONFIG["domain"]
SITE_URL = CONFIG["site_url"].rstrip("/")
TAGLINE = CONFIG["tagline"]
AREA = CONFIG["area_served"]

STORE_URL = "https://www.avito.ru/user/b2165ff5492372c90fab55f7223f9d3b/profile/items/all"
REPO_URL = "https://github.com/aifirsts/MATRIX2"
SOURCE_REPO_URL = "https://github.com/usaforyou/MANUS1"
ARCHIVE_LABEL = "26.10.2026"
NEW_LAYER_LABEL = "25.10.2026"
FW_LAYER_LABEL = "28.10.2026"
FW_STATUS_TITLES = {
    "new_offer_not_in_archived_catalog": "нет архивной карточки",
    "fresh_price_for_archived_listing": "свежая цена для архивной карточки",
    "not_merged_similar_archived_product_exists": "похожий товар в архиве не объединяется",
}

CATEGORY_TITLES = {
    "Красота и уход": "Косметика и уход",
    "Аксессуары": "Аксессуары",
    "Часы": "Часы",
}

# Short editorial titles used in navigation, cards and share previews. The
# seller's original wording stays available on the product page.
SHORT_TITLES = {
    "7942405497": "Румяна Ambient Lighting Blush",
    "7942010246": "Палетка теней Pillow Talk",
    "7942160038": "Палетка теней Curator Minimalist",
    "8102096652": "Чехол Speck Presidio2 Pro",
    "8165981546": "Лифтинг-крем для тела VOL.U.LIFT",
    "8166119490": "Концентрат VOL.U.LIFT",
    "8166255881": "Дневной крем SPF 30 Daily Prevention",
    "8166335454": "Ночной крем Vital C",
    "8166674710": "Смарт-крем SPF 75",
    "8230842563": "Крем Biotech Longevity",
    "7942108985": "Палетка Ambient Lighting",
    "8165960870": "Сыворотка Restoring Youth",
    "8296456393": "Часы MoonSwatch Bioceramic",
    "8350792227": "Чехол Speck Presidio2 Pro, 2 шт",
}

# Stable, readable, ASCII-only page slugs (SEO + shareable links).
PRODUCT_SLUGS = {
    "7942405497": "hourglass-ambient-lighting-blush",
    "7942010246": "charlotte-tilbury-pillow-talk-palette",
    "7942160038": "hourglass-curator-minimalist-palette",
    "8102096652": "speck-presidio2-pro-iphone-15-pro-max",
    "8165981546": "image-skincare-vol-u-lift-body-cream",
    "8166119490": "image-skincare-vol-u-lift-concentrate",
    "8166255881": "image-daily-prevention-spf-30",
    "8166335454": "image-vital-c-night-cream",
    "8166674710": "image-daily-prevention-spf-75",
    "8230842563": "image-md-biotech-longevity-creme",
    "7942108985": "hourglass-ambient-lighting-palette",
    "8165960870": "image-md-restoring-youth-serum",
    "8296456393": "swatch-omega-moonswatch-bioceramic",
    "8350792227": "speck-presidio2-pro-2-pack",
}

# Brand landing filter values used by the routine page and the catalogue chips.
ROUTINE_TAGS = {
    "8166255881": ["spf"],
    "8166674710": ["spf"],
    "8166335454": ["anti-age", "md"],
    "8165960870": ["anti-age", "md"],
    "8230842563": ["anti-age", "md"],
    "8165981546": ["body"],
    "8166119490": ["body"],
    "7942405497": ["makeup"],
    "7942010246": ["makeup"],
    "7942160038": ["makeup"],
    "7942108985": ["makeup"],
    "8102096652": ["accessories"],
    "8350792227": ["accessories"],
    "8296456393": ["accessories", "watches"],
}

CATEGORY_TAGS = {
    "Красота и уход": ["beauty"],
    "Аксессуары": ["accessories"],
    "Часы": ["watches"],
}

# Curated, item-specific limits. Everything here is either quoted from the
# handoff package or stated as an explicit limitation of the archive.
EXTRA_LIMITS = {
    "8350792227": [
        "В архиве нет отдельной HTML-карточки: есть только PDF-печать страницы от 25.10.2026.",
        "На странице одно фото — упаковка одного чехла Speck Presidio2 Pro. Второй чехол лота «2 шт» не сфотографирован.",
        "Объявление 8102096652 — другой лот (один белый чехол, Москва, 557 ₽). Данные этих объявлений не объединяются.",
    ],
    "8296456393": [
        "Страница объявления показывает 9 фотографий; в архиве есть кадры позиций 1–8. Файла для позиции № 9 нет ни в одном из семи ZIP.",
        "В характеристиках объявления указан «Цвет корпуса: Розовый», хотя на кадрах галереи разные модели коллекции — уточняйте вариант.",
        "Локального официального фото Swatch/OMEGA в архиве нет: у карточки только иллюстраций производителя ноль.",
    ],
    "7942405497": [
        "Описание продавца одновременно упоминает Ambient Strobe Lighting Blush — это другая линейка; на коробке читается Mood Exposure.",
    ],
    "8102096652": [
        "Иллюстрация Speck — материал производителя о линейке, а не фотография именно этого экземпляра.",
    ],
}

PRICE_NOTE = (
    "Архивная цена на 26.10.2026 — не текущая. Актуальную цену, наличие и комплектацию "
    "уточняйте в объявлении на Avito у продавца."
)

HERO_ART = "site/src/assets/hero.jpg"
SHARE_ART = "site/src/assets/og-cover.jpg"


def rub(value) -> str:
    if value is None:
        return "—"
    text = f"{int(value):,}".replace(",", "\u202f")
    return f"{text}\u00a0₽"


def plural_ru(count, one, few, many):
    """Russian plural forms: 1 кадр, 2 кадра, 5 кадров, 11 кадров."""
    n = abs(int(count)) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def slug(text: str) -> str:
    table = str.maketrans(
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ ",
        "abvgdeejziyklmnoprstufhccss_y_euaABVGDEEJZIYKLMNOPRSTUFHCCSS_Y_EUA-",
    )
    return "".join(ch for ch in text.translate(table).lower() if ch.isalnum() or ch in "-_") or "item"


def product_slug(product_id: str, short_title: str, brand: str) -> str:
    """Stable, human-readable, keyword-bearing path segment for a listing."""
    brand_slug = slug(brand).strip("-_")[:24] or "product"
    title_slug = slug(short_title).strip("-_")[:56] or product_id
    return f"{brand_slug}-{title_slug}"


# --------------------------------------------------------------------------- #
# data preparation
# --------------------------------------------------------------------------- #


class Publisher:
    """Copies audited images into the public tree and records their hashes."""

    def __init__(self, out: Path, existing_hashes: dict[str, str]):
        self.out = out
        self.assets_dir = out / "assets" / "img"
        self.existing_hashes = existing_hashes
        self.records: dict[str, dict] = {}

    # Heavy PNG frames from the mobile screenshots are re-encoded for the web; the
    # source file and its hash stay recorded so the published derivative is traceable.
    JPEG_KINDS = ("crop", "pageprint")
    JPEG_QUALITY = 82

    def publish(self, product_id: str, kind: str, number: int, source_path: str) -> dict:
        try:
            from PIL import Image
        except ImportError as error:  # pragma: no cover - environment problem
            raise SystemExit(
                "Для сборки нужен Pillow (перекодирование тяжёлых PNG в JPEG): "
                "python -m pip install -r requirements-dev.txt"
            ) from error

        source = ROOT / source_path
        if not source.is_file():
            raise SystemExit(f"Нет файла изображения: {source_path}")
        target_dir = self.assets_dir / product_id
        target_dir.mkdir(parents=True, exist_ok=True)
        source_bytes = source.read_bytes()
        transform = "copy"
        if kind in self.JPEG_KINDS and source.suffix.lower() == ".png":
            with Image.open(source) as image:
                image = image.convert("RGB")
                dimensions = list(image.size)
                target = target_dir / f"{kind}-{number:02d}.jpg"
                image.save(target, "JPEG", quality=self.JPEG_QUALITY, optimize=True, progressive=True)
            transform = f"png->jpeg q{self.JPEG_QUALITY}"
        else:
            target = target_dir / f"{kind}-{number:02d}{source.suffix.lower()}"
            target.write_bytes(source_bytes)
            with Image.open(source) as image:
                dimensions = list(image.size)
        rel = target.relative_to(self.out).as_posix()
        self.existing_hashes[rel] = sha(target)
        record = {
            "public_path": rel,
            "published_sha256": self.existing_hashes[rel],
            "bytes": target.stat().st_size,
            "source_path": source_path,
            "source_sha256": sha(source),
            "source_bytes": len(source_bytes),
            "transform": transform,
            "dimensions": dimensions,
        }
        self.records[rel] = record
        return record


def load_feed():
    feed = json.loads((ROOT / "handoff" / "storefront.json").read_text(encoding="utf-8"))
    attachments = json.loads(
        (ROOT / "avito_audit" / "attachments_avitos" / "manifest.json").read_text(encoding="utf-8")
    )
    return feed, attachments


def newest_layer(product):
    return product.get("supplemental_2026_10_25") or {}


def fresh_layer(product):
    """2026-10-28 seller-chat price layer, already validated by handoff/generate.py."""
    return product.get("seller_message_2026_10_28") or None


def price_delta(claimed, archived):
    if not claimed or not archived:
        return None
    delta = claimed - archived
    percent = round(delta / archived * 100)
    sign = "+" if delta > 0 else "−"
    value = f"{abs(delta):,}".replace(",", "\u202f")
    return f"{sign}{value}\u00a0₽ ({sign}{abs(percent)}\u00a0%)"


def dedupe(lines):
    """Keep the first occurrence of each limitation (case/spacing insensitive)."""
    seen, result = set(), []
    for line in lines:
        key = " ".join(str(line).lower().split())
        if key in seen:
            continue
        seen.add(key)
        result.append(line)
    return result


# Report sentences that only make sense inside the research notes; the site
# already shows the underlying facts, so they are not repeated as "limits".
DROPPED_LIMIT_MARKERS = (
    "На общем фото четыре подписанные коробки",
)
def build_products(feed, attachments, publisher, fw_public):
    """Turn the handoff package into page view models."""
    by_id = {p["id"]: p for p in feed["products"]}
    fw_photo_alts = {p["path"]: p["alt_ru"] for p in feed["seller_messages_2026_10_28"]["photos"]}
    captured = {str(item["id"]): item["page_print_creation_date_utc"] for item in attachments["listings"]}
    crops_by_position = {
        c["gallery_position_in_badge"]: c
        for c in by_id["8296456393"]["media"]["mobile_gallery_crops_2026_10_25"]
    }
    page_photo = by_id["8350792227"]["media"]["page_print_photo_2026_10_25"]

    products = []
    for order, product in enumerate(feed["products"], 1):
        pid = product["id"]
        listing = product["archived_listing"]
        media = product["media"]
        research = product["manufacturer_research"]
        layer = newest_layer(product)
        title = product["title_from_seller"]
        brand = research.get("brand") or ""
        category = product["category_from_snapshot"]

        slides = []
        evidence_strip = []
        for entry in media["listing_gallery"]:
            position = entry["position"]
            crop = crops_by_position.get(position) if pid == "8296456393" else None
            if crop and crop.get("asset"):
                asset = publisher.publish(pid, "crop", position, crop["asset"]["path"])
                badge = publisher.publish(pid, "badge", position, crop["badge_evidence"]["path"])
                slides.append(
                    {
                        "public_path": asset["public_path"],
                        "width": crop["asset"]["dimensions"][0],
                        "height": crop["asset"]["dimensions"][1],
                        "alt": f"{title} — кадр {position} галереи объявления, снят 25.10.2026",
                        "caption": f"Кадр {position} галереи. «{crop['note_ru']}»",
                        "source": "Кадр галереи · 25.10.2026",
                        "source_kind": "new",
                        "evidence_href": badge["public_path"],
                        "evidence_label": (
                            f"— из мобильного скриншота {crop['source_entry']} "
                            f"(SHA-256 {crop['source_entry_sha256'][:16]}…)"
                        ),
                        "tall": True,
                    }
                )
                evidence_strip.append(
                    {
                        "href": badge["public_path"],
                        "caption": f"позиция {position} — бейдж «{position} из 9»",
                    }
                )
                continue
            image = entry["large"] or entry["thumbnail"]
            if image is None:
                continue
            asset = publisher.publish(pid, "gallery", position, image["path"])
            slides.append(
                {
                    "public_path": asset["public_path"],
                    "width": image.get("dimensions", [0, 0])[0],
                    "height": image.get("dimensions", [0, 0])[1],
                    "alt": f"{title} — фото объявления, кадр {position}",
                    "caption": f"Кадр {position} галереи объявления из архивного HTML-снимка.",
                    "source": "Фото объявления · архив",
                    "source_kind": "listing",
                    "evidence_href": "",
                    "evidence_label": "",
                    "tall": True,
                }
            )

        if pid == "8350792227" and page_photo:
            asset = publisher.publish(pid, "pageprint", 1, page_photo["path"])
            slides.append(
                {
                    "public_path": asset["public_path"],
                    "width": page_photo["dimensions"][0],
                    "height": page_photo["dimensions"][1],
                    "alt": (
                        f"{title} — фотография со страницы объявления: упаковка чехла Speck "
                        "Presidio2 Pro для iPhone 15 Pro Max"
                    ),
                    "caption": (
                        "Единственное фото галереи на странице объявления. Второй чехол лота «2 шт» не сфотографирован."
                    ),
                    "source": "Фото со страницы · 25.10.2026",
                    "source_kind": "new",
                    "evidence_href": "",
                    "evidence_label": "",
                    "tall": True,
                }
            )

        missing_slots = []
        if pid == "8296456393":
            missing_slots.append(
                {
                    "position": 9,
                    "text": (
                        "Страница объявления показывает 9 фотографий, скриншоты покрывают позиции 1–8. "
                        "Файла для позиции № 9 нет ни в одном из семи архивных ZIP — похожее фото не подставляется."
                    ),
                }
            )
        if pid == "8350792227":
            missing_slots.append(
                {
                    "position": None,
                    "text": (
                        "Второй чехол из лота «2 шт» не сфотографирован ни на одном сохранённом кадре. "
                        "Комплектация требует подтверждения у продавца."
                    ),
                }
            )
        for slot in missing_slots:
            slides.append(
                {
                    "public_path": None,
                    "missing": True,
                    "missing_text": slot["text"],
                    "position": slot["position"],
                    "alt": "",
                    "caption": slot["text"],
                    "source": "Файла нет",
                    "source_kind": "missing",
                }
            )

        profile = []
        for preview in media["profile_previews"]:
            asset = publisher.publish(pid, "profile", preview["position"], preview["asset"]["path"])
            profile.append(
                {
                    "src": asset["public_path"],
                    "alt": f"{title} — превью из архивного снимка профиля, кадр {preview['position']}",
                    "caption": f"Профиль · {preview['position']}",
                }
            )

        maker = None
        if media["manufacturer_illustration"]:
            asset = publisher.publish(pid, "maker", 1, media["manufacturer_illustration"]["path"])
            maker = {
                "src": asset["public_path"],
                "alt": f"Иллюстрация производителя {brand}: {research.get('name', '')}. Не фотография продаваемого лота.",
            }

        attributes = dict(listing.get("attributes_from_seller") or {})
        attribute_source = (
            f"Заявленные продавцом характеристики из архивного HTML-объявления ({ARCHIVE_LABEL})"
            if attributes
            else None
        )
        page_print_attributes = {}
        page_print = {}
        if layer.get("page_print_snapshot"):
            page_print = layer["page_print_snapshot"]
            page_print_attributes = page_print.get("attributes_from_page") or {}
            if page_print_attributes:
                attribute_source = (
                    f"Характеристики со страницы объявления, печать {NEW_LAYER_LABEL} "
                    "(архивный HTML-карточки для этого лота нет)"
                )

        description = listing.get("seller_description_normalized") or (
            listing.get("description_profile_excerpt") or {}
        ).get("text") or ""
        description_source = (
            "Полный текст продавца из архивной HTML-карточки"
            if listing.get("seller_description_normalized")
            else "Фрагмент текста из архивного снимка профиля"
        )

        limits = list(EXTRA_LIMITS.get(pid, []))
        for item in layer.get("still_missing", []) or []:
            reason = item.get("reason_ru") or item.get("what")
            if reason:
                limits.append(f"Нет данных: {reason}")
        for line in layer.get("does_not_prove_ru", []) or []:
            limits.append(f"Архив не доказывает: {line}")
        verification = research.get("verification_note_ru")
        if verification:
            limits.append(verification)
        limits = dedupe([l for l in limits if not l.startswith(DROPPED_LIMIT_MARKERS)])
        if layer.get("do_not_merge_with"):
            merge = layer["do_not_merge_with"]
            limits.append(f"Не объединять с объявлением {merge['id']}: {merge['reason_ru']}")

        price_text = rub(listing.get("price_rub"))
        old_price = listing.get("old_price_text")
        discount = listing.get("discount_text")
        fresh = fresh_layer(product)
        fresh_price_value = fresh["price_rub_claimed"] if fresh else None
        fresh_price_text = rub(fresh_price_value) if fresh else None
        fresh_delta = price_delta(fresh_price_value, listing.get("price_rub")) if fresh else None
        if page_print.get("stock_status_text"):
            stock = page_print["stock_status_text"]
            stock_kind = "warn"
            stock_caption = f"по печати страницы {NEW_LAYER_LABEL}"
        elif listing.get("stock_badge_text"):
            stock = listing["stock_badge_text"]
            stock_kind = "info"
            stock_caption = f"по архивному снимку {ARCHIVE_LABEL}"
        else:
            stock = "Наличие не подтверждено"
            stock_kind = ""
            stock_caption = "в архиве нет отметки о наличии"

        search = " ".join(
            filter(
                None,
                [
                    title,
                    brand,
                    category,
                    research.get("name", ""),
                    product["id"],
                    " ".join(attributes.values()),
                    " ".join(page_print_attributes.values()),
                ],
            )
        )
        products.append(
            {
                "id": pid,
                "order": order,
                "title": title,
                "title_short": title if len(title) <= 58 else title[:55].rstrip() + "…",
                "brand": brand,
                "category": category,
                "category_title": CATEGORY_TITLES.get(category, category),
                "slug": slug(title),
                "price_text": price_text,
                "price_value": listing.get("price_rub") or 0,
                "fresh_price_text": fresh_price_text,
                "fresh_price_value": fresh_price_value,
                "fresh_delta": fresh_delta,
                "fresh_quote": fresh["price_quote_ru"] if fresh else None,
                "fresh_note": fresh["note_ru"] if fresh else None,
                "fresh_photo": fw_public.get(fresh["photo_path"]) if fresh else None,
                "fresh_photo_alt": fw_photo_alts.get(fresh["photo_path"]) if fresh else None,
                "old_price": old_price,
                "discount": discount,
                "has_discount": bool(discount),
                "location": listing.get("location_text") or "—",
                "profile_date": listing.get("profile_date_text") or "—",
                "item_page_date": listing.get("item_page_date_text") or "—",
                "views": listing.get("item_page_views_text"),
                "views_profile": None,
                "image": slides[0]["public_path"] if slides and not slides[0].get("missing") else None,
                "image_alt": slides[0]["alt"] if slides and not slides[0].get("missing") else "",
                "photo_count": sum(1 for s in slides if not s.get("missing")),
                "missing_count": sum(1 for s in slides if s.get("missing")),
                "slides": slides,
                "profile": profile,
                "maker": maker,
                "research": research,
                "description": description,
                "description_source": description_source,
                "attributes": attributes,
                "page_print_attributes": page_print_attributes,
                "attribute_source": attribute_source,
                "page_print": page_print,
                "layer": {
                    "captured_at": captured.get(pid),
                    "archive_sha256": attachments["archive_sha256"],
                    "archive_bytes": attachments["archive_bytes"],
                    "source_commit": attachments["source_commit"],
                },
                "limits": limits,
                "stock": stock,
                "stock_kind": stock_kind,
                "stock_caption": stock_caption,
                "avito_url": product["avito_url"],
                "evidence_strip": evidence_strip,
                "search": search,
            }
        )
    return products


# --------------------------------------------------------------------------- #
# view models
# --------------------------------------------------------------------------- #


def decorate(products):
    """Add shop-facing presentation fields that the raw feed does not carry."""
    for product in products:
        pid = product["id"]
        brand = product["brand"] or product["category_title"]
        product["short_title"] = SHORT_TITLES.get(pid, product["title_short"])
        product["slug"] = PRODUCT_SLUGS.get(pid) or product_slug(pid, product["short_title"], brand)
        product["page"] = f"item/{pid}-{product['slug']}.html"
        product["tags"] = sorted(
            set(CATEGORY_TAGS.get(product["category"], [])) | set(ROUTINE_TAGS.get(pid, []))
        )
        product["cta_price"] = product["fresh_price_text"] or product["price_text"]
        product["price_label"] = (
            f"цена продавца · {FW_LAYER_LABEL}" if product["fresh_price_text"] else f"архив · {ARCHIVE_LABEL}"
        )
        product["anchor_brand"] = slug(brand)

    by_brand = {}
    for product in products:
        by_brand.setdefault(product["brand"], []).append(product)
    for product in products:
        siblings = [p for p in by_brand[product["brand"]] if p["id"] != product["id"]]
        same_category = [
            p
            for p in products
            if p["id"] != product["id"]
            and p["category"] == product["category"]
            and p not in siblings
        ]
        product["similar"] = (siblings + same_category)[:3]
    return products


def brands_summary(products):
    """Ordered brand list with counts, used for the brand row and the manifest."""
    order, counts = [], {}
    for product in products:
        brand = product["brand"] or product["category_title"]
        if brand not in counts:
            order.append(brand)
            counts[brand] = 0
        counts[brand] += 1
    return [(brand, counts[brand]) for brand in order]


# --------------------------------------------------------------------------- #
# html helpers
# --------------------------------------------------------------------------- #


def source_badge(kind: str, text: str) -> str:
    return f'<span class="source-badge source-badge--{kind}">{esc(text)}</span>'


def jsonld(payload) -> str:
    return (
        '<script type="application/ld+json">'
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + "</script>"
    )


def head(
    title: str,
    description: str,
    root: str,
    css_version: str,
    js_version: str,
    path: str = "",
    og_image: str = "assets/og-cover.jpg",
    og_image_alt: str = "Иллюстрация витрины: косметика на льняной ткани",
    structured=None,
    noindex: bool = False,
) -> str:
    canonical = f"{SITE_URL}/{path}" if path else f"{SITE_URL}/"
    og_url = f"{SITE_URL}/{og_image}"
    robots = '<meta name="robots" content="noindex, follow">' if noindex else (
        '<meta name="robots" content="index, follow, max-image-preview:large">'
    )
    if not structured:
        ld = ""
    elif isinstance(structured, str):
        ld = structured
    else:
        ld = jsonld(structured)
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(canonical)}">
{robots}
<meta property="og:site_name" content="{esc(BRAND)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:locale" content="{esc(CONFIG['locale'])}">
<meta property="og:image" content="{esc(og_url)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{esc(og_image_alt)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(description)}">
<meta name="twitter:image" content="{esc(og_url)}">
<meta name="color-scheme" content="light">
<meta name="theme-color" content="#f7f3ec">
<meta name="format-detection" content="telephone=no">
<link rel="stylesheet" href="{root}assets/site.css?v={css_version}">
<link rel="icon" href="{root}favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="{root}favicon.svg">
<link rel="manifest" href="{root}site.webmanifest">
{ld}
</head>
<body>
<a class="skip-link" href="#main">Перейти к содержанию</a>
<noscript><p class="noscript">JavaScript отключён: страницы полностью читаемы, но поиск, фильтры, сортировка и переключение кадров галереи не работают. Первый кадр каждой галереи показан статически; заказ — по ссылкам на Avito.</p></noscript>
"""


def header(active: str, root: str) -> str:
    def current(name):
        return ' aria-current="page"' if active == name else ""

    nav_items = list(CONFIG["nav"])
    links = "".join(
        f'<a href="{root}{esc(item["href"])}"{current(item["key"])}>{esc(item["label"])}</a>'
        for item in nav_items
    )
    return f"""<aside class="topline" aria-label="Статус данных о ценах">
  <div class="wrap">
    <span><strong>Витрина продавца</strong> · фото и цены из архивов Avito</span>
    <span>Цена с датой · наличие подтверждает продавец</span>
  </div>
</aside>
<header class="site-header">
  <div class="wrap site-header__bar">
    <a class="brand" href="{root}index.html">
      <span class="brand__mark" aria-hidden="true">{esc(INITIALS)}</span>
      <span>
        <span class="brand__word">{esc(BRAND)}</span>
        <span class="brand__sub">{esc(TAGLINE)}</span>
      </span>
    </a>
    <nav class="site-nav" aria-label="Основная навигация">
      {links}
      <a href="{STORE_URL}" rel="noopener noreferrer nofollow">Профиль на Avito ↗</a>
    </nav>
    <form class="header-search" role="search" action="{root}index.html" method="get" aria-label="Поиск по каталогу">
      <svg class="header-search__icon" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><circle cx="7" cy="7" r="5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M11 11l4 4" stroke="currentColor" stroke-width="1.6" fill="none"/></svg>
      <label class="visually-hidden" for="header-search-input">Поиск по каталогу</label>
      <input id="header-search-input" type="search" name="q" placeholder="Найти товар или бренд" autocomplete="off">
      <button class="visually-hidden" type="submit">Найти</button>
    </form>
  </div>
</header>
"""


def footer(feed, products, root: str) -> str:
    profiles = feed["seller_profile_from_archive"]
    return f"""<footer class="site-footer">
  <div class="wrap site-footer__grid">
    <div>
      <h2>{esc(BRAND)}</h2>
      <p>Витрина продавца: {len(products)} {plural_ru(len(products), "лот", "лота", "лотов")} профессиональной
      косметики и аксессуаров в Москве и Домодедово. Онлайн-оплаты на сайте нет: заказ и все условия
      согласуются с продавцом в Avito.</p>
      <p><a href="{STORE_URL}" rel="noopener noreferrer nofollow">Профиль продавца на Avito ↗</a></p>
    </div>
    <div>
      <h2>Каталог</h2>
      <ul>
        <li><a href="{root}index.html">Все товары</a></li>
        <li><a href="{root}podbor.html">Подбор по задаче</a></li>
        <li><a href="{root}sources.html">Источники, хеши и ограничения</a></li>
      </ul>
    </div>
    <div>
      <h2>Правовое</h2>
      <ul>
        <li>Сайт не является публичной офертой</li>
        <li>Цены — архивный снимок {ARCHIVE_LABEL} и сообщения продавца {FW_LAYER_LABEL}</li>
        <li>Фотографии принадлежат правообладателям</li>
        <li>Отзывы и личные данные не публикуются</li>
      </ul>
    </div>
  </div>
  <div class="wrap site-footer__legal">
    <span>© {esc(BRAND)} · {esc(DOMAIN)}</span>
    <span>Профиль {esc(profiles["display_name"])}, публичный ID {esc(profiles["id"][:8])}…</span>
  </div>
</footer>
<script src="{root}assets/app.js?v=__JS_VERSION__" defer></script>
</body>
</html>
"""


def shell(page_html: str, root: str, js_version: str, feed, products) -> str:
    """Attach the footer script version placeholder in one place."""
    return page_html.replace("__JS_VERSION__", js_version)


def lightbox() -> str:
    return """<dialog class="lightbox" id="lightbox" aria-label="Просмотр фотографии">
  <div class="lightbox__inner">
    <img data-lightbox-image src="" alt="">
    <div class="lightbox__bar">
      <p class="lightbox__caption" data-lightbox-caption></p>
      <button type="button" class="icon-button lightbox__close" data-lightbox-close aria-label="Закрыть просмотр">✕</button>
    </div>
  </div>
</dialog>
"""


def card(product) -> str:
    if product["image"]:
        media = f"""<div class="card__media" data-media>
          <img src="{esc(product["image"])}" alt="{esc(product["image_alt"])}" loading="lazy" decoding="async"
               width="{product["slides"][0].get("width") or 700}" height="{product["slides"][0].get("height") or 700}"
               data-watch data-error-label="Фото не загрузилось — откройте карточку товара">
          <span class="card__photos">{product["photo_count"]} фото</span>"""
    else:
        media = """<div class="card__media card__media--empty">
          <span>Фотографий нет в архиве</span>"""
    discount = (
        f'<span class="card__flag">{esc(product["discount"])} в архиве</span>' if product["has_discount"] else ""
    )
    fresh_flag = (
        f'<span class="card__flag card__flag--fresh">цена продавца · {FW_LAYER_LABEL}</span>'
        if product["fresh_price_text"]
        else ""
    )
    if product["fresh_price_text"]:
        price_row = f"""<div class="card__price">
        <span class="price price--fresh">{product["fresh_price_text"]}</span>
        <span class="price-tag price-tag--fresh">продавец 28.10</span>
        <span class="price price--muted">{product["price_text"]}</span>
        <span class="price-tag">архив 26.10</span>
      </div>
      <p class="card__delta">{esc(product["fresh_delta"])} к архивной цене</p>"""
    else:
        price_row = f"""<div class="card__price">
        <span class="price">{product["price_text"]}</span>
        <span class="price-tag">архив</span>
        {f'<span class="price--old">{esc(product["old_price"])}</span>' if product["old_price"] else ""}
      </div>"""
    tags = "".join(
        f'<span class="tag">{esc(label)}</span>'
        for label in (
            "SPF" if "spf" in product["tags"] else "",
            "антивозрастной" if "anti-age" in product["tags"] else "",
            "для тела" if "body" in product["tags"] else "",
            "макияж" if "makeup" in product["tags"] else "",
        )
        if label
    )
    return f"""<li>
  <a class="card" href="{esc(product["page"])}"
     data-card data-id="{esc(product["id"])}"
     data-category="{esc(product["category"])}"
     data-price="{product["price_value"]}"
     data-discount="{1 if product["has_discount"] else 0}"
     data-tags="{esc(" ".join(product["tags"]))}"
     data-title="{esc(product["short_title"])}"
     data-search="{esc(product["search"] + " " + product["short_title"] + " " + " ".join(product["tags"]))}">
    {media}
      {discount}
      {fresh_flag}
    </div>
    <div class="card__body">
      <span class="card__brand">{esc(product["brand"] or product["category_title"])}</span>
      <h2 class="card__title">{esc(product["short_title"])}</h2>
      {price_row}
      <div class="card__tags">{tags}</div>
      <div class="card__foot">
        <span>{esc(product["location"])}</span>
        <span class="card__cta">Открыть на Avito ↗</span>
      </div>
    </div>
  </a>
</li>"""


def mini_card(product) -> str:
    """Compact cross-sell card used on product pages and the routine page."""
    media = (
        f'<img src="../{esc(product["image"])}" alt="{esc(product["image_alt"])}" loading="lazy" '
        f'decoding="async" width="420" height="420" data-watch>'
        if product["image"]
        else '<span class="mini__placeholder">Нет фото</span>'
    )
    price = product["fresh_price_text"] or product["price_text"]
    label = "продавец 28.10" if product["fresh_price_text"] else "архив"
    return f"""<li class="mini">
  <a class="mini__link" href="../{esc(product["page"])}">
    <span class="mini__media" data-media>{media}</span>
    <span class="card__brand">{esc(product["brand"] or product["category_title"])}</span>
    <span class="mini__title">{esc(product["short_title"])}</span>
    <span class="mini__price"><span class="price">{price}</span><span class="price-tag">{label}</span></span>
  </a>
</li>"""


# --------------------------------------------------------------------------- #
# pages
# --------------------------------------------------------------------------- #


def hero_block(hero_art, products) -> str:
    hero = CONFIG["hero"]
    total = sum(p["photo_count"] for p in products)
    brands = len(brands_summary(products))
    return f"""<main id="main">
  <section class="hero hero--shop">
    <div class="wrap hero__shop">
      <div class="hero__copy">
        <p class="eyebrow">{esc(hero["eyebrow"])}</p>
        <h1>{esc(hero["title_before"])} <em>{esc(hero["title_em"])}</em></h1>
        <p class="hero__lead">{esc(hero["lead"])}</p>
        <p class="hero__actions">
          <a class="button" href="{esc(hero["primary_cta"]["href"])}">{esc(hero["primary_cta"]["label"])}</a>
          <a class="button button--ghost" href="{esc(hero["secondary_cta"]["href"])}" rel="noopener noreferrer nofollow">{esc(hero["secondary_cta"]["label"])} ↗</a>
        </p>
        <dl class="hero__stats hero__stats--shop">
          <div><dt>{len(products)}</dt><dd>{plural_ru(len(products), "лот", "лота", "лотов")}</dd></div>
          <div><dt>{brands}</dt><dd>{plural_ru(brands, "бренд", "бренда", "брендов")}</dd></div>
          <div><dt>{total}</dt><dd>{plural_ru(total, "фотография", "фотографии", "фотографий")}</dd></div>
        </dl>
      </div>
      <figure class="hero__figure">
        <img src="{esc(hero_art["public_path"])}" alt="Иллюстрация витрины: флакон сыворотки, банка крема, тюбик SPF и льняная ткань на тёплом фоне."
             width="{hero_art["dimensions"][0]}" height="{hero_art["dimensions"][1]}" fetchpriority="high" decoding="async" data-watch>
        <figcaption>Иллюстрация витрины. Не фотография конкретного товара — фото каждого лота есть в карточке.</figcaption>
      </figure>
    </div>
  </section>
"""


def trust_strip(products, feed) -> str:
    archives = len(feed["source_archives_sha256"])
    returns = sum(1 for p in products if p["has_discount"])
    return f"""  <section class="trust" aria-label="Что важно знать перед заказом">
    <div class="wrap trust__grid">
      <div class="trust__item">
        <span class="trust__icon" aria-hidden="true">◎</span>
        <h2>Фото и цена с датой</h2>
        <p>У каждого кадра и каждой цены указан источник: архив объявления, печать страницы или переписка с продавцом.</p>
      </div>
      <div class="trust__item">
        <span class="trust__icon" aria-hidden="true">⌘</span>
        <h2>Связь напрямую</h2>
        <p>Кнопка в карточке открывает объявление продавца: там цена, состояние и способ получения.</p>
      </div>
      <div class="trust__item">
        <span class="trust__icon" aria-hidden="true">✓</span>
        <h2>Без навязанной корзины</h2>
        <p>Сайт не принимает оплату и не оформляет доставку, поэтому не бывает «сюрпризов» в чеке.</p>
      </div>
      <div class="trust__item">
        <span class="trust__icon" aria-hidden="true">✷</span>
        <h2>{returns} {plural_ru(returns, "позиция", "позиции", "позиций")} с архивной скидкой</h2>
        <p>{archives} исходных ZIP прошли сверку SHA-256 — данные не придуманы и не переписаны вручную.</p>
      </div>
    </div>
  </section>
"""


def brand_row(products) -> str:
    items = "".join(
        f'<li><a class="brand-pill" href="index.html?q={quote(brand)}">{esc(brand)}'
        f'<span class="brand-pill__count">{count}</span></a></li>'
        for brand, count in brands_summary(products)
    )
    return f"""  <section class="brands" aria-labelledby="brands-title">
    <div class="wrap">
      <h2 id="brands-title" class="eyebrow">Бренды в наличии в архиве</h2>
      <ul class="brand-row">{items}</ul>
    </div>
  </section>
"""


def catalogue_block(products) -> str:
    categories = []
    for name in CATEGORY_TITLES:
        count = sum(1 for p in products if p["category"] == name)
        if count:
            categories.append((name, count))
    chips = [
        (
            f'<button type="button" class="chip" data-filter-category="all" aria-pressed="true">'
            f'Все<span class="chip__count">{len(products)}</span></button>'
        )
    ]
    for name, count in categories:
        chips.append(
            f'<button type="button" class="chip" data-filter-category="{esc(name)}" aria-pressed="false">'
            f'{esc(CATEGORY_TITLES[name])}<span class="chip__count">{count}</span></button>'
        )
    tags = [
        ("spf", "С SPF"),
        ("anti-age", "Антивозрастной уход"),
        ("body", "Для тела"),
        ("makeup", "Макияж"),
        ("accessories", "Аксессуары"),
    ]
    tag_chips = "".join(
        f'<button type="button" class="chip chip--tag" data-filter-tag="{value}" aria-pressed="false">'
        f'{esc(label)}</button>'
        for value, label in tags
    )
    cards = "\n".join(card(p) for p in products)
    return f"""  <section class="controls" id="catalogue" aria-label="Поиск и фильтры каталога">
    <div class="wrap controls__row">
      <fieldset class="chips">
        <legend>Категория</legend>
        {"".join(chips)}
      </fieldset>
      <div class="controls__meta">
        <label class="toggle" for="filter-discount">
          <input id="filter-discount" type="checkbox"> только с архивной скидкой
        </label>
        <label class="visually-hidden" for="catalogue-sort">Сортировка</label>
        <select class="select" id="catalogue-sort">
          <option value="curated">Порядок каталога</option>
          <option value="price-asc">Цена: по возрастанию</option>
          <option value="price-desc">Цена: по убыванию</option>
          <option value="title">По названию</option>
        </select>
        <span class="result-count" id="result-count" role="status" aria-live="polite">{len(products)} из {len(products)}</span>
      </div>
    </div>
    <div class="wrap">
      <label class="visually-hidden" for="catalogue-search">Поиск по названию, бренду и характеристикам</label>
      <div class="header-search header-search--catalogue">
        <svg class="header-search__icon" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><circle cx="7" cy="7" r="5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M11 11l4 4" stroke="currentColor" stroke-width="1.6" fill="none"/></svg>
        <input id="catalogue-search" type="search" placeholder="Например: Hourglass, SPF, чехол, часы" autocomplete="off">
      </div>
      <div class="chips chips--tags" role="group" aria-label="Быстрые подборки">{tag_chips}</div>
    </div>
  </section>

  <section class="catalogue" aria-label="Каталог товаров">
    <div class="wrap">
      <ul class="grid" id="product-grid">
{cards}
      </ul>
      <div class="empty-state" id="empty-state" hidden>
        <h2>Ничего не найдено</h2>
        <p>Попробуйте другое слово или сбросите фильтры.</p>
        <button type="button" class="button button--ghost" id="reset-filters">Сбросить фильтры</button>
      </div>
    </div>
  </section>
"""


def offers_block(feed, products, fw_public) -> str:
    """Seller offers from the 2026-10-28 chat, presented as a price update."""
    layer = feed["seller_messages_2026_10_28"]
    alts = {p["path"]: p["alt_ru"] for p in layer["photos"]}
    dims = {p["path"]: p.get("dimensions") or [960, 1280] for p in layer["photos"]}
    cards = []
    for offer in layer["offers"]:
        photos = [
            {
                "src": fw_public[path],
                "alt": alts.get(path, ""),
                "width": dims.get(path, [960, 1280])[0],
                "height": dims.get(path, [960, 1280])[1],
            }
            for path in offer["photo_paths"]
        ]
        media = ""
        if photos:
            first = photos[0]
            media = (
                f'<div class="offer__media"><img src="{esc(first["src"])}" alt="{esc(first["alt"])}" '
                f'loading="lazy" decoding="async" width="{first["width"]}" height="{first["height"]}" data-watch>'
                f'<span class="offer__photo-note">фото из переписки · {FW_LAYER_LABEL}</span></div>'
            )
        if offer["matches_catalog_id"]:
            match = (
                f'<a class="offer__link" href="item/{esc(offer["matches_catalog_id"])}-'
                f'{esc(next(p["slug"] for p in products if p["id"] == offer["matches_catalog_id"]))}.html">'
                f'Открыть карточку с этой ценой →</a>'
            )
        else:
            match = f'<span class="offer__link offer__link--muted">{esc(FW_STATUS_TITLES.get(offer["status"], offer["status"]))}</span>'
        note = offer.get("note_ru") or offer.get("match_note_ru") or ""
        cards.append(
            f"""<article class="offer">
  {media}
  <div class="offer__body">
    <span class="card__brand">{esc(offer["brand"])}</span>
    <h3 class="offer__title">{esc(offer["title_ru"])}</h3>
    <p class="offer__price"><span class="price price--fresh">{rub(offer["price_rub_claimed"])}</span>
    <span class="price-tag price-tag--fresh">сообщение {FW_LAYER_LABEL}</span></p>
    <blockquote class="offer__quote">«{esc(offer["price_quote_ru"])}»</blockquote>
    {match}
    <p class="panel__note">{esc(note)}</p>
  </div>
</article>"""
        )
    return f"""  <section class="section section--offers" aria-labelledby="fresh-offers">
    <div class="wrap">
      <div class="section__head">
        <span class="section__index">Прайс-лист · {FW_LAYER_LABEL}</span>
        <h2 id="fresh-offers">Цены из переписки с продавцом</h2>
      </div>
      <p class="section__lead">Пять средств IMAGE Skincare и IMAGE MD, которые продавец предложил 28.10.2026.
      Две позиции уже есть в каталоге — для них цена продавца показана в карточке; три предложения пока без
      архивного объявления.</p>
      <div class="offers-grid">
{"".join(cards)}
      </div>
      <p class="panel__note"><strong>Это не архивные объявления.</strong> Цены прислал продавец в переписке
      28.10.2026; на Avito они не проверялись, наличие, комплектация и подлинность не подтверждены.
      Подписи на фото прочитаны машинным OCR и согласованы с текстом сообщений.</p>
    </div>
  </section>
"""


def howto_block() -> str:
    return f"""  <section class="section section--howto" aria-labelledby="howto">
    <div class="wrap">
      <div class="section__head">
        <span class="section__index">Как купить</span>
        <h2 id="howto">Три шага — и товар у вас</h2>
      </div>
      <ol class="steps">
        <li class="step">
          <span class="step__num">01</span>
          <h3>Выберите лот</h3>
          <p>В карточке видны фото, характеристики и обе цены: архивная {ARCHIVE_LABEL} и, если есть,
          цена продавца от {FW_LAYER_LABEL}.</p>
        </li>
        <li class="step">
          <span class="step__num">02</span>
          <h3>Напишите продавцу</h3>
          <p>Кнопка «Написать продавцу на Avito» открывает объявление. Уточните цену, состояние упаковки,
          срок годности и комплектацию.</p>
        </li>
        <li class="step">
          <span class="step__num">03</span>
          <h3>Договоритесь о получении</h3>
          <p>Самовывоз в Москве и Домодедово или отправка — условия и оплату продавец подтверждает лично.
          Сайт денег не принимает.</p>
        </li>
      </ol>
    </div>
  </section>
"""


def faq_block() -> str:
    items = "".join(
        f"""      <details class="faq__item">
        <summary>{esc(item["q"])}</summary>
        <div class="faq__answer"><p>{esc(item["a"])}</p></div>
      </details>"""
        for item in CONFIG["faq"]
    )
    faq_ld = jsonld(
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": item["q"],
                    "acceptedAnswer": {"@type": "Answer", "text": item["a"]},
                }
                for item in CONFIG["faq"]
            ],
        }
    )
    return f"""  <section class="section section--faq" aria-labelledby="faq">
    <div class="wrap">
      <div class="section__head">
        <span class="section__index">Вопросы</span>
        <h2 id="faq">Частые вопросы</h2>
      </div>
      <div class="faq">
{items}
      </div>
    </div>
  </section>
  {faq_ld}
"""


def podbor_block(products) -> str:
    cards = []
    for item in CONFIG["podbor"][:3]:
        matching = [p for p in products if item["filter"] in p["tags"]][:2]
        links = "".join(
            f'<li><a href="{esc(p["page"])}">{esc(p["short_title"])} · {esc(p["cta_price"])}</a></li>'
            for p in matching
        )
        cards.append(
            f"""<article class="routine">
          <h3>{esc(item["title"])}</h3>
          <p class="prose">{esc(item["lead"])}</p>
          <ul class="routine__links">{links}</ul>
          <p class="panel__note">{esc(item["note"])}</p>
        </article>"""
        )
    return f"""  <section class="section" aria-labelledby="routines">
    <div class="wrap">
      <div class="section__head">
        <span class="section__index">Подбор</span>
        <h2 id="routines">Соберите уход по задаче</h2>
      </div>
      <div class="columns columns--three">
        {"".join(cards)}
      </div>
      <p class="section__more"><a class="button button--ghost" href="podbor.html">Все подборки и протоколы →</a></p>
    </div>
  </section>
"""


def render_index(feed, products, fw_public, hero_art, css_version, js_version) -> str:
    store_ld = jsonld(
        {
            "@context": "https://schema.org",
            "@type": "Store",
            "name": BRAND,
            "url": f"{SITE_URL}/",
            "image": f"{SITE_URL}/assets/og-cover.jpg",
            "description": (
                "Витрина продавца профессиональной косметики и аксессуаров: Hourglass, Charlotte Tilbury, "
                "IMAGE Skincare, IMAGE MD, Speck, Swatch/OMEGA."
            ),
            "areaServed": AREA,
            "currenciesAccepted": "RUB",
            "paymentAccepted": "Согласуется с продавцом",
            "sameAs": [STORE_URL],
        }
    )
    body = (
        hero_block(hero_art, products)
        + trust_strip(products, feed)
        + brand_row(products)
        + catalogue_block(products)
        + offers_block(feed, products, fw_public)
        + podbor_block(products)
        + howto_block()
        + faq_block()
        + """</main>
"""
    )
    return (
        head(
            f"{BRAND} — профессиональная косметика и уход в Москве | {DOMAIN}",
            "Hourglass, Charlotte Tilbury, IMAGE Skincare, IMAGE MD, чехлы Speck и часы MoonSwatch: "
            "14 лотов с фото из архивов, ценами с датой и ссылкой на продавца в Avito.",
            "",
            css_version,
            js_version,
            path="",
            structured=store_ld,
        )
        + header("catalogue", "")
        + body
        + footer(feed, products, "")
    ).replace("__JS_VERSION__", js_version)


def thumbs_block(product) -> str:
    thumbs = []
    for position, slide in enumerate(product["slides"], 1):
        if slide.get("missing"):
            thumbs.append(
                f"""<button type="button" class="thumb thumb--missing" data-gallery-thumb data-missing="1"
                data-missing-text="{esc(slide["missing_text"])}" data-caption="{esc(slide["caption"])}"
                data-source="{esc(slide["source"])}" data-source-kind="missing" aria-current="false">
                <span aria-hidden="true">позиция<br>{position}<br>нет фото</span>
                <span class="visually-hidden">Позиция {position}: фотографии нет в архиве. Нажмите, чтобы прочитать причину.</span></button>"""
            )
        else:
            thumbs.append(
                f"""<button type="button" class="thumb" data-gallery-thumb
                data-src="../{esc(slide["public_path"])}" data-alt="{esc(slide["alt"])}"
                data-caption="{esc(slide["caption"])}" data-source="{esc(slide["source"])}"
                data-source-kind="{esc(slide["source_kind"])}"
                data-evidence-href="{esc(("../" + slide["evidence_href"]) if slide.get("evidence_href") else "")}"
                data-evidence-label="{esc(slide.get("evidence_label", ""))}"
                data-tall="{1 if slide.get("tall") else 0}"
                data-w="{slide.get("width") or 0}" data-h="{slide.get("height") or 0}"
                aria-label="Показать кадр {position}: {esc(slide["alt"])}" aria-current="false">
                <img src="../{esc(slide["public_path"])}" alt="" loading="lazy" decoding="async" width="80" height="80" data-watch>
              </button>"""
            )
    return "".join(thumbs)


def attributes_block(product) -> str:
    attributes = []
    for key, value in product["attributes"].items():
        attributes.append(f"<div><dt>{esc(key)}</dt><dd>{esc(value)}</dd></div>")
    for key, value in product["page_print_attributes"].items():
        if key in product["attributes"] and product["attributes"][key] == value:
            continue
        attributes.append(
            f'<div><dt>{esc(key)} <span class="eyebrow">25.10</span></dt><dd>{esc(value)}</dd></div>'
        )
    return (
        f'<dl class="attrs">{"".join(attributes)}</dl>'
        if attributes
        else '<p class="prose">Характеристик в архиве нет.</p>'
    )


def maker_block(product) -> str:
    research = product["research"]
    if not research:
        return '<p class="prose">Материалов производителя по этому лоту в архиве нет.</p>'
    details = research.get("details", {})
    items = []
    for label, values in (
        ("Характеристики", details.get("specifications_ru")),
        ("Состав / INCI", details.get("ingredients_ru")),
        ("Применение", [details.get("use_ru")] if details.get("use_ru") else None),
        ("Заявления производителя", [details.get("claims_ru")] if details.get("claims_ru") else None),
    ):
        if values:
            entries = "".join(f"<li>{esc(v)}</li>" for v in values)
            items.append(f"<h3>{esc(label)}</h3><ul>{entries}</ul>")
    figure = ""
    if product["maker"]:
        figure = f"""<figure class="maker-figure__art">
          <img src="../{esc(product["maker"]["src"])}" alt="{esc(product["maker"]["alt"])}" loading="lazy" decoding="async" data-watch>
          <figcaption class="panel__note">Иллюстрация производителя · не фотография лота</figcaption>
        </figure>"""
    body = f"""<div class="maker-figure__text">
          <h3>{esc(research.get("brand", ""))} — {esc(research.get("name", ""))}</h3>
          <p class="prose">{esc(research.get("summary_ru", ""))}</p>
          {''.join(items)}
          <p class="panel__note">{esc(research.get("verification_note_ru", ""))}</p>
          <p class="panel__note"><a href="{esc(research.get("url", ""))}" rel="noopener noreferrer nofollow">Страница производителя ↗</a>
          · материал проверен {esc(details.get("checked_at", "—"))}</p>
        </div>"""
    return f'<div class="maker-figure">{"".join([figure, body])}</div>'


def highlights(product) -> str:
    research = product["research"] or {}
    details = research.get("details", {})
    bullets = []
    claims = details.get("claims_ru")
    if claims:
        bullets.append(claims)
    specs = details.get("specifications_ru") or []
    bullets.extend(specs[:2])
    if product["fresh_price_text"]:
        bullets.insert(
            0,
            f"Цена продавца от {FW_LAYER_LABEL}: {product['fresh_price_text']} · "
            f"{product['fresh_delta']} к архивной {product['price_text']}.",
        )
    elif product["has_discount"]:
        bullets.insert(0, f"Архивная скидка {product['discount']}: {product['old_price']} → {product['price_text']}.")
    if not bullets:
        bullets.append("Фотографии и характеристики лота сохранены из архива объявления Avito.")
    items = "".join(f"<li>{esc(item)}</li>" for item in bullets[:4])
    return f'<ul class="highlights">{items}</ul>'


def render_product(product, products, feed, css_version, js_version) -> str:
    pid = product["id"]
    index = [p["id"] for p in products].index(pid)
    prev_product = products[index - 1] if index > 0 else None
    next_product = products[index + 1] if index + 1 < len(products) else None

    first_slide = product["slides"][0] if product["slides"] else None
    static_first_frame = (
        f'<img class="gallery__frame" src="../{esc(first_slide["public_path"])}" alt="{esc(first_slide["alt"])}" '
        f'width="{first_slide.get("width") or 700}" height="{first_slide.get("height") or 700}" '
        f'fetchpriority="high" decoding="async">'
        if first_slide and not first_slide.get("missing")
        else ""
    )

    fresh_panel = ""
    if product["fresh_price_text"]:
        fresh_photo = ""
        if product["fresh_photo"]:
            fresh_photo = f"""<figure class="fresh-price__figure">
          <img src="../{esc(product["fresh_photo"])}" alt="{esc(product["fresh_photo_alt"])}" loading="lazy" decoding="async" width="480" height="640" data-watch>
          <figcaption>Фото из сообщения продавца от {FW_LAYER_LABEL} · не архивная фотография объявления</figcaption>
        </figure>"""
        fresh_panel = f"""<div class="fresh-price">
          <p class="fresh-price__head">
            <span class="source-badge source-badge--fresh">Сообщение продавца · {FW_LAYER_LABEL}</span>
          </p>
          <p class="fresh-price__row">
            <span class="price price--fresh price--big">{product["fresh_price_text"]}</span>
            <span class="pill pill--info">{esc(product["fresh_delta"])} к архивной</span>
          </p>
          <blockquote class="prose prose--quote">«{esc(product["fresh_quote"])}»</blockquote>
          {fresh_photo}
          <p class="panel__note">{esc(product["fresh_note"])} Цена из переписки с продавцом от {FW_LAYER_LABEL}:
          на Avito она не проверялась, наличие и комплектация не подтверждены.</p>
        </div>"""

    limits = "".join(f"<li>{esc(line)}</li>" for line in product["limits"])
    page_print_rows = ""
    if product["page_print"]:
        labels = [
            ("listing_number_text", "Номер объявления"),
            ("listing_date_text", "Дата объявления"),
            ("display_price_text", "Цена на странице"),
            ("old_price_text", "Старая цена"),
            ("discount_text", "Скидка"),
            ("bonus_text", "Бонусы"),
            ("stock_status_text", "Статус на странице"),
            ("views_text", "Просмотры"),
            ("location_text", "Местоположение"),
        ]
        extra = [("today_views_text", "Просмотры сегодня")] if product["page_print"].get("today_views_text") else []
        rows = "".join(
            f"<tr><th scope=\"row\">{esc(label)}</th><td>{esc(product['page_print'].get(key) or '—')}</td></tr>"
            for key, label in labels + extra
        )
        page_print_rows = f"""<div class="table-wrap" role="region" aria-label="Факты из печати страницы" tabindex="0"><table><caption class="visually-hidden">
        Факты из PDF-печати страницы объявления</caption><tbody>{rows}</tbody></table></div>
        <p class="panel__note">Источник: печать страницы объявления {esc(NEW_LAYER_LABEL)}, создана
        {esc(product["layer"]["captured_at"])} (UTC). Значения относятся к моменту печати и не являются текущими.</p>"""

    profile_strip = ""
    if product["profile"]:
        figures = "".join(
            f"""<figure><img src="../{esc(item["src"])}" alt="{esc(item["alt"])}" loading="lazy" decoding="async" width="208" height="208" data-watch>
            <figcaption>{esc(item["caption"])}</figcaption></figure>"""
            for item in product["profile"]
        )
        profile_strip = (
            f'<div class="strip" role="region" aria-label="Превью из архивного профиля" tabindex="0">{figures}</div>'
        )

    pill_class = "pill" + (f" pill--{product['stock_kind']}" if product["stock_kind"] else "")
    slides_count = len(product["slides"])
    similar = "".join(mini_card(item) for item in product["similar"])
    related = f"""  <section class="section section--related" aria-labelledby="similar">
    <div class="wrap">
      <div class="section__head">
        <span class="section__index">С этим смотрят</span>
        <h2 id="similar">Похожие лоты</h2>
      </div>
      <ul class="mini-grid">{similar}</ul>
    </div>
  </section>
""" if product["similar"] else ""

    sale_price = product["fresh_price_text"] or product["price_text"]
    sale_label = (
        f"цена продавца · {FW_LAYER_LABEL}" if product["fresh_price_text"] else f"архивная цена · {ARCHIVE_LABEL}"
    )
    product_ld = jsonld(
        {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": f"{product['brand']} {product['short_title']}".strip(),
            "sku": pid,
            "mpn": pid,
            "brand": {"@type": "Brand", "name": product["brand"] or product["category_title"]},
            "category": product["category_title"],
            "image": [
                f"{SITE_URL}/{slide['public_path']}"
                for slide in product["slides"][:4]
                if not slide.get("missing")
            ],
            "description": (product["description"] or product["short_title"])[:420],
            "offers": {
                "@type": "Offer",
                "price": str(product["fresh_price_value"] or product["price_value"]),
                "priceCurrency": "RUB",
                # archival single lots: never promise unlimited stock in structured data
                "availability": "https://schema.org/LimitedAvailability",
                "url": product["avito_url"],
                "areaServed": AREA,
                "seller": {"@type": "Organization", "name": BRAND},
            },
        }
    )
    breadcrumb_ld = jsonld(
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Каталог", "item": f"{SITE_URL}/"},
                {
                    "@type": "ListItem",
                    "position": 2,
                    "name": product["category_title"],
                    "item": f"{SITE_URL}/index.html?category={quote(product['category'])}",
                },
                {"@type": "ListItem", "position": 3, "name": product["short_title"]},
            ],
        }
    )
    body = f"""<main id="main">
  <div class="wrap">
    <nav class="breadcrumb" aria-label="Хлебные крошки">
      <ol>
        <li><a href="../index.html">Каталог</a></li>
        <li><a href="../index.html?category={quote(product["category"])}">{esc(product["category_title"])}</a></li>
        <li aria-current="page">{esc(product["short_title"])}</li>
      </ol>
    </nav>

    <div class="product">
      <section class="gallery" data-gallery aria-roledescription="галерея" aria-label="Фотографии товара">
        <div class="gallery__stage" data-gallery-stage>{static_first_frame}</div>
        <p class="gallery__caption">
          <span class="source-badge source-badge--listing" data-gallery-source>Фото объявления · архив</span>
          <span data-gallery-caption></span>
        </p>
        <p class="gallery__meta" data-gallery-evidence hidden></p>
        <div class="thumbs" role="group" aria-label="Кадры галереи">
          {thumbs_block(product)}
        </div>
        <p class="gallery__meta">
          <span>Кадров в галерее: {product["photo_count"]} из {slides_count}</span>
          <span>Стрелки ← → переключают кадры</span>
          <span>Клик по фото открывает просмотр</span>
        </p>
      </section>

      <section class="buybox" aria-labelledby="product-title">
        <p class="buybox__brand">
          <a href="../index.html?q={quote(product["brand"])}">{esc(product["brand"] or product["category_title"])}</a>
          <span>· № {esc(pid)}</span>
        </p>
        <h1 id="product-title">{esc(product["short_title"])}</h1>
        <p class="buybox__subtitle">{esc(product["title"])}</p>
        <div class="buybox__price">
          <span class="price price--big">{sale_price}</span>
          <span class="price-tag">{sale_label}</span>
          {f'<span class="price--old">{esc(product["old_price"])}</span>' if product["old_price"] else ""}
          {f'<span class="price-tag">{esc(product["discount"])}</span>' if product["discount"] else ""}
        </div>
        {f'<p class="buybox__archive-price"><span class="price price--muted">{product["price_text"]}</span>'
         f'<span class="price-tag">архив {ARCHIVE_LABEL}</span>'
         f'<span class="panel__note"> — цена из архивного объявления, для сравнения</span></p>'
         if product["fresh_price_text"] else ""}
        <p class="buybox__note">{esc(PRICE_NOTE)}</p>
        {highlights(product)}
        <p class="pill-row">
          <span class="{pill_class}">{esc(product["stock"])}</span>
          <span class="pill__note">{esc(product["stock_caption"])}</span>
        </p>
        <a class="button button--block" href="{esc(product["avito_url"])}" rel="noopener noreferrer nofollow">
          Написать продавцу на Avito ↗
        </a>
        <a class="button button--ghost button--block" href="../sources.html">Как проверены фото и цены</a>
        <dl class="buybox__meta">
          <div><dt>Местоположение</dt><dd>{esc(product["location"])}</dd></div>
          <div><dt>Категория</dt><dd>{esc(product["category_title"])}</dd></div>
          <div><dt>Дата в профиле</dt><dd>{esc(product["profile_date"])}</dd></div>
          <div><dt>Дата в объявлении</dt><dd>{esc(product["item_page_date"])}</dd></div>
          {f'<div><dt>Просмотры (архив)</dt><dd>{esc(product["views"])}</dd></div>' if product["views"] else ""}
        </dl>
        {fresh_panel}
      </section>
    </div>
  </div>

{related}
  <section class="section" aria-labelledby="seller">
    <div class="wrap">
      <div class="section__head">
        <span class="section__index">01 — Продавец</span>
        <h2 id="seller">Что говорит продавец</h2>
      </div>
      <div class="columns">
        <div>
          <p class="eyebrow">{esc(product["description_source"])}</p>
          <div class="prose prose--quote">
            {f"<p>{esc(product['description'])}</p>" if product["description"] else "<p>Текст описания в архиве отсутствует.</p>"}
          </div>
          <p class="panel__note">Заявления продавца приводятся как архивная цитата. Сайт их не подтверждает и не гарантирует
          подлинность, эффект или состав конкретного экземпляра.</p>
        </div>
        <div>
          <p class="eyebrow">{esc(product["attribute_source"] or "Характеристики")}</p>
          {attributes_block(product)}
        </div>
      </div>
    </div>
  </section>

  <section class="section" aria-labelledby="maker">
    <div class="wrap">
      <div class="section__head">
        <span class="section__index">02 — Производитель</span>
        <h2 id="maker">Сведения и иллюстрации бренда</h2>
      </div>
      {maker_block(product)}
    </div>
  </section>

  <section class="section" aria-labelledby="media">
    <div class="wrap">
      <div class="section__head">
        <span class="section__index">03 — Фотоматериалы</span>
        <h2 id="media">Происхождение кадров и пропуски</h2>
      </div>
      <div class="columns">
        <div class="panel">
          <h3>Сколько и откуда</h3>
          <ul>
            <li>Фото объявления и профиля: {len(product["profile"]) + sum(1 for s in product["slides"] if s["source_kind"] == "listing")}</li>
            <li>Новый слой {NEW_LAYER_LABEL}: {sum(1 for s in product["slides"] if s["source_kind"] == "new")}</li>
            <li>Пропуски без подстановки: {product["missing_count"]}</li>
            <li>Иллюстрация производителя: {"есть" if product["maker"] else "нет"}</li>
          </ul>
          {f'<h3>Превью из архива профиля</h3>{profile_strip}' if profile_strip else ''}
        </div>
        <div>
          <h3 style="margin-top:0">Честные ограничения данных</h3>
          <p class="prose">Ниже — всё, что архив не позволяет утверждать. Мы не скрываем эти пункты:
          от них зависит, что стоит уточнить у продавца перед покупкой.</p>
          <ul class="missing-list">{limits}</ul>
        </div>
      </div>
    </div>
  </section>

  <section class="section" aria-labelledby="status">
    <div class="wrap">
      <div class="section__head">
        <span class="section__index">04 — Статус</span>
        <h2 id="status">Архивные данные и их дата</h2>
      </div>
      {page_print_rows}
      <div class="notice notice--sage" role="note">
        <span class="notice__icon" aria-hidden="true">◆</span>
        <div>
          <p>Архивный снимок: {esc(ARCHIVE_LABEL)}. Новый слой: печати и скриншоты {esc(NEW_LAYER_LABEL)},
          архив <code>Attachments-Avitos.zip</code>, SHA-256 <code>{esc(product["layer"]["archive_sha256"][:16])}…</code>,
          коммит исходника <code>{esc(product["layer"]["source_commit"][:12])}</code>.</p>
          <p>Текущую цену, наличие и комплектацию продавец подтверждает только в объявлении на Avito.
          Сайт не является публичной офертой.</p>
        </div>
      </div>
      <div class="related">
        {f'<a class="button button--ghost" href="{esc(prev_product["page"].split("/")[-1])}">← {esc(prev_product["short_title"])}</a>' if prev_product else '<span></span>'}
        <a class="button button--ghost" href="../index.html">Весь каталог</a>
        {f'<a class="button button--ghost" href="{esc(next_product["page"].split("/")[-1])}">{esc(next_product["short_title"])} →</a>' if next_product else '<span></span>'}
      </div>
    </div>
  </section>

  <div class="mobile-bar">
    <div class="mobile-bar__price">
      <span class="price">{sale_price}</span>
      <span>{sale_label}</span>
    </div>
    <a class="button" href="{esc(product["avito_url"])}" rel="noopener noreferrer nofollow">Написать продавцу ↗</a>
  </div>
</main>
{lightbox()}
{product_ld}
{breadcrumb_ld}
"""
    meta_description = (
        f"{product['brand']} {product['short_title']}: {sale_price} ({sale_label})"
        + (f", архивная цена {product['price_text']} на {ARCHIVE_LABEL}" if product["fresh_price_text"] else "")
        + ". "
        f"{product['photo_count']} фото, характеристики, состав и ссылка на объявление продавца в Avito. "
        f"Цена с датой, архивные ограничения указаны честно."
    )
    return (
        head(
            f"{product['brand']} {product['short_title']} — купить в Москве | {BRAND}",
            meta_description,
            "../",
            css_version,
            js_version,
            path=product["page"],
        )
        + header("item", "../")
        + body
        + footer(feed, products, "../")
    ).replace("__JS_VERSION__", js_version)


def render_podbor(products, feed, css_version, js_version) -> str:
    blocks = []
    for item in CONFIG["podbor"]:
        matching = [p for p in products if item["filter"] in p["tags"]]
        if not matching:
            continue
        cards = "\n".join(card(p) for p in matching)
        blocks.append(
            f"""  <section class="section routine-section" id="{esc(item["id"])}" aria-labelledby="{esc(item["id"])}-title">
    <div class="wrap">
      <div class="section__head">
        <span class="section__index">{esc(item["title"])}</span>
        <h2 id="{esc(item["id"])}-title">{esc(item["lead"])}</h2>
      </div>
      <p class="section__lead">{esc(item["note"])}</p>
      <ul class="grid grid--three">
{cards}
      </ul>
    </div>
  </section>
"""
        )
    rows = "".join(
        f'<tr><td><a href="{esc(p["page"])}">{esc(p["short_title"])}</a></td>'
        f"<td>{esc(p['brand'] or '—')}</td><td>{esc(p['category_title'])}</td>"
        f"<td>{esc(p['price_text'])}</td><td>{esc(p['fresh_price_text'] or '—')}</td></tr>"
        for p in sorted(products, key=lambda x: x["order"])
    )
    body = f"""<main id="main">
  <section class="hero hero--compact">
    <div class="wrap">
      <p class="eyebrow">Подбор по задаче</p>
      <h1>Что нужно коже — <em>сегодня</em></h1>
      <p class="hero__lead">Пять протоколов из ассортимента продавца: защита от солнца, антивозрастной уход,
      лифтинг для тела, макияж и аксессуары. В каждой подборке — лоты с фотографиями и ценой с датой.</p>
    </div>
  </section>
{"".join(blocks)}
  <section class="section" aria-labelledby="all">
    <div class="wrap">
      <div class="section__head">
        <span class="section__index">Сводка</span>
        <h2 id="all">Все лоты, цены и статус</h2>
      </div>
      <div class="table-wrap" role="region" aria-label="Сводная таблица лотов" tabindex="0"><table>
        <caption class="visually-hidden">Все лоты с архивной и свежей ценой</caption>
        <thead><tr><th scope="col">Товар</th><th scope="col">Бренд</th><th scope="col">Категория</th>
        <th scope="col">Архив {ARCHIVE_LABEL}</th><th scope="col">Продавец {FW_LAYER_LABEL}</th></tr></thead>
        <tbody>{rows}</tbody>
      </table></div>
      <p class="panel__note">Прочерк в правой колонке означает, что продавец не присылал новую цену:
      действует только архивная, и её нужно подтвердить в объявлении.</p>
    </div>
  </section>
  <section class="section section--cta">
    <div class="wrap">
      <div class="cta-box">
        <div>
          <h2>Не нашли нужное средство?</h2>
          <p>В ассортименте появляются новые позиции: продавец присылает цены и фото в переписке.
          Напишите, что ищете, — подберём формат и объём.</p>
        </div>
        <a class="button" href="{STORE_URL}" rel="noopener noreferrer nofollow">Написать продавцу на Avito ↗</a>
      </div>
    </div>
  </section>
</main>
"""
    return (
        head(
            f"Подбор косметики по задаче — SPF, антивозрастной уход, тело, макияж | {BRAND}",
            "Пять подборок профессиональной косметики: минеральные SPF, IMAGE MD, VOL.U.LIFT, Hourglass и "
            "Charlotte Tilbury, аксессуары и часы. Цены с датой и ссылкой на продавца.",
            "",
            css_version,
            js_version,
            path="podbor.html",
        )
        + header("podbor", "")
        + body
        + footer(feed, products, "")
    ).replace("__JS_VERSION__", js_version)


def render_sources(feed, products, attachments, fw, css_version, js_version) -> str:
    archive_rows = "".join(
        f'<tr><th scope="row">{esc(name)}</th><td><code>{esc(value)}</code></td></tr>'
        for name, value in feed["source_archives_sha256"].items()
    )
    product_rows = "".join(
        f'<tr><td><a href="{esc(p["page"])}">{esc(p["short_title"])}</a></td><td>{esc(p["id"])}</td>'
        f"<td>{esc(p['category_title'])}</td><td>{esc(p['price_text'])}</td><td>{esc(p['fresh_price_text'] or '—')}</td>"
        f"<td>{p['photo_count']}</td><td>{p['missing_count']}</td></tr>"
        for p in products
    )
    body = f"""<main id="main" class="doc">
  <div class="wrap">
    <p class="eyebrow">Происхождение данных</p>
    <h1>Источники, проверки и честные ограничения</h1>
    <p>Сайт собран из архивных снимков магазина {esc(BRAND)} на Avito. Владелец подтвердил, что профиль и магазин
    принадлежат ему. Это подтверждение не проверяет актуальные остатки, комплектацию отдельных лотов и права на
    изображения брендов.</p>

    <div class="notice" role="note">
      <span class="notice__icon" aria-hidden="true">◆</span>
      <div>
        <p><strong>Ни одна цена на сайте не является текущей.</strong> Все цены — снимок на {esc(ARCHIVE_LABEL)}
        (или {esc(NEW_LAYER_LABEL)} для нового слоя) либо заявление продавца из переписки {esc(FW_LAYER_LABEL)}.
        Кнопка покупки ведёт на объявление Avito; сайт не принимает оплату, не обещает доставку и не
        подтверждает наличие.</p>
      </div>
    </div>

    <h2>1. Архивные ZIP и контрольные суммы</h2>
    <p>Восемь архивов из <a href="{SOURCE_REPO_URL}" rel="noopener noreferrer">usaforyou/MANUS1</a>. ZIP-файлы и HTML из них
    в репозиторий сайта не копировались; HTML/JS из архивов не исполнялись.</p>
    <div class="table-wrap" role="region" aria-label="Архивы и их SHA-256" tabindex="0"><table>
      <caption class="visually-hidden">Архивы и их SHA-256</caption>
      <thead><tr><th scope="col">Архив</th><th scope="col">SHA-256</th></tr></thead>
      <tbody>{archive_rows}</tbody>
    </table></div>

    <h2>2. Новый архив Attachments-Avitos.zip (проверен {esc(ARCHIVE_LABEL)})</h2>
    <ul>
      <li>Источник: коммит <code>{esc(attachments["source_commit"])}</code> от {esc(attachments["source_commit_date"])};
      файл {attachments["archive_bytes"]}&nbsp;байт, SHA-256 <code>{esc(attachments["archive_sha256"])}</code>.</li>
      <li>Внутри {attachments["entries_count"]} записей: 8 мобильных скриншотов галереи объявления 8296456393 и
      2 PDF-печати страниц. Вложенных архивов, HTML и JS нет.</li>
      <li><strong>8296456393, позиция № 4:</strong> появился настоящий файл кадра, раньше была только внешняя ссылка.</li>
      <li><strong>8296456393, позиция № 9:</strong> страница показывает «1 из 9», скриншоты покрывают 1–8. Кадра № 9 нет —
      похожее фото не подставляется.</li>
      <li><strong>8350792227:</strong> появилась PDF-печать страницы (цена 1 116 ₽, статус «Товар зарезервирован»).
      Фото второго чехла по-прежнему нет. Объявление 8102096652 — другой лот, данные не объединяются.</li>
    </ul>

    <h2>3. Свежий архив Attachments-Fw_ 27.10 avito.zip (проверен {esc(FW_LAYER_LABEL)})</h2>
    <ul>
      <li>Источник: коммит <code>{esc(fw["source_commit"])}</code> от {esc(fw["source_commit_date_utc"])} (UTC);
      файл {fw["bytes"]}&nbsp;байт, SHA-256 <code>{esc(fw["sha256"])}</code>.</li>
      <li>Внутри {fw["entries"]} записей: 7 Apple-плist’ов (NSKeyedArchiver) с текстами сообщений продавца
      и 3 JPEG-фото 960×1280. Вложенных архивов, HTML и JS нет.</li>
      <li><strong>Цены продавца от {esc(FW_LAYER_LABEL)} 13:51:</strong> Max face cream — 11&nbsp;500&nbsp;₽;
      Max eye cream — 6&nbsp;800&nbsp;₽; SPF&nbsp;30 мойсчерайзер (с тинтом и без) — 4&nbsp;900&nbsp;₽;
      Biotech MD cream — 10&nbsp;400&nbsp;₽; Biotech MD serum — 11&nbsp;500&nbsp;₽.</li>
      <li><strong>Сопоставление с каталогом:</strong> SPF-крем соответствует лоту 8166255881
      (архив 5&nbsp;900&nbsp;₽ → 4&nbsp;900&nbsp;₽), Biotech-крем — лоту 8230842563
      (12&nbsp;999&nbsp;₽ → 10&nbsp;400&nbsp;₽). Сыворотка Power-C <em>не объединяется</em> с архивной
      «Restoring Youth Serum» — это разные официальные продукты.</li>
      <li>Сообщение от {esc(NEW_LAYER_LABEL)} содержит ссылку на тот же профиль продавца
      (<code>b2165ff5…</code>), что и архивный снимок. Подписи на фото прочитаны машинным OCR.</li>
    </ul>

    <h2>4. Как разделены сведения</h2>
    <div class="table-wrap" role="region" aria-label="Разделение слоёв данных" tabindex="0"><table>
      <thead><tr><th scope="col">Слой</th><th scope="col">Что это</th><th scope="col">Чего это не доказывает</th></tr></thead>
      <tbody>
        <tr><td>{source_badge("listing", "Фото объявления")}</td><td>Кадры галереи и превью профиля из архивных HTML</td>
        <td>Не подтверждает текущее состояние и комплектацию</td></tr>
        <tr><td>{source_badge("new", "Слой 25.10.2026")}</td><td>Мобильные скриншоты галереи и печати страниц</td>
        <td>Не подтверждает текущую цену и наличие; статус «зарезервирован» относится к {esc(NEW_LAYER_LABEL)}</td></tr>
        <tr><td>{source_badge("fresh", "Сообщения 28.10.2026")}</td><td>Цены и фото из переписки с продавцом</td>
        <td>Заявление продавца вне Avito: цена, наличие и комплектация не проверены</td></tr>
        <tr><td>{source_badge("maker", "Производитель")}</td><td>Описания линеек, INCI, иллюстрации брендов</td>
        <td>Не фотография лота, не гарантия подлинности и не разрешение на коммерческое использование</td></tr>
        <tr><td>{source_badge("maker", "Иллюстрация витрины")}</td><td>Обложка и баннер сайта — сгенерированное изображение косметики</td>
        <td>Не фотография продаваемого товара и не изображение конкретного бренда</td></tr>
      </tbody>
    </table></div>

    <h2>5. Все {len(products)} лотов каталога</h2>
    <div class="table-wrap" role="region" aria-label="Все объявления каталога" tabindex="0"><table>
      <thead><tr><th scope="col">Товар</th><th scope="col">ID</th><th scope="col">Категория</th>
      <th scope="col">Архив {esc(ARCHIVE_LABEL)}</th><th scope="col">Продавец {esc(FW_LAYER_LABEL)}</th>
      <th scope="col">Кадров</th><th scope="col">Пропусков</th></tr></thead>
      <tbody>{product_rows}</tbody>
    </table></div>

    <h2>6. Что не публикуется</h2>
    <ul>
      <li>Отзывы, имена покупателей и контактные данные из исходного HTML.</li>
      <li>Исходные HTML, JS, CSS и трекеры архивов, а также исследовательские JSON с отзывами: они вне веб-корня.</li>
      <li>Кадры рекламы, аватары и блоки «рекомендованные объявления» из печатей страниц.</li>
      <li>Полосы статуса iOS с временем и зарядом устройства: из скриншотов вырезан только кадр галереи.</li>
    </ul>

    <h2>7. Публикация и домен</h2>
    <ul>
      <li>Сайт статический: HTML, CSS, JS и изображения. Сборка — <code>python site/build.py</code>,
      публикуется только каталог <code>site/public</code>.</li>
      <li>Домен <strong>{esc(DOMAIN)}</strong> зарегистрирован в Porkbun; для статического хостинга Porkbun
      каталог <code>site/public</code> загружается в корень сайта (FTP или GitHub Connect).</li>
      <li>Канонический адрес каждой страницы — <code>{esc(SITE_URL)}</code>; карта сайта
      <a href="sitemap.xml">sitemap.xml</a>, правила обхода — <a href="robots.txt">robots.txt</a>.</li>
      <li>Сайт не является публичной офертой. Цены и наличие подтверждает продавец в Avito.</li>
    </ul>

    <p><a href="index.html">← Вернуться в каталог</a></p>
  </div>
</main>
"""
    return (
        head(
            f"Источники и статус данных — {BRAND}",
            f"Происхождение данных {BRAND}: восемь архивных ZIP, слои {NEW_LAYER_LABEL} и {FW_LAYER_LABEL}, "
            "SHA-256, пропущенные фотографии и ограничения архива.",
            "",
            css_version,
            js_version,
            path="sources.html",
        )
        + header("sources", "")
        + body
        + footer(feed, products, "")
    ).replace("__JS_VERSION__", js_version)


def render_404(products, feed, css_version, js_version) -> str:
    picks = products[:4]
    cards = "".join(mini_card(p).replace('href="../', 'href="').replace('src="../', 'src="') for p in picks)
    body = f"""<main id="main">
  <section class="hero hero--compact">
    <div class="wrap">
      <p class="eyebrow">Ошибка 404</p>
      <h1>Такой страницы <em>нет</em></h1>
      <p class="hero__lead">Возможно, ссылка устарела: адреса карточек изменились после обновления витрины.
      Вернитесь в каталог — там все {len(products)} лотов с фото и ценами.</p>
      <p class="hero__actions"><a class="button" href="index.html">В каталог</a>
      <a class="button button--ghost" href="index.html?q=SPF">Подбор с SPF</a></p>
    </div>
  </section>
  <section class="section">
    <div class="wrap">
      <div class="section__head">
        <span class="section__index">Популярное</span>
        <h2>Часто открывают</h2>
      </div>
      <ul class="mini-grid">{cards}</ul>
    </div>
  </section>
</main>
"""
    return (
        head(
            f"Страница не найдена — {BRAND}",
            "Страница не найдена. Вернитесь в каталог профессиональной косметики и аксессуаров.",
            "",
            css_version,
            js_version,
            path="404.html",
            noindex=True,
        )
        + header("404", "")
        + body
        + footer(feed, products, "")
    ).replace("__JS_VERSION__", js_version)


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #


def require_pillow():
    try:
        import PIL  # noqa: F401
    except ImportError as error:  # pragma: no cover - environment problem
        raise SystemExit(
            "Для сборки нужен Pillow (перекодирование тяжёлых PNG в JPEG): "
            "python -m pip install -r requirements-dev.txt"
        ) from error


def publish_own(out: Path, source_path: str, public_name: str) -> dict:
    """Publish a site-owned image (hero art, share card) with its provenance."""
    source = ROOT / source_path
    if not source.is_file():
        raise SystemExit(f"Нет файла изображения витрины: {source_path}")
    target = out / "assets" / public_name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    try:
        from PIL import Image

        with Image.open(target) as image:
            dimensions = list(image.size)
    except ImportError:  # pragma: no cover - covered by require_pillow
        dimensions = [0, 0]
    return {
        "public_path": target.relative_to(out).as_posix(),
        "source_path": source_path,
        "source_sha256": sha(source),
        "published_sha256": sha(target),
        "bytes": target.stat().st_size,
        "transform": "copy",
        "dimensions": dimensions,
    }


def sitemap(products) -> str:
    urls = [("", "1.0", "weekly"), ("podbor.html", "0.8", "weekly"), ("sources.html", "0.4", "monthly")]
    urls += [(p["page"], "0.7", "monthly") for p in products]
    entries = "".join(
        f"  <url>\n    <loc>{SITE_URL}/{esc(path)}</loc>\n"
        f"    <changefreq>{freq}</changefreq>\n    <priority>{priority}</priority>\n  </url>\n"
        for path, priority, freq in urls
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + entries
        + "</urlset>\n"
    )


def robots_txt() -> str:
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /assets/images.json\n"
        f"\nSitemap: {SITE_URL}/sitemap.xml\n"
    )


def build(out: Path | None = None) -> dict:
    """Render the site into ``out`` (defaults to ``site/public``).

    The target directory is only removed after every input and dependency has
    been validated, so a failed build never leaves a half-empty public tree.
    """
    require_pillow()
    out = Path(out) if out is not None else OUT
    feed, attachments = load_feed()
    if out.exists():
        shutil.rmtree(out)
    (out / "assets").mkdir(parents=True)
    (out / "item").mkdir()

    hashes: dict[str, str] = {}
    publisher = Publisher(out, hashes)
    fw_public = {}
    for number, photo in enumerate(feed["seller_messages_2026_10_28"]["photos"], 1):
        record = publisher.publish("seller-2026-10-28", "sellermsg", number, photo["path"])
        fw_public[photo["path"]] = record["public_path"]
    products = decorate(build_products(feed, attachments, publisher, fw_public))

    hero_art = publish_own(out, HERO_ART, "hero.jpg")
    share_art = publish_own(out, SHARE_ART, "og-cover.jpg")

    css_source = (SRC / "site.css").read_text(encoding="utf-8")
    js_source = (SRC / "app.js").read_text(encoding="utf-8")
    css_version = hashlib.sha256(css_source.encode()).hexdigest()[:10]
    js_version = hashlib.sha256(js_source.encode()).hexdigest()[:10]
    (out / "assets" / "site.css").write_text(css_source, encoding="utf-8")
    (out / "assets" / "app.js").write_text(js_source, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    favicon = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" role="img" '
        f'aria-label="{esc(BRAND)}">'
        '<rect width="32" height="32" fill="#1a1613"/>'
        '<text x="16" y="22" font-family="Georgia,serif" font-size="15" fill="#f7f3ec" '
        f'text-anchor="middle">{esc(INITIALS)}</text></svg>'
    )
    (out / "favicon.svg").write_text(favicon, encoding="utf-8")
    (out / "favicon.ico").write_bytes(b"\x00\x00\x01\x00\x00\x00")
    manifest_web = {
        "name": f"{BRAND} — профессиональная косметика",
        "short_name": BRAND,
        "description": TAGLINE,
        "start_url": "/",
        "display": "standalone",
        "background_color": "#f7f3ec",
        "theme_color": "#1a1613",
        "lang": "ru",
        "icons": [{"src": "/favicon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"}],
    }
    (out / "site.webmanifest").write_text(
        json.dumps(manifest_web, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "CNAME").write_text(DOMAIN + "\n", encoding="utf-8")
    (out / "robots.txt").write_text(robots_txt(), encoding="utf-8")
    (out / "sitemap.xml").write_text(sitemap(products), encoding="utf-8")
    (out / "404.html").write_text(
        render_404(products, feed, css_version, js_version), encoding="utf-8"
    )
    (out / "index.html").write_text(
        render_index(feed, products, fw_public, hero_art, css_version, js_version), encoding="utf-8"
    )
    (out / "podbor.html").write_text(
        render_podbor(products, feed, css_version, js_version), encoding="utf-8"
    )
    (out / "sources.html").write_text(
        render_sources(feed, products, attachments, feed["seller_messages_2026_10_28"], css_version, js_version),
        encoding="utf-8",
    )
    for product in products:
        (out / product["page"]).write_text(
            render_product(product, products, feed, css_version, js_version), encoding="utf-8"
        )

    pages = (
        ["index.html", "podbor.html", "sources.html", "404.html"]
        + [p["page"] for p in products]
    )
    manifest = {
        "schema_version": 2,
        "generator": "site/build.py",
        "brand": BRAND,
        "site_url": SITE_URL,
        "data_source": "handoff/storefront.json",
        "archive_date": feed["archive_date"],
        "status": feed["status"],
        "products": len(products),
        "pages": pages,
        "product_pages": {p["id"]: p["page"] for p in products},
        "sitemap": "sitemap.xml",
        "images": [
            record for record in sorted(publisher.records.values(), key=lambda r: r["public_path"])
        ],
        "site_assets": [hero_art, share_art],
        "asset_versions": {"site.css": css_version, "app.js": js_version},
        "not_published": [
            "avito_audit/snapshot.json (содержит отзывы)",
            "avito_audit/item_pages/data.json (исследовательский JSON)",
            "исходные ZIP, HTML, JS и CSS архивов",
            "полные скриншоты с полосой статуса iOS",
        ],
    }
    (out / "assets" / "images.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def snapshot(directory: Path | None = None):
    directory = Path(directory) if directory is not None else OUT
    if not directory.exists():
        return {}
    return {
        path.relative_to(directory).as_posix(): sha(path)
        for path in directory.rglob("*")
        if path.is_file()
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Собрать публичный сайт в site/public")
    parser.add_argument(
        "--check",
        action="store_true",
        help="не перезаписывать: проверить, что сохранённая сборка совпадает с источниками",
    )
    args = parser.parse_args(argv)
    if args.check:
        before = snapshot()
        if not before:
            raise SystemExit("Сборки нет: сначала запустите python site/build.py")
        # a check must never touch the published tree: build into a scratch dir
        with tempfile.TemporaryDirectory() as tmp:
            build(Path(tmp) / "public")
            after = snapshot(Path(tmp) / "public")
        if before != after:
            changed = sorted(set(before) ^ set(after)) + [
                key for key in before if key in after and before[key] != after[key]
            ]
            print("Сборка устарела, пересоберите сайт:", *changed[:10], sep="\n  ")
            return 1
        print(f"Сборка актуальна: {len(after)} файлов")
        return 0
    manifest = build()
    print(f"Собрано страниц: {len(manifest['pages'])}, изображений: {len(manifest['images'])}")
    print(f"Выход: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
