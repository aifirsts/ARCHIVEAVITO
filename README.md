# Beauty Supply — архивная витрина и аудит источников

> GitHub Actions sync trigger: 2026-10-28 — запуск workflow для проверки и публикации сайта.

**Сайт магазина: [`site/public/`](site/public/index.html)** — собственная вёрстка, 16 страниц, 150 изображений, адаптивные карточки и доступная навигация.

Витрина использует 14 товаров из архива профиля Avito: 53 фото-превью профиля, 74 миниатюры и 38 крупных JPEG из 13 отдельных карточек и 53 превью в профиле.

**Статус данных:** владелец подтвердил в переписке, что профиль Avito и магазин принадлежат ему. Источники — снимки архивов и локальные подтверждённые файлы.

**Слой 28.10.2026:** продавец прислал свежие цены (Max face cream 11 500 ₽, Max eye cream 6 800 ₽, SPF 30 мойсчерайзер 4 900 ₽, Biotech MD cream 10 400 ₽, Biotech MD serum 11 500 ₽).

**Для разработчика:** контракт данных — [`handoff/README.md`](handoff/README.md) и [`handoff/storefront.json`](handoff/storefront.json); готовый сайт — [`site/public/`](site/public/index.html).

**[Финальный аудит и дальнейшие шаги](FINAL_AUDIT.md)** — сводная проверка всех восьми ZIP в `MANUS1` и готовности каталога.

## Публикация сайта

Рабочий процесс [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) при пуше в `main` (или запуске вручную — `workflow_dispatch`) прогоняет проверки и публикует `site/public`.

**Статус на 28.10.2026: публикация не выполнена** — у аккаунта владельца репозитория Actions заблокирована биллинговая настройка, но сам workflow готов и запускается при пуше.

## Файлы

- `site/` — **сайт**: `src/site.css`, `src/app.js`, `build.py`, собранный `public/`; см. [`site/README.md`](site/README.md).
- [`catalog.json`](catalog.json) — 14 карточек (цены из снимка, локальные фото, ссылка Avito, расширенные характеристики, примечания к архивной валидации).
- `avito_audit/attachments_fw_2026_10_28/` + [`avito_audit/ATTACHMENTS_FW_2026_10_28.md`](avito_audit/ATTACHMENTS_FW_2026_10_28.md) — разбор восьмого архива: 10 записей, хеши, свежие цены и фото.
- `avito_audit/attachments_avitos/` + [`avito_audit/ATTACHMENTS_2026_10_25.md`](avito_audit/ATTACHMENTS_2026_10_25.md) — разбор седьмого архива: 10 записей, хеши, новые фото и печати страниц.
- [`official_assets/`](official_assets/) — 13 локальных иллюстраций производителей (для 13 карточек); [`manifest.json`](official_assets/manifest.json) — реестр файлов и контрольных сумм.
- [`avito_audit/images/`](avito_audit/images/) — 53 JPEG 208×208 из архивного HTML, разложены по ID объявления.
- [`avito_audit/item_pages/`](avito_audit/item_pages/) — `data.json` с полным текстом продавца, характеристиками, двумя версиями описаний и разметкой карточек.
- [`avito_audit/images_manifest.json`](avito_audit/images_manifest.json) — 55 ссылок на миниатюры с архивными путями и SHA-256 локальных файлов.
- [`avito_audit/OFFICIAL_RESEARCH.md`](avito_audit/OFFICIAL_RESEARCH.md) — сопоставление всех 14 товаров с официальными страницами, оговорками по составу и брендам.
- [`avito_audit/REPORT.md`](avito_audit/REPORT.md) — происхождение ZIP и архивный аудит; `products.csv` и `snapshot.json` — машиночитаемый реестр товаров.
- `avito_audit/extract_images.py` — извлечение старых превью; `avito_audit/extract_item_pages.py` — извлечение новых страниц и JPEG по трём ZIP.

## Локальный просмотр

```bash
python handoff/generate.py
python site/build.py
cd site/public && python -m http.server 8080 --bind 0.0.0.0
```

Откройте `http://localhost:8080/`. Для статического хостинга публикуйте **только `site/public`** (это делает `deploy.yml`), не корень репозитория.

Проверки:

```bash
python -m unittest discover -s tests -v     # 47 офлайн-тестов (архив, пакет, сборка, ссылки, хеши, новый слой)
node --check site/src/app.js
python site/tests/browser_smoke.py          # Chromium: десктоп 1440×950 и мобильный 390×844
```

Дополнительно: axe-core (0 нарушений на страницах × 2 ширины), сверка всех 150 опубликованных изображений по SHA-256 и контроль воспроизводимости сборки.

## Перед коммерческой публикацией

Подтвердить у владельца каждого товара актуальное наличие, цену, состояние, состав, фото и возможность заказа; сам сайт не принимает оплату и не подтверждает статус товаров.
