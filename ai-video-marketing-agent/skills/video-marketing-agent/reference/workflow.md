# Recetas y solución de problemas

`video-agent` = `${CLAUDE_SKILL_DIR}/scripts/video-agent` (ruta absoluta, un comando por llamada).

## Recetas

**«Hazme un vídeo de 30 segundos para TikTok» (sin material)**
→ `video-agent create "<petición>" --plan-only`; si no hay marca, pregunta solo el nombre.
Reescribe textos, `render`, revisa la hoja de contactos, entrega. Fondos generados localmente,
música sintética, logotipo tipográfico provisional: menciónalo.

**«Edita estos clips como un anuncio profesional»**
→ `video-agent edit clip1.mp4 clip2.mov logo.png --brief "Anuncio de <marca> para <objetivo>" --goal ad --platform ad_vertical`.
Si los clips tienen voz, el CLI conserva su audio y subtitula (transcripción real).

**«Crea un vídeo cinematográfico de un coche»**
→ `--style cinematic` (o `automotive` si es un anuncio de concesionario), clips del usuario con
`motion: pan_right`, transiciones `fadeblack`. Sin clips: avisa de que el resultado será
tipográfico con fondos generados y propón aportar material o activar Pexels.

**«Convierte este vídeo horizontal en tres Shorts»**
→ `video-agent shorts entrevista.mp4 -n 3 -d 30 --platform youtube_shorts --fit blur_fill`.
Selecciona los fragmentos con mejor señal (nitidez, movimiento, audio) sin solaparlos y corta
en los cambios de plano. `--fit cover` recorta al centro (mejor si el sujeto está centrado).
Revisa cada `short-0N/previews/qc_final/contact_sheet.jpg`.

**«Añade subtítulos dinámicos y música»**
→ `video-agent subtitle video.mp4 --style dynamic --music musica.mp3` (la música se atenúa bajo la voz).
Requiere faster-whisper; si falta, dilo y ofrece instalarlo (`pip install -e '.[transcribe]'`).

**«Analiza este vídeo y mejora su edición»**
→ `video-agent inspect video.mp4 --platform tiktok` y mira la hoja de contactos. Explica los problemas
(duración, sonoridad, negros, ritmo, encuadre, textos) y después `video-agent edit video.mp4 --brief "<objetivo>"`
para una versión mejorada. Compara ambos informes en la entrega.

**«Crea cinco versiones con diferentes ganchos»**
→ Si no existe el proyecto, créalo primero. Edita `hook_variants` en `project.json` con 5 ganchos
de ángulos distintos (pregunta, dato, dolor, curiosidad, contraste) y ejecuta `video-agent variants <proyecto> -n 5`.
Salen en `exports/variants/variant_0N.mp4`, cada una con su informe.

**«Haz un vídeo de gaming con cortes rápidos»**
→ `--style gaming` (planos de ~1,2 s, transiciones rápidas, subtítulos estilo gaming).

**«Crea una campaña de vídeo para conseguir clientes»**
→ `--goal leads`; produce el vídeo principal (p. ej. Reels 9:16) y luego variantes de gancho;
si piden varios formatos, crea un proyecto por plataforma (`--platform youtube` para 16:9,
`square` para 1:1) reutilizando el mismo material.

**«Haz un vídeo promocional de mi página web»**
→ `--goal traffic`. Si el usuario aporta capturas o grabaciones de pantalla, úsalas con
`fit: contain` o `blur_fill` para no recortar la interfaz. La URL detectada se muestra en el cierre.

## Voz en off

- Local: `espeak-ng` (gratis, sonido robótico): úsala para maquetas o si el usuario lo acepta.
- Natural: `tts.provider: openai` en `video-agent.yaml` + `OPENAI_API_KEY` +
  `permissions.allow_paid_apis: true` + `limits.max_estimated_cost_usd` > 0. **Pide permiso antes.**
- Locución grabada por el usuario: pásala con `-i voz.wav`; se transcribe para los subtítulos.

## Recursos externos

- Pexels (licencia Pexels) requiere `PEXELS_API_KEY` y `permissions.allow_network_asset_search: true`.
  Se registra autor, URL y licencia en `project.json → provenance`.
- No descargues material protegido ni elimines marcas de agua.

## Solución de problemas

| Síntoma | Causa / solución |
|---|---|
| `FFmpeg sin filtros: ass…` | Instala un FFmpeg completo (con libass, libfreetype, libx264) |
| Subtítulos no generados: modelo Whisper | Sin acceso a huggingface.co: descarga un modelo CTranslate2 y `VIDEO_AGENT_WHISPER_MODEL=/ruta` |
| Texto "no cabe en la zona segura" | Acorta el texto o baja `scale`; el CLI reduce un 15 % por intento |
| Locución no cabe en la escena | Acorta la frase o alarga `duration` de la escena |
| Negros inesperados | Clip oscuro o corrupto: el CLI lo sustituye por un fondo; mejor elige otro fragmento (`source.start`) |
| Render lento | Baja `export.fps` o la resolución para pruebas; la caché evita re-renderizar escenas sin cambios |
