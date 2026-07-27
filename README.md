# 💖 Nuestra Historia — Web romántica

Una experiencia web interactiva, elegante y llena de amor. Hecha solo con **HTML, CSS y JavaScript** (sin frameworks). Funciona abriéndola directamente en cualquier navegador.

---

## 🚀 Cómo abrirla

1. Abre **`index.html`** con doble clic (o arrástralo a tu navegador).
2. ¡Listo! Pulsa **“Abrir nuestra historia”** y disfruta.

> Recomendado: Chrome, Edge o Firefox actualizados.

---

## ✨ Cómo personalizarla (lo más fácil)

Abre **`admin.html`** — es tu **panel de edición**. Desde ahí puedes, sin tocar código:

- 🖼️ **Subir fotos** (arrastrando o pulsando) para la galería, la historia y los recuerdos.
- 🎵 **Subir la música** de fondo (un archivo MP3).
- ✍️ Editar **todos los textos**: bienvenida, cartas, razones, frases del cielo, mensaje final…
- 📅 Cambiar la **fecha de inicio** del contador.
- ➕ Añadir o quitar momentos, cartas, razones y recuerdos.

Cuando termines, pulsa **💾 Guardar**. Luego abre `index.html` para ver el resultado.

### 🔐 ¿Dónde se guardan mis cambios?
En **tu propio navegador** (localStorage + IndexedDB). Por eso:

- Los cambios se ven en el **mismo navegador y ordenador**.
- Para llevar la web a otro dispositivo (o para no perder nada), usa
  **⬇ Copia de seguridad** en el panel: descarga un archivo `.json` con
  **todos los textos y fotos**. En el otro dispositivo, abre el panel y pulsa
  **⬆ Importar** para restaurarlo todo.

---

## 📝 Personalizar editando archivos (opcional)

Si prefieres tocar el código, casi todo el contenido por defecto está en:

- **`js/data.js`** → textos, fechas, frases y razones. Muy fácil de editar.

Para las fotos por archivo (en vez de subirlas por el panel), puedes poner rutas:

```js
photo: "assets/photos/nuestra-foto.jpg"
```

y colocar la imagen dentro de `assets/photos/`.

> Si editas `data.js` a mano y ya habías guardado cosas en el panel, entra en
> el panel y pulsa **↺ Restablecer** para cargar los nuevos valores por defecto.

---

## 📂 Estructura del proyecto

```
├── index.html          → La web principal
├── admin.html          → Panel de edición (subir fotos, música y textos)
├── css/
│   ├── styles.css      → Diseño de la web
│   └── admin.css       → Diseño del panel
├── js/
│   ├── data.js         → CONTENIDO por defecto (edítalo aquí)
│   ├── storage.js      → Guardado (localStorage + IndexedDB)
│   ├── effects.js      → Partículas y corazones de fondo
│   ├── main.js         → Lógica de la web
│   └── admin.js        → Lógica del panel
├── assets/
│   ├── photos/         → (opcional) tus fotos por archivo
│   └── music/          → (opcional) tu música por archivo
└── README.md
```

---

## 💌 Secciones incluidas

❤️ Nuestra Historia (línea del tiempo) · 📸 Galería con visor · 💌 Cartas tipo sobre ·
🌹 Razones · ✨ Recuerdos (scrapbook) · ⏳ Contador en tiempo real ·
🎁 Caja sorpresa · 💖 100 razones aleatorias · 🌌 Cielo estrellado · 💬 Mensaje final con lluvia de corazones.

---

Hecho con ❤️. **¡Feliz Día de las Novias!**
