# Esquema del plan de edición (`project.json` → `plan`)

El plan es la fuente de verdad: el editor lo ejecuta literalmente. Tras editarlo, ejecuta
`video-agent render <proyecto>`; las escenas no modificadas se reutilizan de la caché.
Los inicios (`start`) y la duración total se recalculan solos a partir de `duration` de cada escena.

## Nivel superior

| Campo | Tipo | Notas |
|---|---|---|
| `project`, `brief` | str | Nombre e instrucción original |
| `objective`, `goal`, `audience` | str | `goal`: leads, product, brand, service, traffic, followers, educational, community, ad, tech_product, gaming, local_business |
| `platform` | str | tiktok, instagram_reels, youtube_shorts, youtube, ad_vertical, square, landscape (define zonas seguras) |
| `language` | str | es / en |
| `duration` | float | Suma de las escenas (se recalcula) |
| `style` | str | tech_dark, cinematic, corporate, gaming, automotive, minimal, energetic |
| `palette` | [hex] | `[fondo, fondo2, acento, acento2, texto]` |
| `brand` | obj | `name`, `logo` (ruta en el proyecto), `palette`, `website`, `tagline` |
| `script` | [str] | Guion (informativo) |
| `hook_variants` | [str] | Ganchos para `variants` |
| `cta` | str | Llamada a la acción |
| `scenes` | [Scene] | Ver abajo |
| `music` | obj | `path` (archivo del usuario) · `generate` (base sintética local) · `mood` (electronic, cinematic, corporate, gaming, chill) · `bpm` · `volume_db` · `fade_in` · `fade_out` · `duck_under_voice` |
| `voiceover` | obj | `enabled` · `provider` (espeak / openai) · `voice` · `language` · `path` (locución grabada) |
| `subtitles` | obj | `enabled` · `source` (voiceover / transcribe / file) · `file` · `style` (minimal, corporate, cinematic, gaming, dynamic) · `highlight_words` · `max_words` · `font_scale` |
| `export` | obj | `width`, `height` (pares), `fps`, `format` (mp4 / mov / webm), `crf`, `filename` (relativo a `exports/`), `preview`, `letterbox` |
| `notes` | [str] | Avisos del planificador |

## Scene

| Campo | Tipo | Notas |
|---|---|---|
| `id` | str | Único (s01, s02…) |
| `purpose` | str | hook, problem, solution, benefits, cta, body… |
| `duration` | float | Segundos visibles de la escena |
| `source` | obj | `type`: clip, image, generated, color, logo · `path` (relativa al proyecto) · `start` (punto de entrada del clip) · `generator` (tech_grid, gradient, spotlight, speed_lines, minimal, bokeh) · `color` · `fit` (cover = recorte, contain = bandas, blur_fill = fondo desenfocado) · `keep_audio` · `seed` |
| `texts` | [TextOverlay] | Rótulos de la escena |
| `motion` | str | none, zoom_in, zoom_out, pan_left, pan_right, pan_up, pan_down |
| `motion_strength` | float | 0–0.5 (0.04–0.1 recomendado) |
| `speed` | float | 0.25–4 (cámara lenta / rápida) |
| `transition` | str | Transición HACIA la siguiente escena: cut, fade, fadeblack, fadewhite, dissolve, wipeleft/right/up/down, slideleft/right/up/down, smoothleft/right/up/down, circleopen, circleclose, zoomin, pixelize, radial, hblur, distance |
| `transition_duration` | float | 0–2 s (se limita a la mitad de las escenas que une) |
| `voiceover` | str | Frase de locución que empieza con la escena |
| `sfx` | str | whoosh, hit, rise, click (sintetizados localmente) |

## TextOverlay

| Campo | Tipo | Notas |
|---|---|---|
| `text` | str | Corto y legible en móvil (≤ 8 palabras) |
| `role` | str | hook (muy grande), title, body, cta (botón píldora), label (pequeño con barra) |
| `position` | str | top, center, bottom, lower_third — siempre dentro de la zona segura |
| `start`, `end` | float | Relativos a la escena (`end` null = hasta el final) |
| `animation` | str | none, fade, slide_up, slide_left, pop |
| `highlight` | [str] | Palabras en color de acento |
| `scale` | float | Multiplicador de tamaño (el texto se reduce solo si no cabe) |

## Ejemplo mínimo editado a mano

```json
{
  "id": "s01", "purpose": "hook", "duration": 2.5,
  "source": {"type": "clip", "path": "input/producto.mp4", "start": 3.2, "fit": "cover"},
  "texts": [{"text": "Tu web, lista en 7 días", "role": "hook", "position": "center",
             "animation": "slide_up", "highlight": ["7", "días"]}],
  "motion": "zoom_in", "motion_strength": 0.06, "transition": "smoothleft",
  "transition_duration": 0.35, "voiceover": "¿Necesitas una web profesional esta semana?", "sfx": "hit"
}
```
