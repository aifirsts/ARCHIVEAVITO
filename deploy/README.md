# Публикация сайта: GitHub Pages и Porkbun

Готовый сайт — это **только каталог `site/public`** (18 страниц, 150 изображений,
`robots.txt`, `sitemap.xml`, `404.html`, `CNAME`, `site.webmanifest`).
Корень репозитория публиковать нельзя: там аудит, ZIP-источники и скрипты.

| Куда | Что публикуется | Как |
| --- | --- | --- |
| **GitHub Pages** — <https://aifirsts.github.io/MATRIX2/> | каталог [`docs/`](../docs/index.html) ветки `main` | уже включено; пересобрать и закоммитить |
| **Porkbun** — <https://usaforru.shop> | содержимое `site/public` | FTPS-скрипт или панель (разделы 1–7 ниже) |

## 0. GitHub Pages (зеркало, работает без Actions)

Pages настроен на **Settings → Pages → Deploy from a branch → `main` / `/docs`**.
Публикует внутренний сборщик GitHub — он не требует раннеров, поэтому блокировка
GitHub Actions в аккаунте на него не влияет.

```bash
python -m pip install -r requirements-dev.txt
python site/build.py        # site/public (домен) + docs/ (зеркало) за один прогон
python site/build.py --check
python -m unittest discover -s tests -v          # 74 проверки, из них 8 про зеркало
bash scripts/verify.sh      # то же одной командой
git add docs site/public && git commit -m "Rebuild storefront" && git push origin main
```

После пуша Pages пересобирает сайт за 1–2 минуты; статус —
`gh api repos/aifirsts/MATRIX2/pages/builds --jq '.[0].status'` (`built`), адрес —
`gh api repos/aifirsts/MATRIX2/pages --jq .html_url`.

Правила зеркала (их проверяет [`tests/test_pages_mirror.py`](../tests/test_pages_mirror.py)):

- собирается с `pages_url` из [`site/site_config.json`](../site/site_config.json) как каноническим
  адресом — `canonical`, OG/Twitter, JSON-LD, `sitemap.xml` и `robots.txt` указывают на Pages;
- **не содержит `CNAME`**: иначе Pages стал бы претендовать на `usaforru.shop` и сломал бы Porkbun;
- внутренние ссылки относительные, поэтому всё работает в подкаталоге `/MATRIX2/`;
- `404.html` использует абсолютные ссылки с префиксом `/MATRIX2/...`: Pages отдаёт эту страницу
  для любого несуществующего глубокого URL и сохраняет исходный путь;
- `site.webmanifest` с относительными `start_url`/`scope`, чтобы PWA не уезжала в корень домена.

Если репозиторий переименуют или подключат свой домен — поменяйте `pages_url`,
запустите `python site/build.py` и закоммитьте `docs/`.

## 1. Что нужно от Porkbun

1. Панель Porkbun → домен `usaforru.shop` → иконка **«Домик» (Website)** → **Static Hosting**.
2. Оформить план **Starter** (2 ГБ, TLS-сертификат, FTP + GitHub Connect).
   После оплаты списывается первый месяц/год; тариф можно отменить в любой момент.
3. На странице плана взять блок **FTP Credentials**:
   - FTP Server (например `ftp.porkbun.com`),
   - FTP Username — это сам домен `usaforru.shop`,
   - FTP Password,
   - Server Port `21` (Porkbun требует TLS — наш скрипт использует FTPS).

## 2. Сборка сайта

```bash
python -m pip install -r requirements-dev.txt   # нужен Pillow
python handoff/generate.py                     # пакет данных (детерминированный)
python site/build.py                           # пересобрать site/public
python site/build.py --check                   # убедиться, что сборка совпадает с источниками
python -m unittest discover -s tests -v        # 74 офлайн-проверки
```

## 3. Загрузка (вариант A — скрипт, без GUI)

```bash
cp deploy/.env.example deploy/.env      # вписать пароль FTP
export $(grep -v '^#' deploy/.env | xargs)
python deploy/publish_porkbun.py --dry-run   # посмотреть список файлов
python deploy/publish_porkbun.py             # загрузить в корень сайта
```

Скрипт использует только стандартную библиотеку Python (`ftplib.FTP_TLS`),
проверяет, что сборка полная, и печатает каждый загруженный файл.
`--prune` дополнительно удаляет в корне файлы, которых больше нет в сборке.

## 4. Загрузка (вариант B — панель Porkbun)

Static Hosting → **File Browser / Editor**: перетащить **содержимое** `site/public`
(не саму папку) в корень. Файл `index.html` должен оказаться в корне.

## 5. Загрузка (вариант C — GitHub Connect)

Static Hosting → **GitHub Connect** → выбрать репозиторий `aifirsts/MATRIX2`,
ветку `main`, каталог публикации `site/public`. Дальше каждый пуш в `main`
публикует сайт автоматически (сборку в репозитории нужно коммитить — workflow
`.github/workflows/validate.yml` проверяет, что `site/public` совпадает с источниками).

## 6. DNS и SSL

- Домен уже в Porkbun, поэтому A/AAAA-записи для статического хостинга Porkbun
  прописываются автоматически. Проверить: `dig +short usaforru.shop`.
- SSL-сертификат Let's Encrypt выпускается автоматически после первого запроса
  к домену; в панели появится статус **Active**. До этого браузер может ругаться.
- Опционально: `www.usaforru.shop` → CNAME на `usaforru.shop`
  (Porkbun → DNS → Add Record). Сайт использует относительные ссылки,
  поэтому `www` работает без правок.

## 7. Проверка после публикации

```bash
curl -I https://usaforru.shop/                 # 200 и text/html
curl -s https://usaforru.shop/robots.txt       # есть Sitemap:
curl -I https://usaforru.shop/404.html         # 200 (Porkbun отдаёт файл 404)
curl -I https://usaforru.shop/assets/og-cover.jpg
```

Чек-лист:

- [ ] главная открывается по `https://usaforru.shop/`
- [ ] 14 карточек кликабельны, у каждой открывается страница товара
- [ ] поиск и фильтры работают (`/?q=SPF`, `/?tag=makeup`)
- [ ] `sitemap.xml` и `robots.txt` доступны
- [ ] CSS и JS отдаются с кодом 200 (хеш версии в ссылке)
- [ ] нет mixed content: все ссылки относительные, кроме Avito
- [ ] домен добавлен в Google Search Console и Яндекс.Вебмастер,
      отправлена карта `https://usaforru.shop/sitemap.xml`

## 8. Откат

Сборка детерминирована: `git checkout <commit> -- site/public && python deploy/publish_porkbun.py`
вернёт предыдущую версию на домене. На GitHub Pages откат — это коммит, откатывающий `docs/`:
`git checkout <commit> -- docs && git commit -m "Rollback Pages mirror" && git push origin main`.
ZIP-архив каждой сборки также лежит в артефактах workflow `validate.yml`
(`beauty-supply-site` — сайт, `beauty-supply-pages-mirror` — зеркало).

## Ограничения

- Сайт статический: нет корзины, оплаты и базы заказов. Это витрина + переход в Avito.
- Цены в каталоге — архивный снимок `26.10.2026` и сообщения продавца `28.10.2026`;
  они не являются публичной офертой, актуальность подтверждает продавец.
