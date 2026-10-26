# AI Video Marketing Agent

Skill para **Claude Code** que convierte a Claude en un agente de edición de vídeo y marketing.
Describes el vídeo en lenguaje natural (y aportas, si quieres, clips, imágenes, logo, música o
locución) y el agente **planifica, monta con FFmpeg, añade textos animados, música, voz y
subtítulos, revisa el resultado con controles reales y entrega un MP4 listo para publicar**
en TikTok, Instagram Reels, YouTube Shorts, YouTube o como anuncio.

```text
«Quiero un vídeo de 25 segundos para promocionar Nexus Development. Estética tecnológica,
oscura y elegante, música electrónica, textos impactantes y final con el logotipo. TikTok.»
            │
            ▼
plan + guion + storyboard (JSON editable) → render FFmpeg → control de calidad → corrección
            │
            ▼
projects/nexus-development/exports/final.mp4  (1080×1920 · H.264/AAC · 25,00 s)
```

Funciona **en local y sin servicios de pago**: FFmpeg, fondos y gráficos generados con Pillow,
música sintética libre de derechos, voz con espeak-ng y transcripción con faster-whisper.
Los proveedores externos (voz natural de OpenAI, stock de Pexels) son opcionales y están
bloqueados hasta que los autorices.

---

## Índice

