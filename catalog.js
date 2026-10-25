"use strict";

const allowedHosts = new Set([
  "www.avito.ru", "www.hourglasscosmetics.com", "www.charlottetilbury.com",
  "speckproducts.com", "imageskincare.com", "www.swatch.com"
]);
const grid = document.querySelector("#product-grid");
const filters = document.querySelector("#filters");
const search = document.querySelector("#search");
const resultLine = document.querySelector("#result-line");
let items = [];
let selectedCategory = "Все";
const rub = new Intl.NumberFormat("ru-RU");

function safeLink(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && allowedHosts.has(parsed.hostname) ? url : "#";
  } catch { return "#"; }
}
function el(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined && content !== null) node.textContent = content;
  return node;
}
function externalLink(label, href, className) {
  const a = el("a", className, label);
  a.href = safeLink(href);
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}
function card(item) {
  const article = el("article", "card");
  const imageWrap = el("div", "card-image-wrap");
  const image = el("img", "card-image");
  image.src = item.photos[0];
  image.alt = `Фото из объявления: ${item.title}`;
  image.loading = "lazy";
  image.width = 208;
  image.height = 208;
  imageWrap.append(image, el("span", "card-category", item.category), el("span", "card-count", `${item.photos.length} фото из архива`));
  article.append(imageWrap);
  const thumbs = el("div", "thumbs");
  if (item.photos.length > 1) {
    item.photos.forEach((photo, index) => {
      const button = el("button", index === 0 ? "thumb active" : "thumb");
      button.type = "button";
      button.setAttribute("aria-label", `Фото ${index + 1} из ${item.photos.length}: ${item.title}`);
      const thumb = el("img");
      thumb.src = photo;
      thumb.alt = "";
      thumb.loading = "lazy";
      button.append(thumb);
      button.addEventListener("click", () => {
        image.src = photo;
        thumbs.querySelectorAll("button").forEach(x => x.classList.remove("active"));
        button.classList.add("active");
      });
      thumbs.append(button);
    });
  }
  article.append(thumbs);
  const info = el("div", "card-info");
  info.append(el("span", "card-brand", item.official.brand), el("h3", "", item.title));
  const prices = el("div", "card-price");
  prices.append(el("b", "", `${rub.format(item.price_rub_snapshot)} ₽`));
  if (item.old_price_text_snapshot) prices.append(el("del", "", item.old_price_text_snapshot));
  if (item.discount_text_snapshot) prices.append(el("span", "card-discount", item.discount_text_snapshot));
  info.append(prices, el("p", "card-location", `${item.location_snapshot} · цена из архива`));
  const details = el("details");
  details.append(el("summary", "", "О товаре и соответствии ↗"));
  details.append(el("p", "", `${item.official.name}. ${item.official.summary_ru}`));
  details.append(el("p", "caution", `Важно: ${item.official.verification_note_ru}`));
  info.append(details);
  const actions = el("div", "card-actions");
  actions.append(externalLink("На Авито ↗", item.avito_url, "avito"));
  actions.append(externalLink("Сайт бренда ↗", item.official.url));
  info.append(actions);
  article.append(info);
  return article;
}
function render() {
  const q = search.value.trim().toLocaleLowerCase("ru");
  const visible = items.filter(item => (selectedCategory === "Все" || item.category === selectedCategory) &&
    `${item.title} ${item.official.name} ${item.official.brand}`.toLocaleLowerCase("ru").includes(q));
  grid.replaceChildren(...visible.map(card));
  resultLine.textContent = `Показано ${visible.length} из ${items.length} товаров`;
  document.querySelector("#empty").hidden = visible.length !== 0;
}
function buildFilters() {
  ["Все", ...new Set(items.map(i => i.category))].forEach(category => {
    const button = el("button", category === selectedCategory ? "active" : "", category);
    button.type = "button";
    button.setAttribute("aria-pressed", String(category === selectedCategory));
    button.addEventListener("click", () => {
      selectedCategory = category;
      filters.querySelectorAll("button").forEach(b => {
        b.classList.toggle("active", b === button);
        b.setAttribute("aria-pressed", String(b === button));
      });
      render();
    });
    filters.append(button);
  });
}
search.addEventListener("input", render);
fetch("catalog.json").then(response => {
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}).then(data => {
  items = data.products;
  document.querySelector("#total-count").textContent = items.length;
  buildFilters();
  render();
}).catch(() => {
  resultLine.textContent = "Не удалось загрузить каталог. Проверьте соединение или откройте сайт через веб-сервер.";
});
