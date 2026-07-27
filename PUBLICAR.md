# 🌐 Cómo publicar la web en GitHub + Vercel

> Ya está todo preparado: el proyecto es un repositorio Git con el primer commit hecho.

---

## ⭐ PASO 0 (¡MUY IMPORTANTE!) — Meter tu contenido antes de publicar

Tu web guarda las fotos/textos en tu navegador. Para que tu novia lo vea TODO al
abrir el enlace, hay que “congelar” tu contenido en un archivo:

1. Abre **`admin.html`**, sube tus fotos, música y textos y pulsa **💾 Guardar**.
2. Pulsa el botón **🌐 Publicar** → se descarga un archivo **`content.json`**.
3. Mueve ese `content.json` a la **carpeta del proyecto** (junto a `index.html`).

> Cada vez que cambies algo y quieras actualizar la web publicada, repite este
> paso y vuelve a subir el `content.json` (Paso 3).

---

## 1️⃣ Crear el repositorio en GitHub

1. Entra en 👉 https://github.com/new (inicia sesión).
2. **Repository name**: por ejemplo `nuestra-historia`.
3. Déjalo en **Public** (o Private, da igual para Vercel).
4. **NO** marques “Add a README” ni nada más (el proyecto ya lo tiene).
5. Pulsa **Create repository**.
6. Copia la URL que te aparece, será algo así:
   `https://github.com/TU-USUARIO/nuestra-historia.git`

---

## 2️⃣ Subir el proyecto a GitHub

Abre una terminal en la carpeta del proyecto y ejecuta (cambia la URL por la tuya):

```bash
git add .
git commit -m "Añadir contenido"        # solo si añadiste content.json
git remote add origin https://github.com/TU-USUARIO/nuestra-historia.git
git push -u origin main
```

> La primera vez, se abrirá una ventana del navegador para que inicies sesión en
> GitHub. Es normal y seguro (lo gestiona Git). Acepta y listo.

---

## 3️⃣ Publicar en Vercel

1. Entra en 👉 https://vercel.com e inicia sesión **con GitHub** (botón “Continue with GitHub”).
2. Pulsa **Add New… → Project**.
3. Busca tu repositorio `nuestra-historia` y pulsa **Import**.
4. No cambies nada (es un sitio estático). Pulsa **Deploy**.
5. En ~1 minuto tendrás tu enlace: `https://nuestra-historia.vercel.app` 💖

¡Ese es el enlace que le mandas a tu novia!

---

## 🔄 Actualizar la web más adelante

Cuando cambies fotos o textos:

1. Panel → **🌐 Publicar** → reemplaza el `content.json` de la carpeta.
2. En la terminal:
   ```bash
   git add .
   git commit -m "Actualizar contenido"
   git push
   ```
3. Vercel se actualiza solo en unos segundos. 🎉
