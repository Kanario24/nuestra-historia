# assets/

Biblioteca local de recursos reutilizables entre proyectos (vídeos, imágenes, música,
fuentes). `video-agent` busca aquí con `asset_search.search_local` (configurable en
`asset_search.local_dirs`).

- Añade solo material con derechos de uso y anota la licencia.
- Puedes etiquetar archivos con un `tags.json` en cada carpeta:
  `{"coche_rojo.mp4": ["coche", "deportivo", "noche"]}`.
- Los archivos multimedia están excluidos de Git por `.gitignore` (no subas material privado
  ni pesado al repositorio).
