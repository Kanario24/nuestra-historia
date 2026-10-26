# Ejemplo: vídeo de marca para TikTok (ejecución real)

**Petición en Claude Code**

> Quiero un vídeo de 25 segundos para promocionar Nexus Development. Quiero una estética
> tecnológica, oscura y elegante, con transiciones dinámicas, música electrónica, textos
> impactantes y un final con el logotipo. Formato vertical para TikTok.

## 1. Plan automático

```bash
video-agent create "<petición>" --plan-only
```

El planificador detecta: duración 25 s · plataforma `tiktok` (1080×1920) · estilo `tech_dark`
· marca «Nexus Development» · música electrónica (base sintética local a 120 BPM, cortes
ajustados al pulso) · objetivo «presentar una marca» · cierre con logotipo.

## 2. Reescritura del mensaje (Claude, como director creativo)

Claude sustituye los textos genéricos en `project.json` por un mensaje para el público real
(fundadores y pymes que necesitan software a medida) y divide la escena de solución en dos:

| Tiempo | Escena | Texto en pantalla | Movimiento | Transición |
|---|---|---|---|---|
| 00:00–00:03 | gancho | ¿Tu **idea** sigue en una libreta? | zoom in | fadeblack |
| 00:03–00:07,5 | problema | Sin **código**, una idea es solo una idea. | paneo | smoothleft |
| 00:07,5–00:10,5 | solución | **Nexus Development** la convierte en software | zoom out | slideup |
| 00:10,5–00:13,5 | solución | Webs · Apps · **IA** / A medida. Escalable. Seguro. | paneo | slideup |
| 00:13,5–00:16 | beneficio | Diseño que **convierte** | paneo | zoomin |
| 00:16–00:18,5 | beneficio | Código que **escala** | zoom in | fade |
| 00:18,5–00:21 | beneficio | Soporte que **responde** | paneo | fadeblack |
| 00:21–00:25 | CTA | Logotipo + «Hablemos de tu proyecto» + nexusdevelopment.com | zoom in | — |

Ganchos alternativos guardados para `variants`: «Tu próxima app empieza aquí», «Deja de pagar
por plantillas», «De la idea al lanzamiento en semanas», «¿Y si tu web vendiera mientras duermes?».

## 3. Render y control de calidad

```bash
video-agent render projects/nexus-development
```

```text
🎬 projects/nexus-development/exports/final.mp4
   1080×1920 · 25.00s · QC APROBADO (1 intento/s)
```

Extracto de `reports/qc_report.md`:

| | Comprobación | Detalle |
|---|---|---|
| ✅ | Decodificación completa | Todo el archivo se decodifica sin errores |
| ✅ | Duración | 25.00s (esperado 25.00s) |
| ✅ | Resolución | 1080×1920 · SAR 1:1 · 30 fps · H.264 yuv420p + AAC |
| ✅ | Sincronía A/V | vídeo 25.000s / audio 25.000s |
| ✅ | Negros / silencios / congelados | Ninguno inesperado |
| ✅ | Sonoridad | −14.3 LUFS (objetivo −14), pico −1.4 dBTP |
| ✅ | Textos | 10 rótulos dentro de la zona segura de TikTok |

Claude revisa además `previews/qc_final/contact_sheet.jpg` (un fotograma por escena) para
comprobar legibilidad, jerarquía y composición.

Tiempo de render en un contenedor de 4 núcleos: ~90 s. Volver a renderizar tras cambiar un
texto solo recalcula esa escena (caché).

## 4. Entregables

```text
projects/nexus-development/
├── exports/final.mp4
├── previews/final_preview.mp4, final_thumbnail.jpg, qc_final/contact_sheet.jpg
├── storyboard/plan.json, storyboard.md, script.md
└── reports/qc_report.md, summary.md
```

Avisos en la entrega: el logotipo es tipográfico provisional (no se aportó archivo) y la
música es una base sintética local; para publicar, sustitúyelos por el logo real y música
con licencia (`-i logo.png -i musica.mp3`).

## Variantes para pruebas A/B

```bash
video-agent variants projects/nexus-development --count 3
# exports/variants/variant_01.mp4 … variant_03.mp4 (solo se re-renderiza la escena del gancho)
```
