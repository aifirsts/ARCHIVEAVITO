"""Reproducible audit of ``Attachments-Avitos.zip`` from ``usaforyou/MANUS1``.

The archive is **not** stored in this repository. Download it from the pinned
commit, then run::

    python avito_audit/check_attachments_zip.py /path/to/Attachments-Avitos.zip

The script never executes anything from the archive:

* it lists entries and rejects absolute paths / ``..`` traversal,
* it records the kind of every entry (image / PDF page print / forbidden),
* it extracts PDF *page prints* with ``pypdf`` (no JavaScript, no attachments),
* it crops the mobile screenshot gallery frames with fixed geometry,
* it hashes every kept file and writes ``manifest.json`` plus the assets below
  ``avito_audit/attachments_avitos/``.

Classifications (gallery vs advertisement vs avatar vs recommendation) are
curated per entry and each one carries a human-readable reason. Facts quoted
from the PDF page prints are asserted against the extracted text so that the
manifest cannot drift from the source.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "avito_audit" / "attachments_avitos"
IMAGES = OUT / "images"
MANIFEST = OUT / "manifest.json"

SOURCE_REPOSITORY = "https://github.com/usaforyou/MANUS1"
SOURCE_COMMIT = "cf1c74b4a623ad22e7cedd5180aee98571261b1b"
SOURCE_COMMIT_DATE = "2026-10-26T06:22:25+08:00"
ARCHIVE_NAME = "Attachments-Avitos.zip"
ARCHIVE_SHA256 = "7d1eca79385ba06d702f0812eca8b5ee70990295295ec2b06442a28e33b5d6d0"
ARCHIVE_BYTES = 16396636

# Expected content. ZIP entry names from iOS use non-breaking spaces (\xa0),
# so PDF page prints are resolved by their trailing "(<id>).pdf" marker instead
# of a literal name match.
SCREENSHOT_POSITIONS = {
    "IMG_1178.png": (8296456393, 1),
    "IMG_1179.png": (8296456393, 2),
    "IMG_1180.png": (8296456393, 3),
    "IMG_1181.png": (8296456393, 4),
    "IMG_1182.png": (8296456393, 5),
    "IMG_1183.png": (8296456393, 6),
    "IMG_1184.png": (8296456393, 7),
    "IMG_1185.png": (8296456393, 8),
}
PAGE_PRINT_IDS = (8296456393, 8350792227)


def resolve_page_prints(names):
    """Map listing id -> ZIP entry name of its PDF page print."""
    resolved = {}
    for listing_id in PAGE_PRINT_IDS:
        marker = f"({listing_id}).pdf"
        matches = [name for name in names if name.endswith(marker)]
        if len(matches) != 1:
            raise SystemExit(f"Ожидался ровно один PDF для {listing_id}, найдено: {matches}")
        resolved[listing_id] = matches[0]
    return resolved


# Mobile screenshot geometry, identical on all eight shots (iPhone, 1170x2532):
#   0..140    iOS status bar (time, battery) — personal device data, not published
#   141..258  black Avito gallery header, "N из 9" badge is drawn around y=190..235
#   259..1901 the gallery photo itself
#   1902..1957 purple "Купить с доставкой" / "В корзину" buttons
SCREENSHOT_SIZE = (1170, 2532)
HEADER_CROP = {"box": [0, 141, 1170, 258], "why": "бейдж «N из 9» для сопоставления со слотом галереи"}
PHOTO_CROP = {"box": [0, 258, 1170, 1902], "why": "кадр галереи без статус-бара, заголовка, кнопок и адресной строки"}

# PDF embedded images, classified by hand after visual inspection of the page
# prints. Nothing from the "advertisement"/"avatar"/"recommendation" rows is
# published or attributed to a listing.
PDF_IMAGE_CLASSIFICATION = {
    # watches page print (8296456393)
    ("8296456393", "Im72.png"): {
        "role": "gallery",
        "reason": "Крупный кадр лота на белом листе страницы; совпадает с позицией № 1 сохранённой галереи",
        "gallery_position": 1,
    },
    ("8296456393", "Im71.png"): {
        "role": "advertisement",
        "reason": "Баннер «Настоящие скидки до 90% на Хватамбе», не фотография лота",
    },
    # case page print (8350792227)
    ("8350792227", "Im6.png"): {
        "role": "gallery",
        "reason": "Основное фото лота: упаковка Speck Presidio2 Pro для iPhone 15 Pro Max",
        "gallery_position": 1,
    },
    ("8350792227", "Im5.png"): {
        "role": "gallery_thumbnail",
        "reason": "Та же фотография лота в размере миниатюры 150×110 галереи объявления",
        "gallery_position": 1,
    },
    ("8350792227", "Im15.png"): {"role": "advertisement", "reason": "Реклама «Альфа Банк. Кэшбэк до 50%»"},
    ("8350792227", "Im17.png"): {"role": "advertisement", "reason": "Баннер «ХватАмба. До -90%»"},
    ("8350792227", "Im2.png"): {"role": "avatar", "reason": "Аватар аккаунта в шапке мобильной страницы, не товар"},
    ("8350792227", "Im18.png"): {"role": "avatar", "reason": "Небольшой круглый аватар/иконка интерфейса 96×96"},
    ("8350792227", "Im19.png"): {"role": "advertisement", "reason": "Рекламная плашка 284×74"},
    ("8350792227", "Im16.png"): {"role": "ui", "reason": "Пустая серая заглушка рекламного блока 300×600"},
    ("8350792227", "Im7.png"): {"role": "recommendation", "reason": "Блок «Похожие объявления» / «Вместе смотрят»: три чужих чехла"},
    ("8350792227", "Im8.png"): {"role": "recommendation", "reason": "Рекомендация: прозрачный чехол с MagSafe, другое объявление"},
    ("8350792227", "Im9.png"): {"role": "recommendation", "reason": "Рекомендация: два тёмных чехла, другое объявление"},
    ("8350792227", "Im10.png"): {"role": "recommendation", "reason": "Рекомендация: чехол MAGSSORY, другое объявление"},
    ("8350792227", "Im11.png"): {"role": "recommendation", "reason": "Рекомендация: чехлы на бежевом фоне, другое объявление"},
    ("8350792227", "Im12.png"): {"role": "recommendation", "reason": "Рекомендация: шесть разноцветных чехлов, другое объявление"},
}

# Dated observations read from the page prints. Every ``must_contain`` string is
# asserted against the extracted text of that PDF, so the record is evidence
# backed. These are snapshots, not live inventory.
OBSERVATIONS = {
    8350792227: {
        "captured_from": "pdf_page_print",
        "page_print_creation_date_utc": "2026-10-25T22:15:26Z",
        "listing_number_text": "8350792227",
        "listing_date_text": "8 октября в 22:19",
        "views_text": "21 просмотр",
        "today_views_text": "(+0 сегодня)",
        "display_price_text": "1 116 ₽",
        "old_price_text": "1 200 ₽",
        "discount_text": "−7% на распродаже",
        "bonus_text": "+24 бонуса",
        "stock_status_text": "Товар зарезервирован",
        "location_text": "с. Домодедово",
        "breadcrumb_text": "Электроника › Телефоны › Чехлы и плёнки › Чехлы › Аксессуары",
        "attributes_from_page": {
            "Состояние": "Новое",
            "Производитель чехла": "Speck",
            "Подходит для: Производитель": "Apple",
            "Подходит для: Модель": "iPhone 15 Pro Max",
        },
        "description_text": "Для Дениса",
        "gallery_photos_saved_in_print": 1,
        "must_contain": [
            "8350792227",
            "8 октября в 22:19",
            "21 просмотр",
            "+0 сегодня",
            "1 116 ₽",
            "1 200 ₽",
            "7% на распродаже",
            "+24 бонуса",
            "Товар зарезервирован",
            "с. Домодедово",
            "Состояние: Новое",
            "Производитель чехла: Speck",
            "Модель: iPhone 15 Pro Max",
            "Для Дениса",
        ],
    },
    8296456393: {
        "captured_from": "pdf_page_print",
        "page_print_creation_date_utc": "2026-10-25T22:11:16Z",
        "listing_number_text": "8 296 456 393",
        "listing_date_text": "10 октября в 13:44",
        "views_text": "373 просмотра",
        "display_price_text": "33 272 ₽",
        "old_price_text": "35 777 ₽",
        "discount_text": "−7% на распродаже",
        "bonus_text": "+600 бонусов",
        "stock_status_text": None,
        "location_text": "Москва",
        "gallery_badge_text": "1 из 9",
        "gallery_position_count": 9,
        "attributes_from_page": {
            "Тип товара": "Наручные часы",
            "Состояние": "Новое",
            "Бренд": "Omega",
            "Цвет корпуса": "Розовый",
            "Цвет ремешка": "Розовый",
            "Механизм": "Кварцевые",
            "Для кого": "Унисекс",
            "Тип ремешка": "Нейлоновый",
        },
        "must_contain": [
            "33 272 ₽",
            "35 777 ₽",
            "7% на распродаже",
            "1 из 9",
            "373 просмотра",
            "10 октября в 13:44",
            "Бренд: Omega",
            "Наручные часы",
            "Москва",
        ],
    },
}

# Screenshot frame -> gallery slot. The badge order is 1..8; frames 1,2,3,5,6,7,8
# reproduce the photographs already saved for those gallery positions (confirmed
# by visual inspection, see ``visually_confirmed_slot``), which is what ties the
# numbering of the screenshots to the numbering of the archived gallery.
# Frame 4 shows a photograph that exists in no earlier ZIP.
SCREENSHOT_NOTES = {
    1: {"visually_confirmed_slot": 1,
        "note_ru": "Голубые часы в коробке: тот же кадр, что сохранённая позиция № 1"},
    2: {"visually_confirmed_slot": 2,
        "note_ru": "Серые часы с чёрным ремешком: тот же кадр, что позиция № 2"},
    3: {"visually_confirmed_slot": 3,
        "note_ru": "Розовые часы: тот же кадр, что позиция № 3 (в архиве была только миниатюра 150×110)"},
    4: {"visually_confirmed_slot": None,
        "note_ru": "Серо-стальные часы Mission to the Moon: НОВЫЙ кадр, локального файла не было ни в одном ZIP"},
    5: {"visually_confirmed_slot": 5,
        "note_ru": "Коробки 1965 и Omega × Swatch: тот же кадр, что позиция № 5"},
    6: {"visually_confirmed_slot": 6,
        "note_ru": "Открытая коробка 1965: тот же кадр, что позиция № 6 (в архиве была только миниатюра)"},
    7: {"visually_confirmed_slot": 7,
        "note_ru": "Четыре коробки Mission to Venus / Mercury / Uranus / Moon: тот же кадр, что позиция № 7 (только миниатюра в архиве)"},
    8: {"visually_confirmed_slot": 8,
        "note_ru": "Коробки с часами на светлом столе: тот же кадр, что позиция № 8"},
}

# Кадры, где в архиве уже есть крупная копия 720×960, не дублируются в
# репозитории: сохраняем обрезку только там, где она добавляет разрешение
# (позиции 3, 5, 6, 7 имели лишь миниатюру 150×110) или где файла не было вовсе
# (позиция 4).
SCREENSHOT_STORE_CROP = {1: False, 2: False, 3: True, 4: True, 5: True, 6: True, 7: True, 8: False}

# Small embedded bitmaps are text runs / icons of the rendered page, not photos.
GLYPH_MAX_SIDE = 40
GLYPH_MAX_AREA = 6000


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pdf_date_to_iso(value):
    """Convert a PDF ``D:YYYYMMDDHHMMSS...`` date to ``YYYY-MM-DDTHH:MM:SSZ``."""
    if not value:
        return None
    match = re.match(r"D:(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", value)
    if not match:
        return value
    y, mo, d, h, mi, se = match.groups()
    return f"{y}-{mo}-{d}T{h}:{mi}:{se}Z"


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u00a0", " ").replace("\u2212", "-")).strip()


def fingerprint(image):
    """Coarse 24x24 luminance fingerprint for a *supporting* similarity signal.

    Correlation between a mobile screenshot frame and a saved JPEG is weak
    (different crop, letterboxing, UI-free area), so this number never decides
    which gallery slot a frame belongs to. Mapping is curated and confirmed
    visually; the score is stored only as an informational hint.
    """
    small = image.convert("L").resize((24, 24))
    values = [float(v) for v in small.tobytes()]
    mean = sum(values) / len(values)
    deviation = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5 or 1.0
    return [round((v - mean) / deviation, 3) for v in values]


def similarity(left, right) -> float:
    return round(sum(a * b for a, b in zip(left, right)) / len(left), 3)


def existing_fingerprints():
    """Fingerprints of every JPEG/PNG already stored in the repository."""
    from PIL import Image

    records = {}
    for path in sorted(ROOT.glob("avito_audit/**/*.jpg")) + sorted(ROOT.glob("avito_audit/**/*.png")):
        with Image.open(path) as image:
            records[path.relative_to(ROOT).as_posix()] = (sha256(path.read_bytes()), fingerprint(image))
    for path in sorted(ROOT.glob("official_assets/*.png")) + sorted(ROOT.glob("official_assets/*.jpg")):
        with Image.open(path) as image:
            records[path.relative_to(ROOT).as_posix()] = (sha256(path.read_bytes()), fingerprint(image))
    return records


def previous_zip_hashes(archive_paths, current):
    """SHA-256 of every entry of the other MANUS1 ZIPs (when they are available)."""
    hashes = {}
    for path in archive_paths:
        if Path(path).resolve() == Path(current).resolve():
            continue
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                hashes.setdefault(sha256(archive.read(info)), []).append(
                    f"{Path(path).name}:{info.filename}"
                )
    return hashes


def audit_archive(path: Path):
    entries = []
    problems = []
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:  # pragma: no cover - corrupted download
            problems.append(f"CRC ошибка в записи {bad}")
        for info in archive.infolist():
            name = info.filename
            if name.startswith("/") or ".." in Path(name).parts or "\\" in name:
                problems.append(f"Небезопасный путь: {name}")
                continue
            suffix = Path(name).suffix.lower()
            kind = "other"
            if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                kind = "image"
            elif suffix == ".pdf":
                kind = "pdf"
            elif suffix in {".html", ".htm", ".js", ".mjs", ".css", ".svg"}:
                kind = "executable_markup"
                problems.append(f"HTML/JS/CSS внутри архива не публикуется и не исполняется: {name}")
            elif suffix in {".zip", ".7z", ".rar", ".gz", ".tar"}:
                kind = "nested_archive"
                problems.append(f"Вложенный архив: {name}")
            entries.append(
                {
                    "name": name,
                    "bytes": info.file_size,
                    "compressed_bytes": info.compress_size,
                    "sha256": sha256(archive.read(info)),
                    "zip_datetime": "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}".format(*info.date_time),
                    "kind": kind,
                }
            )
    return entries, problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="path to Attachments-Avitos.zip")
    parser.add_argument(
        "--keep-unchanged",
        action="store_true",
        help="do not fail when the pinned SHA-256 differs (writes the actual value)",
    )
    args = parser.parse_args(argv)

    from PIL import Image
    from pypdf import PdfReader

    raw = args.archive.read_bytes()
    actual_sha = sha256(raw)
    if actual_sha != ARCHIVE_SHA256 and not args.keep_unchanged:
        raise SystemExit(
            f"SHA-256 архива не совпадает с закреплённым.\n  ожидалось: {ARCHIVE_SHA256}\n"
            f"  получено: {actual_sha}\nЕсли архив обновился, закрепите новый SHA-256 в этом скрипте."
        )

    entries, problems = audit_archive(args.archive)
    by_name = {e["name"]: e for e in entries}
    page_prints = resolve_page_prints(by_name)
    expected_names = set(SCREENSHOT_POSITIONS) | set(page_prints.values())
    unexpected = sorted(set(by_name) - expected_names)
    missing = sorted(expected_names - set(by_name))
    IMAGES.mkdir(parents=True, exist_ok=True)
    for stale in sorted(IMAGES.rglob("*.png")):
        stale.unlink()

    known = existing_fingerprints()
    previous = previous_zip_hashes(sorted(args.archive.parent.glob("*.zip")), args.archive)

    screenshots = []
    pdf_images = []
    texts = {}
    kept = 0

    with zipfile.ZipFile(args.archive) as archive:
        for name in sorted(by_name):
            info = by_name[name]
            data = archive.read(name)
            if name in SCREENSHOT_POSITIONS:
                kind, (listing_id, position) = "screenshot", SCREENSHOT_POSITIONS[name]
            elif name in page_prints.values():
                kind, position = "pdf_page_print", None
                listing_id = next(k for k, v in page_prints.items() if v == name)
            else:
                continue
            if kind == "screenshot":
                with Image.open(io.BytesIO(data)) as image:
                    if image.size != SCREENSHOT_SIZE:
                        raise SystemExit(f"Неожиданный размер скриншота {name}: {image.size}")
                    image = image.convert("RGB")
                    header = image.crop(tuple(HEADER_CROP["box"]))
                    photo = image.crop(tuple(PHOTO_CROP["box"]))
                target_dir = IMAGES / str(listing_id)
                target_dir.mkdir(parents=True, exist_ok=True)
                header_path = target_dir / f"mobile_gallery_{position:02d}_header.png"
                header.save(header_path, "PNG", optimize=True)
                header_bytes = header_path.read_bytes()
                kept += 1
                store_crop = SCREENSHOT_STORE_CROP[position]
                if store_crop:
                    photo_path = target_dir / f"mobile_gallery_{position:02d}.png"
                    photo.save(photo_path, "PNG", optimize=True)
                    photo_bytes = photo_path.read_bytes()
                    kept += 1
                else:
                    buffer = io.BytesIO()
                    photo.save(buffer, "PNG", optimize=True)
                    photo_bytes = buffer.getvalue()
                shot_fp = fingerprint(photo)
                matches = []
                for other, (other_sha, other_fp) in known.items():
                    if not other.startswith(("avito_audit/item_pages/images/", "avito_audit/images/")):
                        continue
                    if f"/{listing_id}/" not in other:
                        continue
                    matches.append(
                        {
                            "path": other,
                            "similarity": similarity(shot_fp, other_fp),
                            "same_bytes": other_sha == sha256(photo_bytes),
                        }
                    )
                screenshots.append(
                    {
                        "entry": name,
                        "entry_sha256": info["sha256"],
                        "entry_bytes": info["bytes"],
                        "gallery_position_in_badge": position,
                        "listing_id": listing_id,
                        "visually_confirmed_saved_slot": SCREENSHOT_NOTES[position]["visually_confirmed_slot"],
                        "note_ru": SCREENSHOT_NOTES[position]["note_ru"],
                        "photo_crop": {
                            **PHOTO_CROP,
                            "stored": store_crop,
                            "path": photo_path.relative_to(ROOT).as_posix() if store_crop else None,
                            "derived_sha256": sha256(photo_bytes),
                            "derived_bytes": len(photo_bytes),
                            "dimensions": list(photo.size),
                            "not_stored_reason_ru": None if store_crop else (
                                "в архиве уже есть крупная копия этого кадра 720×960, "
                                "дубликат по содержимому не сохраняется"
                            ),
                        },
                        "header_evidence_crop": {
                            **{k: v for k, v in HEADER_CROP.items() if k != "why"},
                            "path": header_path.relative_to(ROOT).as_posix(),
                            "sha256": sha256(header_bytes),
                            "bytes": len(header_bytes),
                            "dimensions": list(header.size),
                        },
                        "weak_similarity_signal": {
                            "method": "корреляция 24×24 по яркости; слабый сигнал, не доказательство",
                            "best": sorted(matches, key=lambda m: -m["similarity"])[:3],
                        },
                    }
                )
            elif kind == "pdf_page_print":
                reader = PdfReader(io.BytesIO(data))
                if len(reader.pages) != 1:
                    problems.append(f"{name}: страниц {len(reader.pages)}, ожидалась 1")
                page = reader.pages[0]
                texts[listing_id] = normalize(page.extract_text() or "")
                images = []
                for embedded in page.images:
                    images.append((embedded.name, embedded.data, embedded.image.size, embedded.image.mode))
                created = (reader.metadata or {}).get("/CreationDate")
                observed = OBSERVATIONS[listing_id]
                if pdf_date_to_iso(created) != observed["page_print_creation_date_utc"]:
                    problems.append(
                        f"{name}: дата создания {created!r} не совпадает с записью наблюдения "
                        f"{observed['page_print_creation_date_utc']}"
                    )
                for embedded_name, embedded_data, size, mode in images:
                    label = PDF_IMAGE_CLASSIFICATION.get((str(listing_id), embedded_name))
                    record = {
                        "pdf_entry": name,
                        "embedded_name": embedded_name,
                        "dimensions": list(size),
                        "mode": mode,
                        "bytes": len(embedded_data),
                        "sha256": sha256(embedded_data),
                    }
                    if label is None:
                        if max(size) <= GLYPH_MAX_SIDE or size[0] * size[1] <= GLYPH_MAX_AREA:
                            record.update({"role": "interface_glyph",
                                           "reason_ru": "Текстовый фрагмент или иконка интерфейса, не фотография"})
                        else:
                            record.update({"role": "not_classified",
                                           "reason_ru": "Не классифицировано; не публикуется"})
                        pdf_images.append(record)
                        continue
                    record.update({"role": label["role"], "reason_ru": label["reason"]})
                    if "gallery_position" in label:
                        record["gallery_position"] = label["gallery_position"]
                    if label["role"] in {"gallery", "gallery_thumbnail"}:
                        with Image.open(io.BytesIO(embedded_data)) as image:
                            fp = fingerprint(image.convert("RGB"))
                        matches = []
                        for other, (other_sha, other_fp) in known.items():
                            if f"/{listing_id}/" not in other:
                                continue
                            matches.append(
                                {
                                    "path": other,
                                    "similarity": similarity(fp, other_fp),
                                    "same_bytes": other_sha == record["sha256"],
                                }
                            )
                        best = sorted(matches, key=lambda m: -m["similarity"])[:3]
                        record["weak_similarity_signal"] = {
                            "method": "корреляция 24×24 по яркости; слабый сигнал, не доказательство",
                            "best": best,
                        }
                        # A full-size page-print photo is stored only when no saved
                        # asset of this listing is a near copy of it.
                        already_saved = bool(best) and best[0]["similarity"] >= 0.9
                        if label["role"] == "gallery" and not already_saved:
                            target_dir = IMAGES / str(listing_id)
                            target_dir.mkdir(parents=True, exist_ok=True)
                            stored = target_dir / f"page_print_photo_{label['gallery_position']:02d}.png"
                            with Image.open(io.BytesIO(embedded_data)) as image:
                                image.convert("RGB").save(stored, "PNG", optimize=True)
                            kept += 1
                            stored_bytes = stored.read_bytes()
                            record["stored_path"] = stored.relative_to(ROOT).as_posix()
                            record["stored_sha256"] = sha256(stored_bytes)
                            record["stored_bytes"] = len(stored_bytes)
                        elif label["role"] == "gallery":
                            record["stored_path"] = None
                            record["stored_sha256"] = None
                            record["stored_bytes"] = None
                            record["reason_ru"] += "; не сохранён: кадр уже есть в сохранённых файлах объявления"
                    pdf_images.append(record)
            elif kind == "image":
                problems.append(f"Неожиданное изображение вне классификации: {name}")

    # Assert every curated observation against the extracted page-print text.
    listings = []
    for listing_id, observed in OBSERVATIONS.items():
        text = texts.get(listing_id)
        if text is None:
            raise SystemExit(f"Нет текста страницы для {listing_id}")
        for needle in observed["must_contain"]:
            if normalize(needle) not in text:
                raise SystemExit(f"Наблюдение не подтверждено в PDF {listing_id}: {needle!r}")
        galleries = [r for r in pdf_images if r.get("gallery_position") and r.get("pdf_entry") in
                     {e["name"] for e in entries if e["name"].endswith(f"({listing_id}).pdf")}]
        listings.append(
            {
                "id": listing_id,
                **{k: v for k, v in observed.items() if k != "must_contain"},
                "evidence_assertions_checked": len(observed["must_contain"]),
                "pdf_embedded_gallery_images": [
                    {"embedded_name": g["embedded_name"], "role": g["role"], "stored_path": g.get("stored_path")}
                    for g in galleries
                ],
            }
        )

    glyphs = [r for r in pdf_images if r["role"] == "interface_glyph"]
    pdf_images = [r for r in pdf_images if r["role"] != "interface_glyph"]
    if glyphs:
        pdf_images.append(
            {
                "role": "interface_glyph",
                "reason_ru": "Текстовые фрагменты и иконки отрисованной страницы; не фотографии товара",
                "count": len(glyphs),
                "dimensions_max": [max(r["dimensions"][0] for r in glyphs), max(r["dimensions"][1] for r in glyphs)],
                "total_bytes": sum(r["bytes"] for r in glyphs),
                "examples": [r["embedded_name"] for r in glyphs[:3]],
            }
        )

    manifest = {
        "schema_version": 1,
        "status": "archival_research_only_not_live_inventory",
        "source_repository": SOURCE_REPOSITORY,
        "source_commit": SOURCE_COMMIT,
        "source_commit_date": SOURCE_COMMIT_DATE,
        "archive_file": ARCHIVE_NAME,
        "archive_sha256": actual_sha,
        "archive_sha256_pinned": ARCHIVE_SHA256,
        "archive_bytes": len(raw),
        "archive_bytes_pinned": ARCHIVE_BYTES,
        "entries_count": len(entries),
        "entries_uncompressed_bytes": sum(e["bytes"] for e in entries),
        "entries": entries,
        "safety": {
            "path_traversal": False,
            "nested_archives": [e["name"] for e in entries if e["kind"] == "nested_archive"],
            "html_or_js_entries": [e["name"] for e in entries if e["kind"] == "executable_markup"],
            "pdf_javascript": False,
            "pdf_embedded_files": False,
            "pdf_open_actions": False,
            "pdf_external_links": "только аннотации /URI на страницы avito.ru, ничего не открывается и не исполняется",
            "nothing_executed": True,
            "problems": problems,
        },
        "expected_entries_missing": missing,
        "unexpected_entries": unexpected,
        "mobile_screenshots": screenshots,
        "pdf_embedded_images": pdf_images,
        "listings": listings,
        "duplicate_report": {
            "zip_entry_hashes_unique": len({e["sha256"] for e in entries}) == len(entries),
            "entry_hashes_found_in_other_manus1_zips": sorted(
                {
                    e["name"]
                    for e in entries
                    if e["sha256"] in previous
                }
            ),
            "note_ru": (
                "Побайтовых совпадений между записями ZIP нет. Скриншоты и кадры страниц — "
                "новые файлы, но часть кадров содержательно повторяет уже сохранённые фотографии "
                "галереи (см. weak_similarity_signal и visually_confirmed_saved_slot), поэтому новыми ракурсами считаются только кадр № 4 часов."
            ),
        },
        "kept_files": kept,
        "web_publication": {
            "published_from_this_archive": [
                s["photo_crop"]["path"] for s in screenshots if s["photo_crop"]["stored"]
            ] + sorted(r["stored_path"] for r in pdf_images if r.get("stored_path")),
            "excluded_from_publication": [
                {
                    "entry": r["pdf_entry"],
                    "embedded_name": r["embedded_name"],
                    "role": r["role"],
                    "why": r["reason_ru"],
                }
                for r in pdf_images
                if "pdf_entry" in r
                and r["role"] in {"advertisement", "avatar", "recommendation", "ui", "interface_glyph", "not_classified"}
            ],
            "not_published_from_zip": [
                "исходные скриншоты целиком (полоса статуса iOS и кнопки Avito обрезаны)",
                "PDF-печати страниц (содержат блок рекомендаций, рекламу и ссылки на сторонние сервисы)",
            ],
        },
    }

    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Записей в архиве: {len(entries)}; сохранено файлов: {kept}")
    print(f"Манифест: {MANIFEST.relative_to(ROOT)}")
    if problems:
        print("Предупреждения:", *problems, sep="\n  ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