- [Qué hace (y qué no)](#qué-hace-y-qué-no)
- [Requisitos e instalación](#requisitos-e-instalación)
- [Instalar la skill en Claude Code](#instalar-la-skill-en-claude-code)
- [Uso desde Claude Code](#uso-desde-claude-code)
- [Uso desde la terminal (CLI)](#uso-desde-la-terminal-cli)
- [Estructura de un proyecto](#estructura-de-un-proyecto)
- [Configuración, proveedores y permisos](#configuración-proveedores-y-permisos)
- [Política de claves y recursos](#política-de-claves-y-recursos)
- [Pruebas](#pruebas)
- [Solución de problemas](#solución-de-problemas)
- [Arquitectura del código](#arquitectura-del-código)
- [Publicar en GitHub](#publicar-en-github)
- [Licencia](#licencia)

---

## Qué hace (y qué no)

| Capacidad | Estado | Cómo |
|---|---|---|
| Plan creativo desde una petición (objetivo, plataforma, duración, estilo, marca, guion, storyboard con tiempos, CTA) | ✅ Implementado y probado | `planner.py`, `marketing.py`, plantillas en `templates/` |
| Montaje real: recorte/escala a 9:16, 16:9 o 1:1, zooms y paneos, velocidad, corrección de color por estilo, transiciones (xfade), cortes al pulso de la música | ✅ | `editor.py` (FFmpeg) |
| Textos animados con jerarquía tipográfica, palabras resaltadas, botón CTA y zonas seguras por plataforma | ✅ | `motion_graphics.py` + overlay FFmpeg |
| Fondos animados, partículas en paralaje y logotipo final (o logotipo tipográfico provisional) | ✅ | Pillow + FFmpeg |
| Análisis del material: formato, duración, audio, archivos dañados, duplicados (exactos y visuales), cortes de escena, negros, congelados, nitidez/movimiento, fotogramas de referencia | ✅ | `media_manager.py` |
| Selección automática de fragmentos sin repetir material; montaje cronológico para material con voz | ✅ | `choose_segments`, `dialogue_scenes` |
| Música: la del usuario (bucle, fundidos) o base sintética local; ducking bajo la voz; normalización EBU R128 | ✅ | `audio.py` |
| Voz en off local (espeak-ng) | ✅ (voz robótica) | `tts.provider: espeak` |
| Voz en off natural (OpenAI TTS) | ⚠️ Implementado, **no probado contra la API real** (requiere clave y permiso de gasto) | `tts.provider: openai` |
| Transcripción real y subtítulos SRT/ASS animados (5 estilos, palabra activa resaltada, fuera de la interfaz de la app) | ✅ (faster-whisper) | `subtitles.py` |
| Control de calidad: decodificación completa, duración, resolución, SAR, códecs, audio, sincronía de pistas, negros, silencios, congelados, sonoridad, textos/subtítulos dentro de márgenes, hoja de contactos | ✅ | `quality_control.py` |
| Corrección automática y nuevo render (textos que no caben, subtítulos grandes, clips negros, audio, duración) con registro de intentos | ✅ | `agent.apply_fixes` |
| Variantes con ganchos distintos, reutilizando escenas en caché | ✅ | `video-agent variants` |
| Vídeo horizontal → varios Shorts verticales | ✅ | `video-agent shorts` |
| Búsqueda de stock en Pexels con registro de licencia | ⚠️ Implementado y probado con respuestas simuladas, no contra la API real | `asset_search.py` |
| Generación de imágenes o vídeo por IA | ❌ No integrado (no se inventan integraciones) | — |
| Motor MoviePy | ❌ No implementado: existe la interfaz `EditorBackend`; FFmpeg cubre todo el flujo | — |
| Publicar en redes | ❌ Deliberadamente no: el agente nunca publica | — |

Limitaciones honestas:

- El análisis automático de clips es **de señal**, no semántico. La comprensión del contenido la
  aporta Claude mirando los fotogramas de referencia y la hoja de contactos (visión real).
- La revisión visual automática es **por muestras** (un fotograma por escena), no fotograma a fotograma.
- La música sintética y la voz de espeak-ng son recursos de maqueta: para un anuncio final,
  aporta música con licencia y una locución (o activa un TTS natural).
- No se garantizan alcance, viralidad ni resultados comerciales.

## Requisitos e instalación

- Python ≥ 3.10
- **FFmpeg ≥ 5** con `libx264`, `libass` y `libfreetype` (las compilaciones estándar los incluyen)
- `fontconfig` (`fc-match`) y alguna fuente sans (Inter, DejaVu o Liberation)
- Opcional: `espeak-ng` (voz local) y `faster-whisper` (subtítulos de voz)

### 1. FFmpeg

```bash
# macOS
brew install ffmpeg espeak-ng
# Debian / Ubuntu
sudo apt install ffmpeg fontconfig fonts-dejavu espeak-ng
# Windows (winget) — o usa WSL
winget install Gyan.FFmpeg
```

Comprueba: `ffmpeg -filters | grep -E " (xfade|ass|loudnorm) "` debe listar los tres filtros.

### 2. Entorno Python

```bash
git clone https://github.com/<usuario>/ai-video-marketing-agent.git
cd ai-video-marketing-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[transcribe,dev]"      # sin subtítulos de voz: pip install -e .
video-agent doctor                       # verifica herramientas, proveedores y permisos
```

`faster-whisper` descarga el modelo (`small` por defecto, configurable) de huggingface.co en
el primer uso. Sin acceso a ese dominio, descarga un modelo CTranslate2 por otra vía y define
`VIDEO_AGENT_WHISPER_MODEL=/ruta/al/modelo`.

## Instalar la skill en Claude Code

La skill sigue el formato oficial de Claude Code (`skills/<nombre>/SKILL.md` con frontmatter
`name`/`description`), y el repositorio es a la vez **plugin y marketplace** (`.claude-plugin/`).
Elige una opción:

**A. Como plugin (recomendado para compartir)**

```text
/plugin marketplace add <usuario>/ai-video-marketing-agent
/plugin install ai-video-marketing-agent@ai-video-marketing-agent
```

En Claude Code 2.1.275 o posterior también funciona en un paso:
`/plugin install ai-video-marketing-agent --marketplace <usuario>/ai-video-marketing-agent`.
La skill aparece como `/ai-video-marketing-agent:video-marketing-agent`.

**B. Como skill personal (todos tus proyectos)**

```bash
mkdir -p ~/.claude/skills
ln -s "$PWD/skills/video-marketing-agent" ~/.claude/skills/video-marketing-agent
```

**C. Como skill de un proyecto concreto**

```bash
cd /ruta/a/tu-proyecto
mkdir -p .claude/skills
ln -s /ruta/a/ai-video-marketing-agent/skills/video-marketing-agent .claude/skills/video-marketing-agent
```

En los tres casos la skill ejecuta `scripts/video-agent`, que usa el comando `video-agent` si
lo instalaste con pip o, si no, el código del repositorio clonado (`.venv` incluido). Si
copias la carpeta de la skill en lugar de enlazarla, instala el paquete con
`pip install -e /ruta/a/ai-video-marketing-agent`.

Comprueba la instalación: abre Claude Code en tu proyecto y escribe `/video-marketing-agent`
(o pide «hazme un vídeo…»: la skill se activa sola por su descripción).

## Uso desde Claude Code

Escribe lo que necesitas; la skill decide el comando, planifica, renderiza, revisa la hoja de
contactos y te entrega el archivo:

- «Hazme un vídeo de 30 segundos para TikTok de mi cafetería *La Esquina*»
- «Edita estos clips como un anuncio profesional: ./clips/*.mp4, el logo está en ./marca/logo.png»
- «Crea un vídeo cinematográfico de un coche con estos planos»
- «Convierte este vídeo horizontal en tres Shorts»
- «Haz un vídeo promocional de mi página web www.ejemplo.com»
- «Añade subtítulos dinámicos y música a entrevista.mp4»
- «Analiza este vídeo y mejora su edición»
- «Crea cinco versiones con diferentes ganchos»
- «Haz un vídeo de gaming con cortes rápidos»
- «Crea una campaña de vídeo para conseguir clientes»

El agente solo pregunta si falta algo esencial (p. ej. el nombre de la marca). Pedirá
permiso antes de gastar dinero, usar servicios externos, publicar o tocar tus originales.

## Uso desde la terminal (CLI)

```bash
video-agent create "Vídeo promocional de mi empresa para TikTok" --brand "Acme" --duration 20
video-agent create "Anuncio de 15 s para Acme" -i clip1.mp4 -i clip2.mov -i logo.png --plan-only
video-agent render projects/acme                 # (re)renderiza desde project.json
video-agent edit ./input/video.mp4 --style cinematic --platform youtube
video-agent subtitle entrevista.mp4 --style dynamic --music musica.mp3
video-agent shorts charla.mp4 --count 3 --duration 30 --platform youtube_shorts
video-agent variants projects/acme --count 3
video-agent inspect projects/acme/exports/final.mp4 --platform tiktok --duration 20
video-agent doctor
```

Todos los comandos tienen `--help`, validan sus parámetros y aceptan `--json`.
`inspect` devuelve código de salida 1 si el vídeo no pasa el control.

Estilos: `tech_dark`, `cinematic`, `corporate`, `gaming`, `automotive`, `minimal`, `energetic`.
Plataformas: `tiktok`, `instagram_reels`, `youtube_shorts`, `youtube`, `ad_vertical`, `square`, `landscape`.
Objetivos: `leads`, `product`, `brand`, `service`, `traffic`, `followers`, `educational`,
`community`, `ad`, `tech_product`, `gaming`, `local_business`.

Ejemplos completos con su salida: [examples/marketing_video.md](examples/marketing_video.md) y
[examples/product_promo.md](examples/product_promo.md).

## Estructura de un proyecto

```text
projects/nombre-del-proyecto/
├── project.json        # plan de edición + material + procedencia + intentos + entregables
├── input/              # copias del material del usuario (los originales no se tocan)
├── assets/             # recursos generados (fondos, logotipo provisional) y de stock
├── audio/              # música preparada/sintética, locución, efectos
├── subtitles/          # captions.srt y captions.ass
├── storyboard/         # plan.json, storyboard.md, script.md
├── timeline/           # montaje intermedio y timeline_*.json (segmentos, tiempos, rótulos)
├── previews/           # vista previa, miniatura, fotogramas de referencia y de QC, hoja de contactos
├── exports/            # final.mp4 y variants/
├── reports/            # qc_report.md/json, summary.md, media_analysis.json
└── cache/              # escenas renderizadas (reutilizadas si no cambian)
```

`project.json` es reproducible: edítalo (textos, clips, duraciones, transiciones…) y ejecuta
`video-agent render <proyecto>`. Esquema: [skills/video-marketing-agent/reference/plan-schema.md](skills/video-marketing-agent/reference/plan-schema.md).

## Configuración, proveedores y permisos

`config/settings.yaml` contiene los valores por defecto. Para cambiarlos sin tocar el
repositorio, crea `video-agent.yaml` en tu directorio de trabajo (o apunta
`VIDEO_AGENT_SETTINGS` a un YAML) con solo las claves que cambies:

```yaml
render: {crf: 18, preset: slow}
audio: {loudness_lufs: -14}
limits: {max_duration_s: 180, max_render_attempts: 3, max_estimated_cost_usd: 0.5}
permissions: {allow_paid_apis: true}       # solo tras decidirlo tú
tts: {provider: openai}
```

- `config/platforms.yaml`: resolución, FPS, duración y **zonas seguras** de cada plataforma.
  Las recomendaciones de las redes cambian: revisa su documentación vigente y ajusta.
- `config/editing_presets.yaml`: estilos (paleta, corrección de color, transiciones, ritmo, música).
- `config/marketing.yaml`: objetivos (ganchos, mensajes, CTA) en español e inglés.
- `templates/`: estructura narrativa por plataforma.

Proveedores opcionales (copia `.env.example` a `.env`):

| Proveedor | Variable | Coste | Activación |
|---|---|---|---|
| OpenAI TTS (voz natural) | `OPENAI_API_KEY` ([crear clave](https://platform.openai.com/api-keys)) | De pago | `tts.provider: openai` + `permissions.allow_paid_apis: true` + `limits.max_estimated_cost_usd` > 0 |
| Pexels (stock) | `PEXELS_API_KEY` ([gratis](https://www.pexels.com/api/)) | Gratis | `permissions.allow_network_asset_search: true` |
| Whisper | `VIDEO_AGENT_WHISPER_MODEL` | Local | `pip install -e ".[transcribe]"` |

## Política de claves y recursos

- Las claves van en variables de entorno o en `.env` (excluido por `.gitignore`). Nunca en el código ni en `project.json`.
- Por defecto todo lo que cuesta dinero, usa la red o envía material fuera del equipo está **desactivado**
  (`permissions`). El agente pide autorización antes de activarlo.
- Los originales del usuario se copian a `input/` (con su SHA-256) y nunca se modifican.
- Cada recurso externo o generado queda registrado en `project.json → provenance` (origen, licencia, autor, URL).
- Usa solo música, voces e imágenes con derechos de uso. No se descarga contenido protegido ni se eliminan marcas de agua.
- `.gitignore` excluye `projects/` y los formatos multimedia para no subir material privado.

## Pruebas

```bash
pytest                          # suite completa (≈2 min, genera su propio material con FFmpeg)
pytest -m "not slow"            # sin el render 1080×1920 completo
VIDEO_AGENT_WHISPER_MODEL=small pytest -m transcription   # prueba C con Whisper real
```

| Prueba de aceptación | Test |
|---|---|
| A. Vídeo de entrada → versión editada con cortes, textos y MP4 | `tests/test_editor.py::test_A_edit_input_video_with_cuts_and_text` |
| B. TikTok vertical a partir de clips | `tests/test_editor.py::test_B_tiktok_vertical_from_clips` |
| C. Subtítulos con transcripción real | `tests/test_subtitles.py::test_C_subtitles_from_real_transcription` |
| D. Detectar exportaciones defectuosas e informar | `tests/test_quality_control.py::test_D_*` |
| E. Re-ejecutar desde project.json (también editado a mano) | `tests/test_editor.py::test_E_rerender_from_project_json` |
| F. Estructura y metadatos de la skill/plugin | `tests/test_cli_and_integrations.py::test_F_skill_structure` + `claude plugin validate .` |

Las integraciones de pago o con red (OpenAI, Pexels) se prueban con respuestas simuladas y
permisos; las pruebas contra las APIs reales necesitan tus claves.

## Solución de problemas

| Problema | Solución |
|---|---|
| `'ffmpeg' no está instalado` | Instala FFmpeg (ver arriba) y abre una terminal nueva |
| `FFmpeg sin filtros: ass` / `xfade` | Tu FFmpeg es mínimo o antiguo: instala la versión completa (≥ 5) |
| `No se pudo cargar el modelo Whisper` | Sin acceso a huggingface.co: modelo local + `VIDEO_AGENT_WHISPER_MODEL` |
| `espeak-ng no está instalado` | `brew/apt install espeak-ng`, o desactiva la voz (`--voiceover off`) |
| «El texto no cabe en la zona segura» | Acorta el texto; el agente reduce el tamaño automáticamente en cada intento |
| Subtítulos con fuente incorrecta | Instala Inter o DejaVu, o cambia `fonts.subtitle` en la configuración |
| Render lento | Reduce `export.fps`/resolución para pruebas; la caché evita repetir escenas |
| La skill no aparece en Claude Code | Comprueba la ruta `…/skills/video-marketing-agent/SKILL.md` y reinicia la sesión (o `/reload-plugins`) |
| `Faltan dependencias de Python` | `pip install -e /ruta/a/ai-video-marketing-agent` en el Python que usa la skill (o crea `.venv` en el repo) |

## Arquitectura del código

```text
src/video_agent/
├── cli.py              # comandos video-agent
├── agent.py            # orquestador: ingesta → plan → render → QC → corrección → entrega
├── planner.py          # director creativo: petición → EditPlan (escenas, tiempos, textos, audio)
├── marketing.py        # objetivos, ganchos, CTA, variantes
├── models.py           # esquema Pydantic del plan (project.json)
├── project_manager.py  # carpetas, importación segura, procedencia, intentos
├── media_manager.py    # análisis de material y selección de fragmentos
├── editor.py           # motor FFmpeg (EditorBackend): escenas, transiciones, mezcla, exportación
├── motion_graphics.py  # fondos, partículas, rótulos, logotipos, hoja de contactos
├── audio.py            # música sintética, TTS, efectos, ducking, sonoridad
├── subtitles.py        # Whisper, SRT, ASS animado, comprobación de márgenes
├── quality_control.py  # controles técnicos y visuales reales
├── exporter.py         # presets, vista previa, miniatura, formatos
├── asset_search.py     # biblioteca local y Pexels
├── integrations.py     # detección de capacidades y permisos
└── ff.py, config.py    # utilidades FFmpeg y configuración
```

## Publicar en GitHub

```bash
cd ai-video-marketing-agent
git init -b main
git add .
git commit -m "AI Video Marketing Agent v0.1.0"
# con GitHub CLI:
gh repo create ai-video-marketing-agent --public --source . --push
# o crea el repositorio vacío en github.com y:
git remote add origin https://github.com/<usuario>/ai-video-marketing-agent.git
git push -u origin main
git tag v0.1.0 && git push origin v0.1.0
```

## Licencia

[MIT](LICENSE). La música y los gráficos que genera el sistema son propios del proyecto. Los
recursos que aportes o descargues mantienen su propia licencia (ver `provenance`).
