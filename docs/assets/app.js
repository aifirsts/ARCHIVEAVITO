/* Beauty Supply — storefront behaviour (no dependencies).
   Everything here is progressive enhancement: pages stay readable without JS. */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------------- image loading states ---------------- */

  function markLoaded(img) {
    img.classList.add("is-loaded");
    var holder = img.closest("[data-media]");
    if (holder) holder.classList.add("is-loaded");
  }

  function markError(img) {
    img.classList.add("is-error");
    var holder = img.closest("[data-media]");
    if (holder) holder.classList.add("is-error");
    var label = img.getAttribute("data-error-label") || "Фото недоступно";
    var box = document.createElement("div");
    box.className = "media-error";
    box.setAttribute("role", "img");
    box.setAttribute("aria-label", label);
    var inner = document.createElement("div");
    var title = document.createElement("strong");
    title.textContent = "Фото не загрузилось";
    inner.appendChild(title);
    inner.appendChild(document.createTextNode(label));
    box.appendChild(inner);
    if (img.parentNode) img.parentNode.replaceChild(box, img);
  }

  function watchImages(root) {
    var images = root.querySelectorAll("img[data-watch]");
    Array.prototype.forEach.call(images, function (img) {
      if (img.complete && img.naturalWidth > 0) {
        markLoaded(img);
        return;
      }
      img.addEventListener("load", function () {
        markLoaded(img);
      });
      img.addEventListener("error", function () {
        markError(img);
      });
    });
  }

  /* ---------------- gallery ---------------- */

  function initGallery(root) {
    var stage = root.querySelector("[data-gallery-stage]");
    var thumbs = Array.prototype.slice.call(root.querySelectorAll("[data-gallery-thumb]"));
    var counter = root.querySelector("[data-gallery-counter]");
    var caption = root.querySelector("[data-gallery-caption]");
    var badgenode = root.querySelector("[data-gallery-source]");
    var prev = root.querySelector("[data-gallery-prev]");
    var next = root.querySelector("[data-gallery-next]");
    var lightbox = document.getElementById("lightbox");
    if (!stage || !thumbs.length) return;

    var index = 0;
    var slides = thumbs.map(function (thumb) {
      return {
        src: thumb.getAttribute("data-src") || "",
        alt: thumb.getAttribute("data-alt") || "",
        caption: thumb.getAttribute("data-caption") || "",
        source: thumb.getAttribute("data-source") || "",
        sourceKind: thumb.getAttribute("data-source-kind") || "listing",
        missing: thumb.getAttribute("data-missing") === "1",
        missingText: thumb.getAttribute("data-missing-text") || "",
        evidenceHref: thumb.getAttribute("data-evidence-href") || "",
        evidenceLabel: thumb.getAttribute("data-evidence-label") || "",
        tall: thumb.getAttribute("data-tall") === "1",
        width: Number(thumb.getAttribute("data-w")) || 0,
        height: Number(thumb.getAttribute("data-h")) || 0
      };
    });

    function render(nextIndex, moveFocus) {
      index = (nextIndex + slides.length) % slides.length;
      var slide = slides[index];
      stage.classList.toggle("is-tall", !!slide.tall);
      while (stage.firstChild) stage.removeChild(stage.firstChild);

      if (slide.missing) {
        var empty = document.createElement("div");
        empty.className = "gallery__missing";
        empty.setAttribute("role", "img");
        empty.setAttribute("aria-label", "Позиция " + (index + 1) + ": фотографии нет в архиве");
        var emptyBox = document.createElement("div");
        var emptyTitle = document.createElement("strong");
        emptyTitle.textContent = "Позиция " + (index + 1) + " — фото нет";
        var emptyNote = document.createElement("span");
        emptyNote.textContent = slide.missingText || "";
        emptyBox.appendChild(emptyTitle);
        emptyBox.appendChild(emptyNote);
        empty.appendChild(emptyBox);
        stage.appendChild(empty);
      } else {
        var img = document.createElement("img");
        img.className = "gallery__frame";
        img.src = slide.src;
        img.alt = slide.alt;
        img.setAttribute("data-watch", "");
        img.setAttribute("data-media", "");
        img.setAttribute("data-error-label", "Кадр " + (index + 1) + " не загрузился. Откройте объявление на Avito.");
        img.decoding = "async";
        if (slide.width && slide.height) {
          img.width = slide.width;
          img.height = slide.height;
        }
        if (index > 0) img.loading = "lazy";
        stage.appendChild(img);
        watchImages(stage);
      }

      var controls = document.createElement("div");
      controls.className = "gallery__controls";
      var nav = document.createElement("div");
      nav.className = "gallery__nav";
      var prevButton = document.createElement("button");
      prevButton.type = "button";
      prevButton.className = "icon-button";
      prevButton.setAttribute("data-nav", "prev");
      prevButton.setAttribute("aria-label", "Предыдущий кадр");
      prevButton.textContent = "\u2190";
      var nextButton = document.createElement("button");
      nextButton.type = "button";
      nextButton.className = "icon-button";
      nextButton.setAttribute("data-nav", "next");
      nextButton.setAttribute("aria-label", "Следующий кадр");
      nextButton.textContent = "\u2192";
      nav.appendChild(prevButton);
      nav.appendChild(nextButton);
      var counterNode = document.createElement("span");
      counterNode.className = "gallery__counter";
      counterNode.setAttribute("data-gallery-counter", "");
      counterNode.textContent = (index + 1) + " / " + slides.length;
      controls.appendChild(nav);
      controls.appendChild(counterNode);
      stage.appendChild(controls);
      if (!slide.missing) {
        controls.querySelector('[data-nav="next"]').addEventListener("click", function () {
          render(index + 1);
        });
        controls.querySelector('[data-nav="prev"]').addEventListener("click", function () {
          render(index - 1);
        });
      }
      if (prev) prev.disabled = index === 0;
      if (next) next.disabled = index === slides.length - 1;

      if (counter) counter.textContent = (index + 1) + " / " + slides.length;
      if (caption) caption.textContent = slide.caption;
      if (badgenode) {
        badgenode.textContent = slide.source;
        badgenode.className = "source-badge source-badge--" + slide.sourceKind;
      }
      var meta = root.querySelector("[data-gallery-evidence]");
      if (meta) {
        while (meta.firstChild) meta.removeChild(meta.firstChild);
        if (slide.evidenceLabel) {
          if (slide.evidenceHref) {
            var evidenceLink = document.createElement("a");
            evidenceLink.href = slide.evidenceHref;
            evidenceLink.textContent = "Бейдж «" + (index + 1) + " из " + slides.length + "»";
            meta.appendChild(evidenceLink);
            meta.appendChild(document.createTextNode(" "));
          }
          meta.appendChild(document.createTextNode(slide.evidenceLabel));
          meta.hidden = false;
        } else {
          meta.hidden = true;
        }
      }
      thumbs.forEach(function (thumb, i) {
        thumb.setAttribute("aria-current", i === index ? "true" : "false");
      });
      if (moveFocus) {
        var active = thumbs[index];
        if (active) active.focus({ preventScroll: true });
      }
      root.setAttribute("data-current-index", String(index));
    }

    thumbs.forEach(function (thumb, i) {
      thumb.addEventListener("click", function () {
        render(i);
      });
    });

    if (prev) prev.addEventListener("click", function () { render(index - 1); });
    if (next) next.addEventListener("click", function () { render(index + 1); });

    // Gallery shortcuts work from anywhere on the product page except form
    // fields and the open lightbox, so keyboards can browse without tabbing.
    document.addEventListener("keydown", function (event) {
      var target = event.target;
      var tag = (target.tagName || "").toLowerCase();
      if (tag === "input" || tag === "select" || tag === "textarea" || target.isContentEditable) return;
      if (lightbox && lightbox.open) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "ArrowRight") {
        event.preventDefault();
        render(index + 1);
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        render(index - 1);
      } else if (event.key === "Home") {
        event.preventDefault();
        render(0);
      } else if (event.key === "End") {
        event.preventDefault();
        render(slides.length - 1);
      }
    });

    stage.addEventListener("click", function (event) {
      if (event.target.closest("[data-nav]")) return;
      var current = slides[index];
      if (!current || current.missing || !lightbox) return;
      openLightbox(current, index, slides.length);
    });

    function openLightbox(slide, position, total) {
      var image = lightbox.querySelector("[data-lightbox-image]");
      var text = lightbox.querySelector("[data-lightbox-caption]");
      image.src = slide.src;
      image.alt = slide.alt;
      text.textContent = slide.caption + " · " + slide.source + " · кадр " + (position + 1) + " из " + total;
      if (typeof lightbox.showModal === "function") {
        lightbox.showModal();
      } else {
        lightbox.setAttribute("open", "");
      }
      lightbox.querySelector("[data-lightbox-close]").focus();
    }

    render(0);
  }

  function initLightbox() {
    var lightbox = document.getElementById("lightbox");
    if (!lightbox) return;
    lightbox.addEventListener("click", function (event) {
      if (event.target === lightbox || event.target.closest("[data-lightbox-close]")) {
        if (typeof lightbox.close === "function" && lightbox.open) lightbox.close();
        else lightbox.removeAttribute("open");
      }
    });
    lightbox.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        if (typeof lightbox.close === "function" && lightbox.open) lightbox.close();
        else lightbox.removeAttribute("open");
      }
    });
  }

  /* ---------------- catalogue search & filters ---------------- */

  function initCatalogue() {
    var grid = document.getElementById("product-grid");
    if (!grid) return;
    var cards = Array.prototype.slice.call(grid.querySelectorAll("[data-card]"));
    var search = document.getElementById("catalogue-search");
    var chips = Array.prototype.slice.call(document.querySelectorAll("[data-filter-category]"));
    var tagChips = Array.prototype.slice.call(document.querySelectorAll("[data-filter-tag]"));
    var sortSelect = document.getElementById("catalogue-sort");
    var discountToggle = document.getElementById("filter-discount");
    var count = document.getElementById("result-count");
    var empty = document.getElementById("empty-state");
    var reset = document.getElementById("reset-filters");
    var state = { query: "", category: "all", tag: "", sort: "curated", discountOnly: false };
    var originalOrder = cards.slice();

    function normalise(value) {
      return (value || "").toLowerCase().replace(/ё/g, "е").trim();
    }

    function matches(card) {
      if (state.category !== "all" && card.getAttribute("data-category") !== state.category) return false;
      if (state.tag) {
        var tags = (card.getAttribute("data-tags") || "").split(" ");
        if (tags.indexOf(state.tag) === -1) return false;
      }
      if (state.discountOnly && card.getAttribute("data-discount") !== "1") return false;
      if (!state.query) return true;
      var haystack = normalise(card.getAttribute("data-search"));
      return state.query.split(/\s+/).every(function (token) {
        return haystack.indexOf(token) !== -1;
      });
    }

    function orderVisible(visible) {
      var list = visible.slice();
      if (state.sort === "price-asc") {
        list.sort(function (a, b) { return Number(a.dataset.price) - Number(b.dataset.price); });
      } else if (state.sort === "price-desc") {
        list.sort(function (a, b) { return Number(b.dataset.price) - Number(a.dataset.price); });
      } else if (state.sort === "title") {
        list.sort(function (a, b) { return a.dataset.title.localeCompare(b.dataset.title, "ru"); });
      } else {
        list.sort(function (a, b) { return originalOrder.indexOf(a) - originalOrder.indexOf(b); });
      }
      return list;
    }

    function update() {
      var visible = cards.filter(matches);
      // hide everything first, then re-append the visible cards in the chosen order
      cards.forEach(function (card) {
        card.closest("li").hidden = true;
      });
      orderVisible(visible).forEach(function (card) {
        var holder = card.closest("li");
        grid.appendChild(holder);
        holder.hidden = false;
      });
      if (count) {
        count.textContent = visible.length + " из " + cards.length;
      }
      if (empty) {
        empty.hidden = visible.length !== 0;
      }
      var params = new URLSearchParams();
      if (state.query) params.set("q", state.query);
      if (state.category !== "all") params.set("category", state.category);
      if (state.tag) params.set("tag", state.tag);
      if (state.sort !== "curated") params.set("sort", state.sort);
      if (state.discountOnly) params.set("discount", "1");
      var next = location.pathname + (params.toString() ? "?" + params.toString() : "") + location.hash;
      // file:// pages have a null origin: replaceState with a URL throws there,
      // and a broken search must never kill the catalogue. Shareable URLs only
      // work when the site is served over http(s) anyway.
      try {
        history.replaceState(null, "", next);
      } catch (error) {
        /* noop — filters still applied to the DOM above */
      }
    }

    if (search) {
      search.addEventListener("input", function () {
        state.query = normalise(search.value);
        update();
      });
      search.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
          search.value = "";
          state.query = "";
          update();
        }
      });
    }

    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        state.category = chip.getAttribute("data-filter-category");
        chips.forEach(function (other) {
          other.setAttribute("aria-pressed", other === chip ? "true" : "false");
        });
        update();
      });
    });

    tagChips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        var value = chip.getAttribute("data-filter-tag");
        state.tag = state.tag === value ? "" : value;
        tagChips.forEach(function (other) {
          other.setAttribute(
            "aria-pressed",
            other.getAttribute("data-filter-tag") === state.tag ? "true" : "false"
          );
        });
        update();
      });
    });

    if (sortSelect) {
      sortSelect.addEventListener("change", function () {
        state.sort = sortSelect.value;
        update();
      });
    }

    if (discountToggle) {
      discountToggle.addEventListener("change", function () {
        state.discountOnly = discountToggle.checked;
        update();
      });
    }

    if (reset) {
      reset.addEventListener("click", function () {
        state = { query: "", category: "all", tag: "", sort: "curated", discountOnly: false };
        if (search) search.value = "";
        if (sortSelect) sortSelect.value = "curated";
        if (discountToggle) discountToggle.checked = false;
        chips.forEach(function (chip) {
          chip.setAttribute("aria-pressed", chip.getAttribute("data-filter-category") === "all" ? "true" : "false");
        });
        tagChips.forEach(function (chip) {
          chip.setAttribute("aria-pressed", "false");
        });
        update();
        if (search) search.focus();
      });
    }

    // restore state from the query string (shareable links)
    var params = new URLSearchParams(location.search);
    if (params.get("q") && search) {
      search.value = params.get("q");
      state.query = normalise(params.get("q"));
    }
    var category = params.get("category");
    if (category) {
      state.category = category;
      chips.forEach(function (chip) {
        chip.setAttribute("aria-pressed", chip.getAttribute("data-filter-category") === category ? "true" : "false");
      });
    }
    var tag = params.get("tag");
    if (tag) {
      state.tag = tag;
      tagChips.forEach(function (chip) {
        chip.setAttribute("aria-pressed", chip.getAttribute("data-filter-tag") === tag ? "true" : "false");
      });
    }
    var sort = params.get("sort");
    if (sort && sortSelect) {
      state.sort = sort;
      sortSelect.value = sort;
    }
    if (params.get("discount") === "1" && discountToggle) {
      state.discountOnly = true;
      discountToggle.checked = true;
    }
    update();

    // "/" focuses the catalogue search, mirroring common shop shortcuts
    document.addEventListener("keydown", function (event) {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
      var tag = (event.target.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select" || event.target.isContentEditable) return;
      if (!search) return;
      event.preventDefault();
      search.focus();
      search.select();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    watchImages(document);
    initGallery(document.querySelector("[data-gallery]") || document.createElement("div"));
    initLightbox();
    initCatalogue();
    if (!reduceMotion) {
      document.documentElement.classList.add("has-motion");
    }
  });
})();
