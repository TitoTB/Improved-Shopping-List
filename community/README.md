# Diccionario de imágenes comunitarias

## Aportar

En Ajustes → Comunidad → Exportar mis iconos se descarga un ZIP voluntario. El usuario decide si lo envía al mantenedor. No hay envíos automáticos, cuentas adicionales ni servidores externos de recepción.

El ZIP contiene `dictionary.json`, las imágenes locales admitidas y datos de procedencia/licencia disponibles. Solo se incluyen nombres de productos, traducciones almacenadas, referencias a imágenes/iconos y su presencia en el catálogo local. No incluye códigos, notas, etiquetas, categorías, entidades, listas ni credenciales. Las URL con parámetros o credenciales se omiten. No se descargan URL externas durante la exportación. Se admiten SVG estáticos, PNG, JPEG y WebP locales; archivos inexistentes, no compatibles o fuera de los directorios de imágenes permitidos se omiten.

Si falta `name_en`, el mantenedor debe completar la traducción antes de publicar. Todos los registros exportados llevan `requires_review: true`; una exportación no concede derechos de redistribución.

## Incorporar una aportación

1. Revisar el JSON y las imágenes sin ejecutar contenido; no extraer rutas arbitrarias de ZIP recibidos. Verificar procedencia y licencia, incluidos los avisos y atribuciones exigidos. No publicar imágenes con permisos desconocidos.
2. Asignar un identificador estable al término inglés; agrupar sinónimos y variantes sin confundir productos distintos.
3. Eliminar imágenes idénticas mediante SHA-256. Guardar el archivo revisado en `images/<sha256>.<extensión>` y añadir su registro a `index.json`.
4. Registrar cada aportación revisada una sola vez. Un reenvío del mismo ZIP no debe incrementar el contador. `catalog_uses` del ZIP no equivale a usuarios ni a descargas globales.
5. Ejecutar `npm run check` antes de publicar. La integración vuelve a consultar el índice cada 24 horas y conserva una copia si no hay conexión. No necesita una nueva versión para recibir nuevas imágenes.

## Formato público

```json
{
  "schema_version": 1,
  "icons": [{
    "id": "rice-bowl",
    "name_en": "Rice",
    "terms": ["rice", "arroz"],
    "file": "images/<sha256>.svg",
    "sha256": "<sha256>",
    "author": "Autor revisado",
    "license": "CC0-1.0",
    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
    "contributions": 1
  }]
}
```

`contributions` cuenta aportaciones independientes revisadas que usan esa imagen para ese término, no todos los usuarios de la integración. El orden es decreciente por ese contador y estable por identificador en los empates. El índice comienza vacío; no hay estadísticas inventadas.

La integración antepone estas sugerencias a Iconify. Solo descarga una imagen cuando el usuario la elige, verifica su hash y la guarda localmente con su atribución. Las búsquedas usan la traducción almacenada y los términos alternativos publicados. No se envían eventos de selección ni datos del catálogo al repositorio.
