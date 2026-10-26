# Ejemplo: promo de producto a partir de clips del usuario

## Material

```text
material/
├── unboxing.mov        # vertical, con sonido ambiente
├── detalle_producto.mp4
├── uso_exterior.mp4
├── logo_acme.png       # "logo" en el nombre → se usa en el cierre
└── musica_licenciada.mp3
```

## Petición

> Edita estos clips como un anuncio profesional de 15 segundos para Instagram Reels del nuevo
> termo Acme Flow. Quiero un estilo dinámico y que termine con «Consíguelo ahora».

Claude ejecuta:

```bash
video-agent create "Anuncio de 15 segundos para Instagram Reels del nuevo termo Acme Flow, estilo dinámico" \
  -i material/unboxing.mov -i material/detalle_producto.mp4 -i material/uso_exterior.mp4 \
  -i material/logo_acme.png -i material/musica_licenciada.mp3 \
  --goal product --brand "Acme Flow" --cta "Consíguelo ahora" --plan-only
```

Qué hace el sistema con el material:

1. Copia los archivos a `projects/acme-flow/input/` (con SHA-256; los originales no se tocan).
2. Analiza cada clip: formato, duración, audio, cortes de escena, tramos negros o congelados,
   nitidez y movimiento por segundo; descarta archivos dañados y duplicados; extrae fotogramas
   de referencia a `previews/reference/` (`reports/media_analysis.json`).
3. Asigna a cada escena el mejor fragmento sin repetir material, alternando clips.
4. Usa la música aportada (bucle si es corta, fundidos, normalización a −14 LUFS) y el logo en el cierre.

Claude mira los fotogramas de referencia, ajusta qué clip va en el gancho (el plano más
llamativo), reescribe los textos y renderiza:

```bash
video-agent render projects/acme-flow
video-agent inspect projects/acme-flow/exports/final.mp4 --platform instagram_reels --duration 15
```

## Otros formatos del mismo material

```bash
# versión horizontal para YouTube
video-agent create "Anuncio de 30 segundos del termo Acme Flow para YouTube" -i material/detalle_producto.mp4 -i material/uso_exterior.mp4 -i material/logo_acme.png --platform youtube
# tres cortos a partir de un vídeo largo de presentación
video-agent shorts material/presentacion.mp4 --count 3 --duration 20 --platform instagram_reels
```
