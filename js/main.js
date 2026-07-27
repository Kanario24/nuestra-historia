/* =========================================================================
   MAIN.JS  —  Lógica de la web
   Lee el contenido desde Store (admin) o desde data.js (por defecto)
   y construye todas las secciones con sus animaciones.
   ========================================================================= */

(async function () {
  "use strict";

  const $  = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));

  // Carga el contenido publicado (content.json) si existe y no hay ediciones locales.
  await Store.bootstrap();

  // Datos actuales (ediciones locales > content.json publicado > valores por defecto)
  const data = Store.getData();

  // Escapa texto para evitar problemas al inyectar en HTML
  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  // Crea un elemento <img> que resuelve referencias "idb:" desde IndexedDB
  async function makeImg(ref, alt = "", className = "") {
    const src = await Store.resolveSrc(ref);
    if (!src) return null;
    const img = document.createElement("img");
    img.src = src;
    img.alt = alt;
    img.loading = "lazy";
    if (className) img.className = className;
    return img;
  }

  /* ================= AJUSTES / TEXTOS ================= */
  function applySettings() {
    const s = data.settings || {};
    if (s.welcomeText)   $("#welcome-title").textContent = s.welcomeText;
    if (s.welcomeButton) $("#welcome-btn-text").textContent = s.welcomeButton;
    $("#final-text").textContent = data.finalMessage || "";
    if (s.musicTitle) $("#song-title").textContent = s.musicTitle;
  }

  /* ================= ❤️ TIMELINE ================= */
  async function buildTimeline() {
    const wrap = $("#timeline");
    wrap.innerHTML = "";
    for (const item of (data.timeline || [])) {
      const el = document.createElement("div");
      el.className = "tl-item reveal";
      const img = await makeImg(item.photo, item.title);
      el.innerHTML = `
        <span class="tl-dot"></span>
        <div class="tl-card">
          <div class="tl-photo ${img ? "" : "empty"}">${img ? "" : "❤️"}</div>
          <div class="tl-body">
            <div class="tl-date">${esc(item.date)}</div>
            <h3 class="tl-title">${esc(item.title)}</h3>
            <p class="tl-desc">${esc(item.description)}</p>
          </div>
        </div>`;
      if (img) $(".tl-photo", el).appendChild(img);
      wrap.appendChild(el);
    }
  }

  /* ================= 📸 GALERÍA + LIGHTBOX ================= */
  let galleryItems = []; // { src, caption }
  async function buildGallery() {
    const wrap = $("#gallery");
    wrap.innerHTML = "";
    galleryItems = [];
    const list = data.gallery || [];
    if (!list.length) {
      wrap.innerHTML = `<p class="gallery-empty">Aún no hay fotos aquí. ¡Añádelas desde el panel de edición! 📸</p>`;
      return;
    }
    for (const g of list) {
      const src = await Store.resolveSrc(g.photo);
      if (!src) continue;
      const idx = galleryItems.length;
      galleryItems.push({ src, caption: g.caption || "" });
      const item = document.createElement("div");
      item.className = "gallery-item";
      item.innerHTML = `<img src="${src}" alt="${esc(g.caption)}" loading="lazy" />
        ${g.caption ? `<div class="cap">${esc(g.caption)}</div>` : ""}`;
      item.addEventListener("click", () => openLightbox(idx));
      wrap.appendChild(item);
    }
  }

  const lb = $("#lightbox");
  let lbIndex = 0;
  function openLightbox(i) {
    lbIndex = i;
    const it = galleryItems[i];
    if (!it) return;
    $("#lb-img").src = it.src;
    $("#lb-cap").textContent = it.caption;
    lb.classList.add("open");
  }
  function closeLightbox() { lb.classList.remove("open"); }
  function lbStep(dir) {
    lbIndex = (lbIndex + dir + galleryItems.length) % galleryItems.length;
    openLightbox(lbIndex);
  }
  $("#lb-close").addEventListener("click", closeLightbox);
  $("#lb-prev").addEventListener("click", () => lbStep(-1));
  $("#lb-next").addEventListener("click", () => lbStep(1));
  lb.addEventListener("click", (e) => { if (e.target === lb) closeLightbox(); });
  document.addEventListener("keydown", (e) => {
    if (!lb.classList.contains("open")) return;
    if (e.key === "Escape") closeLightbox();
    if (e.key === "ArrowLeft") lbStep(-1);
    if (e.key === "ArrowRight") lbStep(1);
  });

  /* ================= 💌 CARTAS ================= */
  function buildLetters() {
    const wrap = $("#letters");
    wrap.innerHTML = "";
    (data.letters || []).forEach((letter) => {
      const el = document.createElement("div");
      el.className = "envelope reveal";
      el.innerHTML = `
        <div class="env-body">
          <div class="env-label">${esc(letter.title || "Para ti")}</div>
        </div>
        <div class="env-flap"></div>
        <div class="env-heart">❤️</div>
        <div class="env-hint">Pulsa para abrir 💌</div>`;
      el.addEventListener("click", () => {
        el.classList.add("open");
        setTimeout(() => openLetter(letter), 380);
      });
      wrap.appendChild(el);
    });
  }
  const letterModal = $("#letter-modal");
  function openLetter(letter) {
    $("#letter-title").textContent = letter.title || "Para ti";
    $("#letter-text").textContent = letter.message || "";
    letterModal.classList.add("open");
  }
  function closeLetter() {
    letterModal.classList.remove("open");
    // reinicia los sobres para que se puedan volver a abrir
    setTimeout(() => $$(".envelope").forEach((e) => e.classList.remove("open")), 300);
  }
  $("#letter-close").addEventListener("click", closeLetter);
  letterModal.addEventListener("click", (e) => { if (e.target === letterModal) closeLetter(); });

  /* ================= 🌹 RAZONES ================= */
  function buildReasons() {
    const wrap = $("#reasons");
    wrap.innerHTML = "";
    const icons = ["❤️", "💖", "💕", "🌹", "✨", "💘", "😍", "🥰", "💝", "💗"];
    (data.reasons || []).forEach((r, i) => {
      const el = document.createElement("div");
      el.className = "reason-card reveal";
      el.innerHTML = `<div class="ic">${icons[i % icons.length]}</div><p>${esc(r)}</p>`;
      wrap.appendChild(el);
    });
  }

  /* ================= ✨ SCRAPBOOK ================= */
  async function buildScrapbook() {
    const wrap = $("#scrapbook");
    wrap.innerHTML = "";
    const stickers = ["💕", "🌸", "⭐", "🦋", "🌷", "💫"];
    let i = 0;
    for (const item of (data.scrapbook || [])) {
      const el = document.createElement("div");
      el.className = "scrap-item reveal";
      const img = await makeImg(item.photo, item.note);
      el.innerHTML = `
        <div class="scrap-sticker">${stickers[i % stickers.length]}</div>
        <div class="scrap-photo ${img ? "" : "empty"}">${img ? "" : "📷"}</div>
        <div class="scrap-note">${esc(item.note)}</div>`;
      if (img) $(".scrap-photo", el).appendChild(img);
      wrap.appendChild(el);
      i++;
    }
  }

  /* ================= ⏳ CONTADOR ================= */
  function startCounter() {
    const start = new Date(data.settings?.startDate || "2023-08-01T00:00:00");
    const dEl = $("#c-days"), hEl = $("#c-hours"), mEl = $("#c-min"), sEl = $("#c-sec");
    function tick() {
      const now = new Date();
      let diff = Math.max(0, now - start);
      const days = Math.floor(diff / 86400000); diff -= days * 86400000;
      const hours = Math.floor(diff / 3600000); diff -= hours * 3600000;
      const mins = Math.floor(diff / 60000); diff -= mins * 60000;
      const secs = Math.floor(diff / 1000);
      dEl.textContent = days.toLocaleString("es-ES");
      hEl.textContent = String(hours).padStart(2, "0");
      mEl.textContent = String(mins).padStart(2, "0");
      sEl.textContent = String(secs).padStart(2, "0");
    }
    tick();
    setInterval(tick, 1000);
  }

  /* ================= 🎁 CAJA SORPRESA ================= */
  function initGift() {
    const gift = $("#gift"), msg = $("#gift-message"), hint = $("#gift-hint");
    msg.textContent = data.surpriseMessage || "";
    gift.addEventListener("click", () => {
      if (gift.classList.contains("open")) return;
      gift.classList.add("open");
      hint.textContent = "";
      setTimeout(() => { msg.classList.add("show"); burstHearts(gift); }, 400);
    });
  }

  /* ================= 💖 100 RAZONES ================= */
  function initHundred() {
    const btn = $("#hundred-btn"), display = $("#hundred-display");
    const txt = $("#hundred-text"), num = $("#hundred-num"), prog = $("#hundred-progress");
    const all = (data.hundredReasons || []).slice();
    let pool = [];
    const seen = new Set();
    btn.addEventListener("click", () => {
      if (!all.length) return;
      if (!pool.length) pool = all.slice(); // rellena cuando se agotan
      const idx = Math.floor(Math.random() * pool.length);
      const reason = pool.splice(idx, 1)[0];
      const globalIdx = all.indexOf(reason);
      seen.add(reason);
      display.classList.remove("flip"); void display.offsetWidth; display.classList.add("flip");
      txt.textContent = reason;
      num.textContent = "#" + (globalIdx + 1);
      prog.textContent = `Has descubierto ${seen.size} de ${all.length} razones 💖`;
    });
  }

  /* ================= 🌌 CIELO ESTRELLADO ================= */
  function initSky() {
    const sky = $("#sky"), msgEl = $("#star-msg");
    const phrases = data.stars || [];
    const count = Math.max(phrases.length, 26);
    // posiciones "pseudo-aleatorias" estables usando una semilla simple
    for (let i = 0; i < count; i++) {
      const star = document.createElement("div");
      star.className = "star";
      const x = (Math.sin(i * 12.9898) * 43758.5453 % 1 + 1) % 1;
      const y = (Math.sin(i * 78.233) * 12543.123 % 1 + 1) % 1;
      star.style.left = (6 + x * 88) + "%";
      star.style.top = (14 + y * 72) + "%";
      star.style.animationDelay = (i % 10) * 0.25 + "s";
      const phrase = phrases.length ? phrases[i % phrases.length] : "Te amo ✨";
      star.addEventListener("click", () => {
        msgEl.textContent = phrase;
        msgEl.classList.add("show");
        star.style.transform = "scale(2)";
        setTimeout(() => (star.style.transform = ""), 400);
      });
      sky.appendChild(star);
    }
  }

  /* ================= LLUVIA / EXPLOSIÓN DE CORAZONES ================= */
  function heartRain(duration = 5000) {
    const layer = $("#heart-rain");
    const emojis = ["❤️", "💖", "💕", "💗", "🌹", "💘"];
    const interval = setInterval(() => {
      const h = document.createElement("div");
      h.className = "rain-heart";
      h.textContent = emojis[Math.floor(Math.random() * emojis.length)];
      h.style.left = Math.random() * 100 + "vw";
      h.style.fontSize = 16 + Math.random() * 26 + "px";
      h.style.animationDuration = 3 + Math.random() * 4 + "s";
      layer.appendChild(h);
      setTimeout(() => h.remove(), 7000);
    }, 140);
    setTimeout(() => clearInterval(interval), duration);
  }
  // pequeña explosión localizada (caja sorpresa)
  function burstHearts(originEl) {
    const rect = originEl.getBoundingClientRect();
    for (let i = 0; i < 14; i++) {
      const h = document.createElement("div");
      h.className = "rain-heart";
      h.textContent = "❤️";
      h.style.left = (rect.left + rect.width / 2) + "px";
      h.style.top = (rect.top) + "px";
      h.style.position = "fixed";
      h.style.fontSize = 14 + Math.random() * 18 + "px";
      h.style.animation = `fall ${1.5 + Math.random() * 1.5}s ease-in forwards`;
      $("#heart-rain").appendChild(h);
      setTimeout(() => h.remove(), 3200);
    }
  }

  /* ================= REPRODUCTOR DE MÚSICA ================= */
  async function initPlayer() {
    const audio = $("#audio"), btn = $("#play-btn"), player = $("#player");
    const src = await Store.resolveSrc(data.settings?.music);
    let ready = false;
    if (src) { audio.src = src; ready = true; }

    function setPlaying(p) {
      player.classList.toggle("paused", !p);
      btn.textContent = p ? "❚❚" : "▶";
    }
    btn.addEventListener("click", async () => {
      if (!ready) {
        $("#song-title").textContent = "Añade música desde el panel ♪";
        return;
      }
      if (audio.paused) {
        try { await audio.play(); setPlaying(true); }
        catch (e) { console.warn("No se pudo reproducir:", e); }
      } else { audio.pause(); setPlaying(false); }
    });
    audio.addEventListener("ended", () => setPlaying(false));
    // Intenta arrancar la música tras abrir la historia (si el navegador lo permite)
    window.__tryAutoplay = async () => {
      if (ready) { try { await audio.play(); setPlaying(true); } catch (e) {} }
    };
  }

  /* ================= REVEAL AL HACER SCROLL ================= */
  function initReveal() {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e, i) => {
        if (e.isIntersecting) {
          e.target.classList.add("in");
          io.unobserve(e.target);
        }
      });
    }, { threshold: 0.12 });
    $$(".reveal").forEach((el) => io.observe(el));

    // Observa el mensaje final para lanzar la lluvia de corazones
    const finalIO = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) { heartRain(6000); finalIO.disconnect(); }
      });
    }, { threshold: 0.5 });
    finalIO.observe($("#final"));
  }

  /* ================= NAVEGACIÓN ================= */
  function initNav() {
    const toggle = $("#nav-toggle"), links = $("#nav-links");
    toggle.addEventListener("click", () => links.classList.toggle("open"));
    $$("#nav-links a").forEach((a) => a.addEventListener("click", () => links.classList.remove("open")));
  }

  /* ================= PANTALLA DE BIENVENIDA ================= */
  function initWelcome() {
    const welcome = $("#welcome"), openBtn = $("#open-btn");
    openBtn.addEventListener("click", () => {
      welcome.classList.add("hidden");
      $("#topbar").classList.add("show");
      $("#player").classList.add("show");
      // intenta música + un pequeño saludo de corazones
      if (window.__tryAutoplay) window.__tryAutoplay();
      heartRain(2500);
      // reactiva las animaciones reveal que ya estén en pantalla
      setTimeout(() => window.dispatchEvent(new Event("scroll")), 200);
    });
  }

  /* ================= ARRANQUE ================= */
  applySettings();
  await buildTimeline();
  await buildGallery();
  buildLetters();
  buildReasons();
  await buildScrapbook();
  startCounter();
  initGift();
  initHundred();
  initSky();
  await initPlayer();
  initReveal();
  initNav();
  initWelcome();

  console.log("💖 Web cargada. ¡Feliz Día de las Novias!");
})();
