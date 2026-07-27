/* =========================================================================
   ADMIN.JS  —  Lógica del panel de edición
   Todo se guarda en el navegador (localStorage + IndexedDB) mediante Store.
   ========================================================================= */

(function () {
  "use strict";
  const $  = (s, c = document) => c.querySelector(s);
  const $$ = (s, c = document) => Array.from(c.querySelectorAll(s));

  // Estado en memoria (copia editable de los datos)
  let data = Store.getData();
  let dirty = false;

  /* ---------------- utilidades ---------------- */
  function markDirty() {
    dirty = true;
    $("#save-bar").classList.add("dirty");
    $("#save-status").textContent = "Cambios sin guardar";
  }
  function markClean() {
    dirty = false;
    $("#save-bar").classList.remove("dirty");
    $("#save-status").textContent = "Todo guardado";
  }
  let toastTimer;
  function toast(msg, type = "") {
    const t = $("#toast");
    t.textContent = msg;
    t.className = "toast show " + type;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (t.className = "toast"), 2600);
  }

  // Crea un cuadro de subida de imagen reutilizable.
  // onUpload(ref) se llama con la nueva referencia "idb:..." tras subir.
  function imageUploader(currentRef, onUpload, label = "Subir foto") {
    const box = document.createElement("label");
    box.className = "uploader";
    box.innerHTML = `
      <input type="file" accept="image/*" />
      <div class="up-icon">🖼️</div>
      <div class="up-text">${label}</div>`;
    const input = $("input", box);

    async function preview(ref) {
      const src = await Store.resolveSrc(ref);
      $("img", box)?.remove();
      if (src) {
        const img = document.createElement("img");
        img.src = src;
        box.appendChild(img);
        if (!$(".up-badge", box)) {
          const b = document.createElement("span");
          b.className = "up-badge"; b.textContent = "Cambiar";
          box.appendChild(b);
        }
      }
    }
    preview(currentRef);

    async function handle(file) {
      if (!file || !file.type.startsWith("image/")) { toast("Selecciona una imagen", "err"); return; }
      const ref = await Store.uploadFile(file);
      await preview(ref);
      onUpload(ref);
      markDirty();
    }
    input.addEventListener("change", (e) => handle(e.target.files[0]));
    // drag & drop
    box.addEventListener("dragover", (e) => { e.preventDefault(); box.classList.add("drag"); });
    box.addEventListener("dragleave", () => box.classList.remove("drag"));
    box.addEventListener("drop", (e) => {
      e.preventDefault(); box.classList.remove("drag");
      handle(e.dataTransfer.files[0]);
    });
    return box;
  }

  // Cabecera de item con eliminar / subir / bajar
  function itemHeader(index, title, handlers) {
    const head = document.createElement("div");
    head.className = "item-head";
    head.innerHTML = `<span class="num">${title} ${index + 1}</span>
      <div class="item-tools">
        <button class="icon-btn up" title="Subir">▲</button>
        <button class="icon-btn down" title="Bajar">▼</button>
        <button class="icon-btn del" title="Eliminar">🗑</button>
      </div>`;
    $(".up", head).addEventListener("click", handlers.up);
    $(".down", head).addEventListener("click", handlers.down);
    $(".del", head).addEventListener("click", handlers.del);
    return head;
  }

  function move(arr, i, dir) {
    const j = i + dir;
    if (j < 0 || j >= arr.length) return false;
    [arr[i], arr[j]] = [arr[j], arr[i]];
    return true;
  }

  /* =====================================================================
     GENERAL
     ===================================================================== */
  function bindGeneral() {
    const s = data.settings || (data.settings = {});
    $("#s-welcomeText").value   = s.welcomeText || "";
    $("#s-welcomeButton").value = s.welcomeButton || "";
    $("#s-musicTitle").value    = s.musicTitle || "";
    // datetime-local necesita formato AAAA-MM-DDTHH:MM
    if (s.startDate) {
      const d = new Date(s.startDate);
      if (!isNaN(d)) {
        const pad = (n) => String(n).padStart(2, "0");
        $("#s-startDate").value =
          `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
      }
    }
    const bindText = (id, key) => $(id).addEventListener("input", (e) => { s[key] = e.target.value; markDirty(); });
    bindText("#s-welcomeText", "welcomeText");
    bindText("#s-welcomeButton", "welcomeButton");
    bindText("#s-musicTitle", "musicTitle");
    $("#s-startDate").addEventListener("input", (e) => { s.startDate = e.target.value; markDirty(); });

    // Música
    const mu = $("#music-uploader"), mf = $("#music-file"), mn = $("#music-name");
    if (s.music) mn.textContent = "Música cargada ✓ (pulsa para cambiar)";
    async function handleMusic(file) {
      if (!file) return;
      if (!file.type.startsWith("audio/")) { toast("Selecciona un archivo de audio", "err"); return; }
      mn.textContent = "Subiendo…";
      s.music = await Store.uploadFile(file);
      mn.textContent = file.name + " ✓";
      markDirty();
      toast("Música lista 🎵", "ok");
    }
    mf.addEventListener("change", (e) => handleMusic(e.target.files[0]));
    mu.addEventListener("dragover", (e) => { e.preventDefault(); mu.classList.add("drag"); });
    mu.addEventListener("dragleave", () => mu.classList.remove("drag"));
    mu.addEventListener("drop", (e) => { e.preventDefault(); mu.classList.remove("drag"); handleMusic(e.dataTransfer.files[0]); });
  }

  /* =====================================================================
     TIMELINE
     ===================================================================== */
  function renderTimeline() {
    const list = $("#timeline-list");
    list.innerHTML = "";
    data.timeline = data.timeline || [];
    data.timeline.forEach((item, i) => {
      const card = document.createElement("div");
      card.className = "card";
      card.appendChild(itemHeader(i, "Momento", {
        up:   () => { if (move(data.timeline, i, -1)) { markDirty(); renderTimeline(); } },
        down: () => { if (move(data.timeline, i, +1)) { markDirty(); renderTimeline(); } },
        del:  () => { data.timeline.splice(i, 1); markDirty(); renderTimeline(); },
      }));
      const row = document.createElement("div");
      row.className = "card-row";
      const left = document.createElement("div");
      left.appendChild(imageUploader(item.photo, (ref) => item.photo = ref, "Foto del momento"));
      const right = document.createElement("div");
      right.innerHTML = `
        <div class="field"><label>Fecha</label><input type="text" class="f-date" placeholder="Ej: 1 de Agosto, 2023" /></div>
        <div class="field"><label>Título</label><input type="text" class="f-title" /></div>
        <div class="field"><label>Descripción</label><textarea class="f-desc"></textarea></div>`;
      $(".f-date", right).value = item.date || "";
      $(".f-title", right).value = item.title || "";
      $(".f-desc", right).value = item.description || "";
      $(".f-date", right).addEventListener("input", (e) => { item.date = e.target.value; markDirty(); });
      $(".f-title", right).addEventListener("input", (e) => { item.title = e.target.value; markDirty(); });
      $(".f-desc", right).addEventListener("input", (e) => { item.description = e.target.value; markDirty(); });
      row.append(left, right);
      card.appendChild(row);
      list.appendChild(card);
    });
  }
  $("#add-timeline").addEventListener("click", () => {
    data.timeline = data.timeline || [];
    data.timeline.push({ date: "", title: "Nuevo momento", description: "", photo: "" });
    markDirty(); renderTimeline();
  });

  /* =====================================================================
     GALERÍA
     ===================================================================== */
  function renderGallery() {
    const grid = $("#gallery-grid");
    grid.innerHTML = "";
    data.gallery = data.gallery || [];
    data.gallery.forEach((g, i) => {
      const cell = document.createElement("div");
      cell.className = "gal-cell";
      Store.resolveSrc(g.photo).then((src) => {
        cell.innerHTML = `
          <button class="del-x" title="Eliminar">✕</button>
          <img src="${src}" alt="" />
          <input class="cap-input" type="text" placeholder="Escribe un texto…" />`;
        $(".cap-input", cell).value = g.caption || "";
        $(".cap-input", cell).addEventListener("input", (e) => { g.caption = e.target.value; markDirty(); });
        $(".del-x", cell).addEventListener("click", () => { data.gallery.splice(i, 1); markDirty(); renderGallery(); });
      });
      grid.appendChild(cell);
    });
    // celda para añadir (permite varias a la vez)
    const add = document.createElement("label");
    add.className = "gal-add";
    add.innerHTML = `<input type="file" accept="image/*" multiple />
      <div><div style="font-size:1.8rem">＋</div><div>Añadir fotos</div></div>`;
    $("input", add).addEventListener("change", async (e) => {
      const files = Array.from(e.target.files || []);
      if (!files.length) return;
      toast("Subiendo " + files.length + " foto(s)…");
      for (const f of files) {
        if (!f.type.startsWith("image/")) continue;
        const ref = await Store.uploadFile(f);
        data.gallery.push({ photo: ref, caption: "" });
      }
      markDirty();
      renderGallery();
      toast("Fotos añadidas 📸", "ok");
    });
    grid.appendChild(add);
  }

  /* =====================================================================
     CARTAS
     ===================================================================== */
  function renderLetters() {
    const list = $("#letters-list");
    list.innerHTML = "";
    data.letters = data.letters || [];
    data.letters.forEach((l, i) => {
      const card = document.createElement("div");
      card.className = "card";
      card.appendChild(itemHeader(i, "Carta", {
        up:   () => { if (move(data.letters, i, -1)) { markDirty(); renderLetters(); } },
        down: () => { if (move(data.letters, i, +1)) { markDirty(); renderLetters(); } },
        del:  () => { data.letters.splice(i, 1); markDirty(); renderLetters(); },
      }));
      const body = document.createElement("div");
      body.innerHTML = `
        <div class="field"><label>Título del sobre</label><input type="text" class="l-title" /></div>
        <div class="field"><label>Mensaje</label><textarea class="l-msg" style="min-height:110px"></textarea></div>`;
      $(".l-title", body).value = l.title || "";
      $(".l-msg", body).value = l.message || "";
      $(".l-title", body).addEventListener("input", (e) => { l.title = e.target.value; markDirty(); });
      $(".l-msg", body).addEventListener("input", (e) => { l.message = e.target.value; markDirty(); });
      card.appendChild(body);
      list.appendChild(card);
    });
  }
  $("#add-letter").addEventListener("click", () => {
    data.letters = data.letters || [];
    data.letters.push({ title: "Nueva carta", message: "" });
    markDirty(); renderLetters();
  });

  /* =====================================================================
     RAZONES (chips)
     ===================================================================== */
  function renderReasons() {
    const wrap = $("#reasons-chips");
    wrap.innerHTML = "";
    data.reasons = data.reasons || [];
    data.reasons.forEach((r, i) => {
      const chip = document.createElement("div");
      chip.className = "chip";
      chip.innerHTML = `<input type="text" /><button class="x" title="Eliminar">✕</button>`;
      const input = $("input", chip);
      input.value = r;
      input.style.width = Math.max(60, r.length * 9) + "px";
      input.addEventListener("input", (e) => {
        data.reasons[i] = e.target.value;
        input.style.width = Math.max(60, e.target.value.length * 9) + "px";
        markDirty();
      });
      $(".x", chip).addEventListener("click", () => { data.reasons.splice(i, 1); markDirty(); renderReasons(); });
      wrap.appendChild(chip);
    });
  }
  $("#add-reason").addEventListener("click", () => {
    data.reasons = data.reasons || [];
    data.reasons.push("Nueva razón");
    markDirty(); renderReasons();
  });

  /* =====================================================================
     SCRAPBOOK
     ===================================================================== */
  function renderScrapbook() {
    const list = $("#scrapbook-list");
    list.innerHTML = "";
    data.scrapbook = data.scrapbook || [];
    data.scrapbook.forEach((item, i) => {
      const card = document.createElement("div");
      card.className = "card";
      card.appendChild(itemHeader(i, "Recuerdo", {
        up:   () => { if (move(data.scrapbook, i, -1)) { markDirty(); renderScrapbook(); } },
        down: () => { if (move(data.scrapbook, i, +1)) { markDirty(); renderScrapbook(); } },
        del:  () => { data.scrapbook.splice(i, 1); markDirty(); renderScrapbook(); },
      }));
      const row = document.createElement("div");
      row.className = "card-row";
      const left = document.createElement("div");
      left.appendChild(imageUploader(item.photo, (ref) => item.photo = ref, "Foto del recuerdo"));
      const right = document.createElement("div");
      right.innerHTML = `<div class="field"><label>Nota / recuerdo</label><textarea class="sc-note" style="min-height:110px"></textarea></div>`;
      $(".sc-note", right).value = item.note || "";
      $(".sc-note", right).addEventListener("input", (e) => { item.note = e.target.value; markDirty(); });
      row.append(left, right);
      card.appendChild(row);
      list.appendChild(card);
    });
  }
  $("#add-scrap").addEventListener("click", () => {
    data.scrapbook = data.scrapbook || [];
    data.scrapbook.push({ photo: "", note: "Nuevo recuerdo" });
    markDirty(); renderScrapbook();
  });

  /* =====================================================================
     100 RAZONES
     ===================================================================== */
  function renderHundred() {
    const list = $("#hundred-list");
    list.innerHTML = "";
    data.hundredReasons = data.hundredReasons || [];
    const card = document.createElement("div");
    card.className = "card";
    data.hundredReasons.forEach((r, i) => {
      const row = document.createElement("div");
      row.className = "chip";
      row.style.cssText = "width:100%; margin-bottom:8px; border-radius:12px;";
      row.innerHTML = `<span style="color:var(--gold); font-size:.8rem; font-weight:600">#${i + 1}</span>
        <input type="text" style="flex:1; width:auto" /><button class="x" title="Eliminar">✕</button>`;
      $("input", row).value = r;
      $("input", row).addEventListener("input", (e) => { data.hundredReasons[i] = e.target.value; markDirty(); });
      $(".x", row).addEventListener("click", () => { data.hundredReasons.splice(i, 1); markDirty(); renderHundred(); });
      card.appendChild(row);
    });
    const counter = document.createElement("div");
    counter.className = "hint";
    counter.textContent = `Tienes ${data.hundredReasons.length} razones (ideal: 100 💖)`;
    card.appendChild(counter);
    list.appendChild(card);
  }
  $("#add-hundred").addEventListener("click", () => {
    data.hundredReasons = data.hundredReasons || [];
    data.hundredReasons.push("");
    markDirty(); renderHundred();
    const inputs = $$("#hundred-list input");
    inputs[inputs.length - 1]?.focus();
  });

  /* =====================================================================
     ESTRELLAS
     ===================================================================== */
  function renderStars() {
    const list = $("#stars-list");
    list.innerHTML = "";
    data.stars = data.stars || [];
    const card = document.createElement("div");
    card.className = "card";
    data.stars.forEach((r, i) => {
      const row = document.createElement("div");
      row.className = "chip";
      row.style.cssText = "width:100%; margin-bottom:8px; border-radius:12px;";
      row.innerHTML = `<span style="font-size:.9rem">⭐</span>
        <input type="text" style="flex:1; width:auto" /><button class="x" title="Eliminar">✕</button>`;
      $("input", row).value = r;
      $("input", row).addEventListener("input", (e) => { data.stars[i] = e.target.value; markDirty(); });
      $(".x", row).addEventListener("click", () => { data.stars.splice(i, 1); markDirty(); renderStars(); });
      card.appendChild(row);
    });
    list.appendChild(card);
  }
  $("#add-star").addEventListener("click", () => {
    data.stars = data.stars || [];
    data.stars.push("");
    markDirty(); renderStars();
    const inputs = $$("#stars-list input");
    inputs[inputs.length - 1]?.focus();
  });

  /* =====================================================================
     SORPRESA / FINAL (textos simples)
     ===================================================================== */
  function bindTexts() {
    $("#s-surprise").value = data.surpriseMessage || "";
    $("#s-final").value = data.finalMessage || "";
    $("#s-surprise").addEventListener("input", (e) => { data.surpriseMessage = e.target.value; markDirty(); });
    $("#s-final").addEventListener("input", (e) => { data.finalMessage = e.target.value; markDirty(); });
  }

  /* =====================================================================
     GUARDAR / EXPORTAR / IMPORTAR / RESET
     ===================================================================== */
  function normalizeStartDate() {
    // datetime-local devuelve "AAAA-MM-DDTHH:MM"; lo guardamos tal cual (válido para new Date()).
    if (data.settings && data.settings.startDate && data.settings.startDate.length === 16) {
      data.settings.startDate += ":00";
    }
  }
  function save() {
    normalizeStartDate();
    Store.saveData(data);
    markClean();
    toast("Guardado ✓ Ya puedes ver la web", "ok");
  }
  $("#save-btn").addEventListener("click", save);

  // Guardado con Ctrl/Cmd + S
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); save(); }
  });

  // Aviso al salir con cambios sin guardar
  window.addEventListener("beforeunload", (e) => {
    if (dirty) { e.preventDefault(); e.returnValue = ""; }
  });

  // Exportar copia de seguridad (JSON con textos + archivos)
  $("#export-btn").addEventListener("click", async () => {
    if (dirty) save();
    const bundle = await Store.exportAll();
    const blob = new Blob([JSON.stringify(bundle)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "nuestra-historia-copia.json";
    a.click();
    URL.revokeObjectURL(url);
    toast("Copia de seguridad descargada ⬇", "ok");
  });

  // Publicar: genera "content.json" (textos + fotos) para subir a internet (Vercel/GitHub).
  $("#publish-btn").addEventListener("click", async () => {
    if (dirty) save();
    const bundle = await Store.exportAll();
    const blob = new Blob([JSON.stringify(bundle)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "content.json";
    a.click();
    URL.revokeObjectURL(url);
    toast("content.json descargado 🌐 Ponlo en la carpeta del proyecto", "ok");
  });

  // Importar copia de seguridad
  $("#import-input").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      const text = await file.text();
      const bundle = JSON.parse(text);
      await Store.importAll(bundle);
      data = Store.getData();
      renderAll();
      markClean();
      toast("Copia importada correctamente ✓", "ok");
    } catch (err) {
      console.error(err);
      toast("No se pudo importar el archivo", "err");
    }
    e.target.value = "";
  });

  // Restablecer a valores por defecto
  $("#reset-btn").addEventListener("click", () => {
    if (!confirm("¿Restablecer todo a los valores por defecto? Se perderán los textos guardados (las fotos subidas seguirán en la copia de seguridad).")) return;
    data = Store.resetData();
    renderAll();
    markClean();
    toast("Restablecido a valores por defecto");
  });

  /* =====================================================================
     PESTAÑAS
     ===================================================================== */
  $$(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      $$(".tab").forEach((t) => t.classList.remove("active"));
      $$(".panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      $(`.panel[data-panel="${tab.dataset.tab}"]`).classList.add("active");
    });
  });

  /* =====================================================================
     RENDER GLOBAL
     ===================================================================== */
  function renderAll() {
    bindGeneral();
    renderTimeline();
    renderGallery();
    renderLetters();
    renderReasons();
    renderScrapbook();
    renderHundred();
    renderStars();
    bindTexts();
  }

  renderAll();
  markClean();
  console.log("⚙️ Panel de edición listo.");
})();
