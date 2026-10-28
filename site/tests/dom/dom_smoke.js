/* Headless DOM checks for the built storefront — no browser required.
 *
 *   cd site/tests/dom && npm install && node dom_smoke.js
 *   node site/tests/dom/dom_smoke.js            # needs jsdom resolvable
 *   SITE_DIR=docs SITE_ORIGIN=https://aifirsts.github.io/MATRIX2/ node dom_smoke.js
 *
 * Runs site/src/app.js against the real built markup in jsdom and checks
 * search, category/tag filters, sorting, the discount filter, URL state, the
 * product gallery (thumbnails, keyboard, missing slot, lightbox) and that no
 * page raises a JavaScript error. Exit code 1 on any failure.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..", "..");
// SITE_DIR/SITE_ORIGIN let the same checks run against the GitHub Pages mirror
// (docs/), which differs only in its mount path and canonical origin.
const PUBLIC = path.resolve(ROOT, process.env.SITE_DIR || path.join("site", "public"));
const ORIGIN = process.env.SITE_ORIGIN || "https://usaforru.shop/";
const MOUNT = new URL(ORIGIN).pathname.replace(/\/$/, "");
const APP = fs.readFileSync(path.join(PUBLIC, "assets", "app.js"), "utf8");
const MANIFEST = JSON.parse(fs.readFileSync(path.join(PUBLIC, "assets", "images.json"), "utf8"));

function localPath(src) {
  return src.startsWith(MOUNT + "/") ? src.slice(MOUNT.length + 1) : src;
}

let failures = 0;
function check(condition, message) {
  if (condition) {
    console.log("  ok   " + message);
  } else {
    failures += 1;
    console.log("  FAIL " + message);
  }
}

function load(pageRel, query = "") {
  const html = fs.readFileSync(path.join(PUBLIC, pageRel), "utf8");
  const errors = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on("jsdomError", (error) => errors.push(String(error)));
  virtualConsole.on("error", (...args) => errors.push(args.join(" ")));
  const dom = new JSDOM(html, {
    url: ORIGIN + pageRel + query,
    runScripts: "outside-only",
    pretendToBeVisual: true,
    virtualConsole,
  });
  const { window } = dom;
  window.matchMedia =
    window.matchMedia ||
    ((query_) => ({
      matches: false,
      media: query_,
      addEventListener() {},
      removeEventListener() {},
      addListener() {},
      removeListener() {},
      onchange: null,
      dispatchEvent() {
        return false;
      },
    }));
  window.HTMLElement.prototype.scrollIntoView = function () {};
  window.eval(APP);
  window.document.dispatchEvent(new window.Event("DOMContentLoaded", { bubbles: true }));
  return { window, document: window.document, errors };
}

function visibleCards(document) {
  return [...document.querySelectorAll("#product-grid li")].filter((li) => !li.hidden);
}

console.log("[главная: поиск, фильтры, теги, сортировка]");
{
  const { window, document, errors } = load("index.html");
  check(document.querySelectorAll("[data-card]").length === 14, "14 карточек в DOM");

  const search = document.getElementById("catalogue-search");
  search.value = "hourglass";
  search.dispatchEvent(new window.Event("input", { bubbles: true }));
  check(visibleCards(document).length === 3, "поиск «hourglass» → 3");
  check(document.getElementById("result-count").textContent === "3 из 14", "счётчик «3 из 14»");

  search.value = "чехол";
  search.dispatchEvent(new window.Event("input", { bubbles: true }));
  check(visibleCards(document).length === 2, "поиск «чехол» → 2");

  search.value = "";
  search.dispatchEvent(new window.Event("input", { bubbles: true }));
  document.querySelector('[data-filter-category="Часы"]').click();
  check(visibleCards(document).length === 1, "категория «Часы» → 1");
  document.querySelector('[data-filter-category="all"]').click();

  document.querySelector('[data-filter-tag="spf"]').click();
  check(visibleCards(document).length === 2, "тег «С SPF» → 2");
  check(window.location.search.includes("tag=spf"), "URL содержит tag=spf");
  document.querySelector('[data-filter-tag="spf"]').click();
  check(visibleCards(document).length === 14, "повторный клик по тегу снимает фильтр");

  const sort = document.getElementById("catalogue-sort");
  sort.value = "price-asc";
  sort.dispatchEvent(new window.Event("change", { bubbles: true }));
  const prices = visibleCards(document).map((li) =>
    Number(li.querySelector("[data-card]").dataset.price)
  );
  check(
    JSON.stringify(prices) === JSON.stringify([...prices].sort((a, b) => a - b)),
    "сортировка по цене"
  );

  const discount = document.getElementById("filter-discount");
  discount.checked = true;
  discount.dispatchEvent(new window.Event("change", { bubbles: true }));
  check(visibleCards(document).length === 7, "только со скидкой → 7");

  document.getElementById("reset-filters").click();
  check(visibleCards(document).length === 14, "сброс фильтров возвращает 14");
  check(!window.location.search, "сброс очищает query string");
  check(errors.length === 0, "нет ошибок JS на главной" + (errors[0] ? ": " + errors[0] : ""));
}

console.log("[главная: состояние из URL]");
{
  const { window, document, errors } = load("index.html", "?q=SPF");
  check(visibleCards(document).length === 2, "?q=SPF → 2 лота");
  check(document.getElementById("catalogue-search").value === "SPF", "поле поиска из URL");
  check(errors.length === 0, "нет ошибок JS при старте из URL");
}

console.log("[карточка товара: галерея, пропуск, лайтбокс]");
{
  const watch = Object.entries(MANIFEST.product_pages).find(([id]) => id === "8296456393")[1];
  const { window, document, errors } = load(watch);
  const gallery = document.querySelector("[data-gallery]");
  const thumbs = document.querySelectorAll("[data-gallery-thumb]");
  check(thumbs.length === 9, "9 миниатюр (8 кадров + пропуск)");
  const firstSrc = document.querySelector(".gallery__stage img").getAttribute("src");
  check(!!firstSrc, "первый кадр отрисован");
  check(gallery.getAttribute("data-current-index") === "0", "стартовый индекс 0");

  thumbs[2].click();
  const after = document.querySelector(".gallery__stage img").getAttribute("src");
  check(after !== firstSrc && after.includes("03"), "клик по миниатюре меняет кадр");
  check(gallery.getAttribute("data-current-index") === "2", "индекс = 2 после клика");
  check(document.querySelector("[data-gallery-caption]").textContent.length > 0, "подпись кадра заполнена");
  check(document.querySelector("[data-gallery-source]").textContent.length > 0, "источник кадра указан");

  document.dispatchEvent(new window.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
  check(gallery.getAttribute("data-current-index") === "3", "ArrowRight → индекс 3");

  document.dispatchEvent(new window.KeyboardEvent("keydown", { key: "End", bubbles: true }));
  check(gallery.getAttribute("data-current-index") === "8", "End → последняя позиция");
  check(!!document.querySelector(".gallery__missing"), "позиция № 9 показана как отсутствующая");
  check(
    /файла нет/i.test(document.querySelector("[data-gallery-source]").textContent),
    "источник = «файла нет»"
  );

  document.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Home", bubbles: true }));
  check(gallery.getAttribute("data-current-index") === "0", "Home → первый кадр");

  const lightbox = document.getElementById("lightbox");
  document.querySelector(".gallery__stage").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  check(!!lightbox.open || lightbox.hasAttribute("open"), "лайтбокс открывается");
  lightbox.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  check(!lightbox.open && !lightbox.hasAttribute("open"), "Escape закрывает лайтбокс");
  check(errors.length === 0, "нет ошибок JS на карточке" + (errors[0] ? ": " + errors[0] : ""));
}

console.log("[страница подбора]");
{
  const { document, errors } = load("podbor.html");
  check(document.querySelectorAll("[data-card]").length === 14, "14 карточек на странице подбора");
  check(document.querySelectorAll(".routine-section").length === 5, "5 подборок отрисованы");
  check(document.querySelectorAll("table").length >= 1, "есть сводная таблица");
  check(errors.length === 0, "нет ошибок JS на подборе" + (errors[0] ? ": " + errors[0] : ""));
}

console.log("[404]");
{
  const { document, errors } = load("404.html");
  check(document.querySelectorAll(".mini").length === 4, "4 рекомендации на 404");
  const sources = [...document.querySelectorAll(".mini img")].map((img) => img.getAttribute("src"));
  check(
    sources.every((src) => fs.existsSync(path.join(PUBLIC, localPath(src)))),
    "картинки 404 ведут на существующие файлы"
  );
  check(errors.length === 0, "нет ошибок JS на 404" + (errors[0] ? ": " + errors[0] : ""));
}

console.log("[все страницы: JS без ошибок, обязательные элементы]");
{
  let bad = 0;
  for (const page of MANIFEST.pages) {
    const { document, errors } = load(page);
    const title = document.title.trim();
    const canonical = document.querySelector('link[rel="canonical"]');
    if (errors.length || !title || !canonical) {
      bad += 1;
      console.log(`  FAIL ${page}: ошибок ${errors.length}, title=${!!title}, canonical=${!!canonical}`);
    }
  }
  check(bad === 0, `${MANIFEST.pages.length} страниц без ошибок JS, с title и canonical`);
}

if (failures) {
  console.log(`\nПРОВАЛЕНО ПРОВЕРОК: ${failures}`);
  process.exit(1);
}
console.log("\nВсе DOM-проверки пройдены.");
