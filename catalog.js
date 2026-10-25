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
  const savedPage = item.avito_item_page;
  const gallery = savedPage ? savedPage.gallery.filter(photo => photo.path).map(photo => ({
    path: photo.path, label: `Фото ${photo.position} отдельного объявления`,
    quality: photo.resolution === "large" ? "крупный JPEG" : "миниатюра"
  })) : [];
  // Keep the earlier profile-only previews too: they can contain photos not in
  // the separate page's saved gallery. The two archives remain distinguishable.
  const pictures = [...gallery, ...item.photos.map((path, i) => ({
    path, label: `Превью ${i + 1} из страницы профиля`, quality: "208×208"
  }))];
  const imageWrap = el("div", "card-image-wrap");
  const image = el("img", "card-image");
  const sourceLabel = el("span", "card-source");
  image.loading = "lazy";
  image.width = 720;
  image.height = 960;
  function show(photo) {
    image.src = photo.path;
    image.alt = `${photo.label}: ${item.title}`;
    sourceLabel.textContent = `${photo.label} · ${photo.quality}`;
  }
  show(pictures[0]);
  const count = savedPage ? `${gallery.length}/${savedPage.gallery_count} фото карточки · ${item.photos.length} профиля` : `${item.photos.length} фото из профиля`;
  imageWrap.append(image, el("span", "card-category", item.category), el("span", "card-count", count), sourceLabel);
  article.append(imageWrap);
  const thumbs = el("div", "thumbs");
  pictures.forEach((photo, index) => {
    const button = el("button", index === 0 ? "thumb active" : "thumb");
    button.type = "button";
    button.setAttribute("aria-label", `${photo.label}: ${item.title}`);
    button.title = photo.label;
    const thumb = el("img");
    thumb.src = photo.path;
    thumb.alt = "";
    thumb.loading = "lazy";
    button.append(thumb);
    button.addEventListener("click", () => {
      show(photo);
      thumbs.querySelectorAll("button").forEach(x => x.classList.remove("active"));
      button.classList.add("active");
    });
    thumbs.append(button);
  });
  article.append(thumbs);
  // Manufacturer photography is kept separate from the archived seller photos.
  const manufacturer = el("div", "manufacturer-media");
  if (item.official.photos.length) {
    const label = el("span", "manufacturer-label", "ФОТО ПРОИЗВОДИТЕЛЯ · ПРИМЕР ЛИНЕЙКИ");
    const officialImage = el("img", "manufacturer-image");
    officialImage.src = item.official.photos[0];
    officialImage.alt = `Официальное иллюстративное фото: ${item.official.name}. ${item.official.photo_note_ru}`;
    officialImage.loading = "lazy";
    manufacturer.append(label, officialImage, el("p", "manufacturer-note", item.official.photo_note_ru));
  } else {
    manufacturer.append(el("p", "manufacturer-note", item.official.image_unavailable_note_ru));
  }
  article.append(manufacturer);
  const info = el("div", "card-info");
  info.append(el("span", "card-brand", item.official.brand), el("h3", "", item.title));
  const prices = el("div", "card-price");
  prices.append(el("b", "", `${rub.format(item.price_rub_snapshot)} ₽`));
  if (item.old_price_text_snapshot) prices.append(el("del", "", item.old_price_text_snapshot));
  if (item.discount_text_snapshot) prices.append(el("span", "card-discount", item.discount_text_snapshot));
  info.append(prices, el("p", "card-location", `${item.location_snapshot} · цена из архива`));
  const sellerDetails = el("details", "seller-details");
  sellerDetails.append(el("summary", "", savedPage ? "Текст и параметры объявления (архив) ↗" : "Фрагмент объявления (архив профиля) ↗"));
  if (savedPage) {
    sellerDetails.append(el("p", "source-date", `Сохранённая HTML-карточка · видимая дата: ${savedPage.date_display_snapshot || "не указана"} · просмотры: ${savedPage.total_views_display_snapshot || "не указаны"}. Наличие и цена сегодня неизвестны.`));
    sellerDetails.append(el("h4", "detail-heading", "Описание продавца"), el("p", "seller-description", savedPage.description_ru_as_seller_claim));
    const attributes = Object.entries(savedPage.attributes_as_seller_claim);
    if (attributes.length) {
      sellerDetails.append(el("h4", "detail-heading", "Характеристики из HTML"));
      const list = el("ul", "detail-list");
      attributes.forEach(([key, value]) => list.append(el("li", "", `${key}: ${value}`)));
      sellerDetails.append(list);
    }
    if (savedPage.gallery_missing_count) sellerDetails.append(el("p", "caution", `${savedPage.gallery_missing_count} фото есть только по внешней ссылке: файла в ZIP нет.`));
    if (savedPage.stock_badge_display_snapshot) sellerDetails.append(el("p", "source-date", `Указатель наличия в сохранённой HTML-странице: «${savedPage.stock_badge_display_snapshot}». Не является live-остатком.`));
  } else {
    sellerDetails.append(el("p", "caution", "В трёх новых ZIP нет отдельной HTML-карточки этого товара. Доступен только старый снимок профиля."));
    sellerDetails.append(el("p", "seller-description", item.avito_profile_excerpt.text + (item.avito_profile_excerpt.truncated ? "…" : "")));
  }
  info.append(sellerDetails);
  const details = el("details");
  details.append(el("summary", "", "Данные производителя: характеристики и состав ↗"));
  const facts = item.official.details;
  details.append(el("p", "", `${item.official.name}. ${item.official.summary_ru}`));
  function section(title, entries) {
    if (!entries || !entries.length) return;
    details.append(el("h4", "detail-heading", title));
    const list = el("ul", "detail-list");
    entries.forEach(text => list.append(el("li", "", text)));
    details.append(list);
  }
  section("Свойства и параметры линейки", facts.specifications_ru);
  section("Состав / компоненты", facts.ingredients_ru);
  if (facts.use_ru) details.append(el("h4", "detail-heading", "Применение"), el("p", "", facts.use_ru));
  if (facts.claims_ru) details.append(el("p", "manufacturer-claim", `По данным производителя: ${facts.claims_ru}`));
  details.append(el("p", "caution", `Важно: ${item.official.verification_note_ru}`));
  details.append(el("p", "source-date", `Источник: официальная страница бренда, проверена ${facts.checked_at}. Актуальные сведения — по ссылке ниже.`));
  if (facts.inci_local_path) {
    const inci = el("a", "inci-link", "Списки INCI с сайтов производителей ↗");
    inci.href = facts.inci_local_path;
    details.append(inci);
  }
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
    `${item.title} ${item.official.name} ${item.official.brand} ${item.official.details.specifications_ru.join(" ")} ${item.official.details.ingredients_ru.join(" ")} ${item.avito_item_page?.description_ru_as_seller_claim || item.avito_profile_excerpt?.text || ""}`.toLocaleLowerCase("ru").includes(q));
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
