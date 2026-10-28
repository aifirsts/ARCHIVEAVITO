# Beauty Supply — витрина магазина и архивный аудит источников

**Сайт: [`site/public/`](site/public/index.html)** — готовый статический магазин-витрина на 18 страниц,
150 фотографий, собственный дизайн, SEO-разметка, `sitemap.xml`, `robots.txt`, `404.html`.
Основной адрес — **[usaforru.shop](https://usaforru.shop)** (Porkbun Static Hosting).

**Живое зеркало: [aifirsts.github.io/MATRIX2](https://aifirsts.github.io/MATRIX2/)** — тот же сайт,
собранный в каталог [`docs/`](docs/index.html) и опубликованный через **GitHub Pages**
(ветка `main`, папка `/docs`, HTTPS). Зеркало отличается только каноническими адресами и
отсутствием `CNAME`, чтобы не перехватывать домен магазина.

> Пока источник Pages не переключён на папку `/docs`, сайт отдаётся из корня ветки и открывается
> по адресу [`/MATRIX2/docs/`](https://aifirsts.github.io/MATRIX2/docs/). Переключение — разовая
> настройка в **Settings → Pages → Source: Deploy from a branch → `main` / `/docs`**; пересборка
> после неё не нужна, потому что канонические адреса уже указывают на `pages_url`.

> Витрина продаёт не «в корзину», а через продавца: каждая карточка ведёт на конкретное объявление Avito,
> где подтверждаются цена, наличие и комплектация. Онлайн-оплаты на сайте нет — это осознанное решение,
> а не незаконченная функция.

## Что обновилось 28.10.2026

| Область | Было | Стало |
| --- | --- | --- |
| Позиционирование | «архивный каталог, не магазин» | **витрина магазина**: hero, бренды, подбор по задаче, шаги покупки, FAQ |
| Страницы | 16 | **18** (`index`, `podbor`, `sources`, `404` + 14 карточек) |
| Адреса карточек | `item/7942405497.html` | `item/7942405497-hourglass-ambient-lighting-blush.html` — читаемые SEO-слаги |
| Главная | таблица фактов аудита | hero + блок доверия + бренды + каталог + прайс продавца + подборки + FAQ |
| Подбор | — | **`podbor.html`**: 5 сценариев (SPF, антивозрастной уход, тело, макияж, аксессуары) + сводная таблица цен |
| Карточка товара | аудит-отчёт | покупной блок (цена, преимущества, CTA), **похожие лоты**, затем происхождение фото и ограничения |
| SEO | title/description | canonical, OG/Twitter-карточка 1200×630, JSON-LD (`Store`, `Product`, `BreadcrumbList`, `FAQPage`), `sitemap.xml`, `robots.txt` |
| Дизайн | архивная типографика | сохранена база + «магазинный» слой: hero-фото, trust-полоса, бренд-пилюли, теги, шаги, аккордеон FAQ, мини-карточки |
| Публикация | не выполнялась | GitHub Pages из `docs/` (живое зеркало) + пошаговый runbook и `deploy/publish_porkbun.py` (FTPS) для домена |
| Тесты | 37 | **74 офлайн-проверки** + HTML5/a11y-валидация 18 страниц сайта и 18 страниц зеркала + headless-DOM прогон поиска, фильтров и галереи в двух раскладках |

Подробный отчёт: [`SITE_UPDATES.md`](SITE_UPDATES.md). Публикация: [`deploy/README.md`](deploy/README.md).

## Структура сайта

| Страница | Назначение |
| --- | --- |
| [`index.html`](site/public/index.html) | витрина: hero, доверие, бренды, каталог с поиском/фильтрами/тегами, прайс продавца 28.10, подборки, 3 шага покупки, FAQ |
| [`podbor.html`](site/public/podbor.html) | пять подборок по задаче + сводная таблица «архивная цена / цена продавца / продавец» |
| `item/<id>-<slug>.html` × 14 | карточка: галерея с источниками кадров, цена с датой, преимущества, CTA в Avito, похожие лоты, характеристики, бренд, происхождение фото, честные ограничения |
| [`sources.html`](site/public/sources.html) | происхождение данных: 8 ZIP с SHA-256, слои 25.10 / 28.10, разделение слоёв, что не публикуется, домен и публикация |
| [`404.html`](site/public/404.html) | страница ошибки с подборкой популярных лотов |

## Данные

| Файл | Что внутри |
| --- | --- |
| [`catalog.json`](catalog.json) | 14 карточек: архивные цены, старые цены, ссылки Avito, характеристики, материалы производителей, свежие цены продавца |
| [`handoff/storefront.json`](handoff/storefront.json) | пакет данных для сборки (генерируется `handoff/generate.py`, детерминированно) |
| [`avito_audit/`](avito_audit/) | разборы восьми ZIP, извлечённые JPEG, PDF-печати, распознанные сообщения продавца |
| [`official_assets/`](official_assets/) | 13 иллюстраций производителей + манифест SHA-256 |
| `site/site_config.json` | бренд, домен, hero-тексты, FAQ, подборки — вся «маркетинговая» правка без Python |
| `site/src/assets/hero.jpg`, `og-cover.jpg` | сгенерированные иллюстрации витрины (не фото товара) |

## Сборка и проверки

**Одна команда — все проверки (то же, что CI):**

```bash
bash scripts/verify.sh          # 9 групп проверок, код возврата 0 = всё зелёное
bash scripts/verify.sh --offline   # без сети (пропускает html-validate и npm)
```

По шагам:

```bash
python -m pip install -r requirements-dev.txt   # Pillow
python handoff/generate.py                      # пакет данных
python site/build.py                            # пересобрать site/public и зеркало docs/
python site/build.py --check                    # проверить, что обе сборки = источники
python -m unittest discover -s tests -v         # 74 офлайн-теста
node --check site/src/app.js
npx --yes html-validate@11 "site/public/**/*.html" "docs/**/*.html"   # HTML5 + доступность
node site/tests/dom/dom_smoke.js                # поиск/фильтры/галерея в jsdom (нужен npm install в site/tests/dom)
SITE_DIR=docs SITE_ORIGIN=https://aifirsts.github.io/MATRIX2/ node site/tests/dom/dom_smoke.js   # то же для зеркала
python3 deploy/publish_porkbun.py --dry-run     # план загрузки на Porkbun
```

Локальный просмотр:

```bash
cd site/public && python -m http.server 8080 --bind 0.0.0.0
```

## Публикация

### GitHub Pages (живое зеркало, работает сейчас)

Pages отдаёт каталог [`docs/`](docs/index.html) ветки `main`: настройка
**Settings → Pages → Source: Deploy from a branch, Branch: `main`, Folder: `/docs`**.
Никаких секретов и workflow не нужно — GitHub собирает статику своим внутренним сборщиком.

```bash
python site/build.py        # собирает site/public и docs/ одновременно
bash scripts/verify.sh      # 8 групп проверок, включая зеркало
git add docs && git commit -m "Rebuild Pages mirror" && git push origin main
```

Адрес зеркала задаётся в [`site/site_config.json`](site/site_config.json) полем `pages_url`
(по умолчанию `https://aifirsts.github.io/MATRIX2`). При смене имени репозитория или переходе
на `*.github.io` достаточно поменять это поле и пересобрать — canonical, Open Graph, JSON-LD,
`sitemap.xml` и `robots.txt` зеркала обновятся сами.

Особенности зеркала:

- собирается с `pages_url` как каноническим адресом, а не с доменом магазина;
- **не содержит `CNAME`**: иначе GitHub Pages попытался бы забрать `usaforru.shop` у Porkbun;
- все внутренние ссылки относительные, поэтому сайт работает в подкаталоге `/MATRIX2/`;
- `404.html` ссылается на абсолютные пути с префиксом (`/MATRIX2/...`), потому что Pages отдаёт
  эту страницу для любого несуществующего глубокого URL, сохраняя путь в адресной строке;
- манифест (`site.webmanifest`) использует относительные `start_url` и `scope`.

### Домен usaforru.shop (Porkbun)

1. Porkbun → домен → **Website → Static Hosting → Starter**.
2. Взять FTP-доступы из блока **FTP Credentials**.
3. `export $(grep -v '^#' deploy/.env | xargs)` → `python deploy/publish_porkbun.py`.
4. Проверить `https://usaforru.shop/`, `/sitemap.xml`, `/robots.txt` (чек-лист в [`deploy/README.md`](deploy/README.md)).

Альтернативы: панель Porkbun (File Browser) или **GitHub Connect** на ветку `main`, каталог `site/public`.
Workflow [`.github/workflows/publish-porkbun.yml`](.github/workflows/publish-porkbun.yml) публикует по кнопке
(нужны секреты `PORKBUN_FTP_HOST`, `PORKBUN_FTP_USER`, `PORKBUN_FTP_PASS`).

> **GitHub Actions в этом аккаунте заблокированы биллингом:** задания падают за 2–3 секунды
> (`steps: []`, раннер не выдан) — это ограничение аккаунта, а не ошибка кода. Поэтому публикация
> Pages идёт не через Actions, а из закоммиченного каталога `docs/` (внутренний сборщик GitHub
> работает без раннеров). Все проверки выполняются локально командой `bash scripts/verify.sh`;
> после включения Actions они пойдут в CI без правок, включая сверку `docs/` со сборкой.

## Что важно знать о данных

- **Цены не текущие.** Архивный снимок `26.10.2026` + сообщения продавца `28.10.2026` (заявления продавца).
  На каждой карточке обе цены подписаны; актуальную подтверждает продавец в Avito.
- **Четыре слоя фото** не смешиваются: фото объявления, мобильные скриншоты `25.10.2026`, фото из переписки
  `28.10.2026`, иллюстрации производителей. Источник подписан на каждом кадре.
- **Известные пропуски:** у часов `8296456393` нет файла позиции № 9; у лота `8350792227` не сфотографирован
  второй чехол и нет отдельной HTML-карточки. Отсутствующие файлы не подменяются чужими фото.
- **Права:** иллюстрации брендов принадлежат правообладателям; владение магазином не означает разрешение
  на их коммерческое использование. Перед промо-кампанией это нужно согласовать.
- **Отзывы и персональные данные** из исходных HTML не публикуются.

## Документы аудита (история)

- [`SITE_UPDATES.md`](SITE_UPDATES.md) — что именно изменено 28.10.2026 и как проверено.
- [`FINAL_AUDIT.md`](FINAL_AUDIT.md) — сводная проверка восьми ZIP из `usaforyou/MANUS1`.
- [`REPOSITORY_AUDIT.md`](REPOSITORY_AUDIT.md) — повторная проверка репозитория (историческая таблица).
- [`deploy/README.md`](deploy/README.md) — публикация, DNS, SSL, чек-лист, откат.
