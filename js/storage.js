/* =========================================================================
   STORAGE.JS  —  Capa de almacenamiento compartida
   -------------------------------------------------------------------------
   Guarda el CONTENIDO (textos, fechas, frases) en localStorage y los
   ARCHIVOS PESADOS (fotos, música, vídeos) en IndexedDB como data-URLs.

   Así el panel de admin puede subir archivos sin necesidad de servidor,
   y la web funciona abriéndola directamente en el navegador (file://).

   Referencia de archivos:
     - "idb:ID"          -> archivo guardado en IndexedDB (subido desde admin)
     - "assets/..."      -> ruta a un archivo local
     - "http(s)://..."   -> URL de internet
     - ""                -> sin archivo (placeholder)
   ========================================================================= */

const Store = (() => {
  const LS_KEY = "nuestra_historia_data_v1";
  const DB_NAME = "nuestra_historia_files";
  const DB_STORE = "files";
  let _dbPromise = null;

  // Contenido publicado (cargado desde content.json en el sitio web).
  // Permite que CUALQUIER visitante vea tus fotos y textos, no solo tu navegador.
  let _published = null;

  /* ---------------- IndexedDB (archivos) ---------------- */

  function openDB() {
    if (_dbPromise) return _dbPromise;
    _dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(DB_STORE)) {
          db.createObjectStore(DB_STORE);
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    return _dbPromise;
  }

  async function putFile(id, dataUrl) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(DB_STORE, "readwrite");
      tx.objectStore(DB_STORE).put(dataUrl, id);
      tx.oncomplete = () => resolve(id);
      tx.onerror = () => reject(tx.error);
    });
  }

  async function getFile(id) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(DB_STORE, "readonly");
      const req = tx.objectStore(DB_STORE).get(id);
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => reject(req.error);
    });
  }

  async function deleteFile(id) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(DB_STORE, "readwrite");
      tx.objectStore(DB_STORE).delete(id);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async function allFiles() {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(DB_STORE, "readonly");
      const store = tx.objectStore(DB_STORE);
      const out = {};
      const req = store.openCursor();
      req.onsuccess = () => {
        const cur = req.result;
        if (cur) { out[cur.key] = cur.value; cur.continue(); }
        else resolve(out);
      };
      req.onerror = () => reject(req.error);
    });
  }

  /* ---------------- Resolución de referencias de archivo ---------------- */

  // Convierte una referencia ("idb:xxx", ruta o URL) en algo usable por <img>/<audio>.
  async function resolveSrc(ref) {
    if (!ref) return "";
    if (typeof ref === "string" && ref.startsWith("idb:")) {
      const id = ref.slice(4);
      // 1º: contenido publicado (content.json) para los visitantes de la web.
      if (_published && _published.files && _published.files[id]) {
        return _published.files[id];
      }
      // 2º: archivo subido en este navegador (IndexedDB).
      const data = await getFile(id);
      return data || "";
    }
    return ref; // ruta o URL directa
  }

  /* ---------------- Carga del contenido publicado ---------------- */

  // Llamar UNA vez al iniciar la web. Si no hay ediciones locales, intenta
  // cargar "content.json" (generado desde el panel con el botón "Publicar").
  async function bootstrap() {
    try {
      if (localStorage.getItem(LS_KEY)) return; // este navegador tiene ediciones propias
    } catch (e) { /* localStorage no disponible */ }
    try {
      const res = await fetch("content.json", { cache: "no-store" });
      if (res && res.ok) {
        const bundle = await res.json();
        if (bundle && bundle.data) _published = bundle;
      }
    } catch (e) {
      // Sin content.json (o abierto como archivo local): se usarán los valores de data.js
    }
  }

  /* ---------------- Datos (textos/estructura) ---------------- */

  function _clone(obj) { return JSON.parse(JSON.stringify(obj)); }

  // Devuelve los datos guardados o, si no hay, los valores por defecto.
  function getData() {
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (raw) return JSON.parse(raw);
    } catch (e) { console.warn("No se pudieron leer los datos:", e); }
    if (_published && _published.data) return _clone(_published.data);
    return _clone(window.DEFAULT_DATA || {});
  }

  function saveData(data) {
    localStorage.setItem(LS_KEY, JSON.stringify(data));
    return data;
  }

  function resetData() {
    localStorage.removeItem(LS_KEY);
    return _clone(window.DEFAULT_DATA || {});
  }

  /* ---------------- Utilidades de subida ---------------- */

  // Lee un File del input y devuelve un data-URL.
  function fileToDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
  }

  // Genera un ID único sin depender de Date/Math (por si acaso).
  let _counter = 0;
  function uid(prefix = "f") {
    _counter += 1;
    const rnd = (typeof crypto !== "undefined" && crypto.getRandomValues)
      ? crypto.getRandomValues(new Uint32Array(1))[0].toString(36)
      : (performance.now().toString(36).replace(".", ""));
    return `${prefix}_${rnd}_${_counter}`;
  }

  // Sube un File a IndexedDB y devuelve su referencia "idb:ID".
  async function uploadFile(file) {
    const dataUrl = await fileToDataUrl(file);
    const id = uid();
    await putFile(id, dataUrl);
    return "idb:" + id;
  }

  /* ---------------- Exportar / Importar (copia de seguridad) ---------------- */

  async function exportAll() {
    const data = getData();
    const files = await allFiles();
    return { version: 1, data, files };
  }

  async function importAll(bundle) {
    if (!bundle || typeof bundle !== "object") throw new Error("Archivo inválido");
    if (bundle.data) saveData(bundle.data);
    if (bundle.files) {
      for (const [id, val] of Object.entries(bundle.files)) {
        await putFile(id, val);
      }
    }
    return true;
  }

  return {
    // arranque
    bootstrap,
    // datos
    getData, saveData, resetData,
    // archivos
    uploadFile, putFile, getFile, deleteFile, allFiles, resolveSrc,
    fileToDataUrl, uid,
    // backup
    exportAll, importAll,
  };
})();

if (typeof window !== "undefined") window.Store = Store;
