"""Real-browser smoke test for the generated storefront.

Not part of ``unittest`` discovery: it needs Playwright and a Chromium build.

    python -m pip install playwright && python -m playwright install chromium
    python site/build.py
    python site/tests/browser_smoke.py            # serves site/public itself
    python site/tests/browser_smoke.py --base-url http://127.0.0.1:8080

Checks desktop (1440x950) and mobile (390x844): console/network errors, all 14
cards, search, filters, sorting, keyboard gallery navigation, the missing-slot
state, the lightbox and the archive-price disclaimer.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

PUBLIC = Path(__file__).resolve().parents[1] / "public"
FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)
        print(f"  ✗ {message}")
    else:
        print(f"  ✓ {message}")


def serve(directory: Path):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def run(base: str, executable: str | None = None) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable) if executable else p.chromium.launch()
        for label, viewport in (("desktop", {"width": 1440, "height": 950}), ("mobile", {"width": 390, "height": 844})):
            print(f"\n[{label} {viewport['width']}x{viewport['height']}]")
            context = browser.new_context(viewport=viewport, locale="ru-RU")
            page = context.new_page()
            problems: list[str] = []
            page.on("console", lambda m: problems.append(f"console.{m.type}: {m.text}")
                    if m.type == "error" else None)
            page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
            page.on("requestfailed", lambda r: problems.append(f"requestfailed: {r.url}"))

            page.goto(f"{base}/index.html", wait_until="networkidle")
            check(page.locator("[data-card]").count() == 14, "на главной 14 карточек")
            check(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"),
                  "нет горизонтальной прокрутки на главной")
            # lazy images only start loading when scrolled near the viewport
            page.evaluate(
                """async () => {
                  const step = Math.round(window.innerHeight * 0.75);
                  for (let y = 0; y < document.body.scrollHeight; y += step) {
                    window.scrollTo(0, y);
                    await new Promise((resolve) => setTimeout(resolve, 180));
                  }
                  window.scrollTo(0, 0);
                }"""
            )
            try:
                page.wait_for_function(
                    "Array.from(document.images).every(i => i.complete && i.naturalWidth > 0)",
                    timeout=20000,
                )
                all_loaded = True
            except Exception:  # noqa: BLE001 - reported as a failed check below
                all_loaded = False
            check(all_loaded, "все изображения главной загрузились")
            check(page.evaluate(
                "Array.from(document.images).every(i => i.complete && (i.naturalWidth > 0 || i.loading === 'lazy'))"),
                "нет «битых» изображений (0 байт при загруженном состоянии)")

            page.fill("#catalogue-search", "hourglass")
            page.wait_for_timeout(150)
            check(page.locator("[data-card]:visible").count() == 3, "поиск «hourglass» → 3 товара")
            check(page.inner_text("#result-count").startswith("3 из"), "счётчик результатов обновился")

            page.fill("#catalogue-search", "чехол")
            page.wait_for_timeout(150)
            check(page.locator("[data-card]:visible").count() == 2, "поиск «чехол» → 2 товара")

            page.fill("#catalogue-search", "")
            page.click('[data-filter-category="Часы"]')
            page.wait_for_timeout(150)
            check(page.locator("[data-card]:visible").count() == 1, "фильтр «Часы» → 1 товар")
            page.click('[data-filter-category="all"]')

            page.select_option("#catalogue-sort", "price-asc")
            page.wait_for_timeout(150)
            prices = page.eval_on_selector_all("[data-card]:visible", "els => els.map(e => Number(e.dataset.price))")
            check(prices == sorted(prices), "сортировка по цене работает")

            page.click("h1")
            page.keyboard.press("/")
            check(page.evaluate("document.activeElement.id") == "catalogue-search",
                  "клавиша «/» переводит фокус в поиск")

            # the header search is a native GET form (no JS URL assignment)
            page.fill("#header-search-input", "omega")
            page.press("#header-search-input", "Enter")
            page.wait_for_url("**q=omega**")
            page.wait_for_timeout(200)
            check(page.locator("[data-card]:visible").count() == 1,
                  "поиск из шапки открывает каталог с одним результатом")
            check(page.eval_on_selector("#catalogue-search", "e => e.value") == "omega",
                  "запрос из шапки подставлен в поиск каталога")

            for pid in ("8296456393", "8350792227"):
                page.goto(f"{base}/item/{pid}.html", wait_until="networkidle")
                check(page.locator("[data-gallery-thumb]").count() >= 1, f"{pid}: галерея отрисована")
                check(page.locator("a[href^='https://www.avito.ru/']").count() >= 1,
                      f"{pid}: есть ссылка на объявление Avito")
                check("Архивная цена" in page.inner_text("body"), f"{pid}: цена помечена как архивная")
                check(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"),
                      f"{pid}: нет горизонтальной прокрутки")

            page.goto(f"{base}/item/8296456393.html", wait_until="networkidle")
            page.keyboard.press("ArrowRight")
            page.keyboard.press("ArrowRight")
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(500)
            check(page.get_attribute("[data-gallery]", "data-current-index") == "3",
                  "стрелки клавиатуры переключают на 4-й кадр")
            check("25.10.2026" in page.inner_text("[data-gallery-source]"),
                  "4-й кадр помечен новым источником")
            check(page.locator("[data-gallery-evidence] a").count() == 1,
                  "у 4-го кадра есть ссылка на бейдж «4 из 9»")
            page.keyboard.press("End")
            page.wait_for_timeout(300)
            check("ФАЙЛА НЕТ" in page.inner_text("[data-gallery-source]").upper(),
                  "позиция № 9 показана как отсутствующая, без подстановки")
            page.keyboard.press("Home")
            page.wait_for_timeout(300)
            page.click(".gallery__stage")
            page.wait_for_timeout(300)
            check(page.evaluate("document.getElementById('lightbox').open"), "лайтбокс открывается")
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
            check(not page.evaluate("document.getElementById('lightbox').open"), "лайтбокс закрывается по Esc")

            page.goto(f"{base}/sources.html", wait_until="networkidle")
            sources = page.inner_text("body")
            check("Attachments-Avitos.zip" in sources, "страница источников описывает новый архив")
            check("7d1eca79385ba06d702f0812eca8b5ee70990295295ec2b06442a28e33b5d6d0" in sources,
                  "на странице источников опубликован SHA-256 архива")

            real = [p for p in problems if "favicon" not in p]
            check(not real, f"нет ошибок консоли и сети ({len(real)} шт.)")
            for item in real[:5]:
                print("      ·", item)
            context.close()
        browser.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url")
    parser.add_argument("--executable", help="путь к Chromium, если он не установлен через playwright install")
    args = parser.parse_args()
    if args.base_url:
        run(args.base_url.rstrip("/"), args.executable)
    else:
        if not (PUBLIC / "index.html").is_file():
            print("Сначала соберите сайт: python site/build.py")
            return 2
        httpd, base = serve(PUBLIC)
        try:
            run(base, args.executable)
        finally:
            httpd.shutdown()
    print()
    if FAILURES:
        print(f"Провалено проверок: {len(FAILURES)}")
        return 1
    print("Браузерные проверки пройдены.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
