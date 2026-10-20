# Improved Shopping List

<img src="custom_components/improved_shopping_list/brand/icon.png" alt="Improved Shopping List" width="96">

Una interfaz propia para gestionar las listas de la compra que ya tienes integradas en Home Assistant.

Versión actual: **0.2.0**. Interfaz en español, pensada para móvil y ordenador. Requiere **Home Assistant Core 2026.10 o posterior**. La referencia de desarrollo es Core 2026.10.2.

## Qué puedes hacer

- Seleccionar cualquier entidad `todo.*` disponible para tu usuario, incluida Bring!, Shopping List u otros proveedores.
- Consultar productos pendientes y comprados.
- Añadir productos, marcarlos como comprados y volver a ponerlos por comprar.
- Recibir cambios del proveedor mediante la API nativa de listas de Home Assistant.
- Cambiar de lista desde el panel y cambiar la predeterminada desde la configuración de la integración.
- Crear y editar productos en un catálogo local compartido entre los usuarios de Home Assistant, con vistas Productos y Categorías.
- Asignar categorías, etiquetas, marcas, formatos, códigos de barras, precios orientativos, imágenes y notas.
- Buscar, filtrar y añadir productos del catálogo a la lista seleccionada.

Cada lista conserva sus datos en su integración original. Las operaciones disponibles dependen de lo que admita ese proveedor. Por ejemplo, una lista de solo lectura se puede consultar, pero sus controles de edición aparecen desactivados. La frecuencia con la que Bring! u otro proveedor recibe cambios de su nube depende de su propia integración.

El panel se comunica con Home Assistant usando la sesión del usuario y las APIs nativas. No necesita tokens adicionales, cuentas nuevas ni servicios externos. El JavaScript se sirve localmente y no utiliza un CDN.

## Instalación con HACS

Este repositorio se instala como repositorio personalizado; no está incluido en el catálogo predeterminado de HACS.

1. En HACS, abre el menú de los tres puntos → **Repositorios personalizados**.
2. Añade `https://github.com/TitoTB/Improved-Shopping-List` con tipo **Integración**.
3. Busca **Improved Shopping List**, descarga la última versión y reinicia Home Assistant.
4. Abre **Ajustes → Dispositivos y servicios → Añadir integración**.
5. Busca **Improved Shopping List** y selecciona tu lista de la compra predeterminada.
6. Abre **Improved Shopping List** desde la barra lateral.

Si no tienes ninguna entidad `todo.*`, configura antes Bring!, Shopping List u otra integración que proporcione listas. No necesitas añadir YAML ni recursos de dashboard manualmente.

Si el panel no aparece después de instalar, recarga la página o cierra y abre la aplicación de Home Assistant. Tras actualizar, una recarga completa también permite descartar una versión antigua del JavaScript.

## Actualizaciones

Las versiones se publican en GitHub. HACS permite detectar y descargar las nuevas versiones. Por defecto, decide tú cuándo instalarlas y reiniciar Home Assistant; esta integración no activa instalaciones automáticas.

Para publicar una versión, los mantenedores actualizan la versión en `manifest.json`, `const.py`, `package.json`, la referencia de módulo y el texto de versión en `frontend/panel.js`, el lockfile y `CHANGELOG.md`. Después suben una etiqueta `vX.Y.Z`. GitHub Actions ejecuta las comprobaciones y publica la release si pasan. Los cambios en la rama principal sin una nueva versión no se publican automáticamente como una actualización estable.

## Alcance de esta primera versión

El catálogo se guarda en el almacenamiento de Home Assistant, no en el navegador. Todos los usuarios autenticados que utilicen el panel comparten el mismo catálogo. Las listas siguen perteneciendo a sus proveedores originales; se añade el nombre del producto a la lista, y las propiedades adicionales permanecen en su ficha del catálogo.

Solo es obligatorio el nombre. Las categorías se crean, editan y eliminan desde la vista Categorías, donde puedes elegir su icono MDI y su color. Renombrar una categoría actualiza sus productos; eliminarla los conserva sin categoría. Las categorías introducidas en instalaciones anteriores se recuperan automáticamente con un icono y un color predeterminados. Las etiquetas se introducen separadas por comas en la ficha del producto.

Las tarjetas muestran primero la imagen o el icono del producto y debajo su nombre, centrados. Si no hay imagen ni icono asignados se usa `mdi:shopping`. La categoría se representa con un icono blanco sobre un círculo de su color en la esquina superior derecha. Las imágenes se asignan mediante una URL http/https o una ruta local como `/local/cacao.png`; esta versión no incluye subida de archivos ni descarga de imágenes al servidor. El navegador carga la imagen desde la ubicación indicada.

Los productos pendientes en la lista seleccionada se resaltan con un degradado rojo. La coincidencia se realiza por nombre, sin distinguir mayúsculas ni diferencias de espacios; los elementos comprados no se resaltan. Cambiar de lista actualiza este estado visual y conserva el catálogo común.

El apartado Lista también presenta los productos en una cuadrícula de tarjetas, con imagen o icono y nombre centrados. Si el nombre coincide con una ficha del catálogo, utiliza su imagen, icono, marca, formato, etiquetas y distintivo de categoría. Para productos sin ficha se muestra `mdi:shopping`. Las tarjetas mantienen el control para marcar o desmarcar la compra y el apartado desplegable de comprados, sin mostrar precios.

El campo Añadir producto ofrece hasta ocho coincidencias del catálogo mientras escribes, por nombre, marca, código de barras o etiquetas, sin distinguir tildes ni mayúsculas. Puedes tocar una coincidencia o seleccionarla con las flechas y Enter para añadir su nombre a la lista. Escape cierra el desplegable. También puedes escribir y añadir un producto nuevo libremente.

La barra de Lista reúne en una sola fila el buscador, el botón de añadir (`mdi:plus-thick`) y el selector de listas (`mdi:format-list-checks`). Este último abre un popup con las listas integradas en Home Assistant y marca la seleccionada; toca otra lista para cambiar. La opción de actualizar la lista está dentro de ese popup.

La vista **Sugerencias** (`mdi:creation`) muestra los nombres de productos de la lista seleccionada que aún no están en el catálogo, incluidos los elementos comprados que siguen en la lista. Puedes añadirlos al catálogo en un clic y completar su ficha más adelante, o descartarlos sin modificar la lista. Los nombres repetidos se agrupan ignorando mayúsculas y espacios sobrantes. Los descartes se guardan en Home Assistant, se comparten entre sesiones y listas y se conservan tras reiniciar. Para cambiar la lista de origen, utiliza el selector del apartado Lista.

El precio es manual y orientativo, asociado al formato y la moneda indicados, con su fecha de actualización. Se conserva en la ficha de edición, pero no se muestra en las tarjetas. Todavía no hay comparación de ofertas por supermercado, consulta automática de precios, lector de códigos, Open Food Facts, scrapeo ni importación de PDF. El código de barras se guarda como texto para conservar sus ceros iniciales.

Las ediciones simultáneas se detectan: si otra sesión ha cambiado una ficha, se pide volver a abrirla antes de guardar. No se borra el catálogo al cambiar de lista ni al recargar la integración. Se conserva también al retirar la integración para permitir reinstalarla; los productos de las listas originales tampoco se eliminan.

La configuración de la lista predeterminada se guarda en Home Assistant. El selector del panel permite abrir otra lista durante la sesión; no modifica la predeterminada. Para cambiarla de forma permanente, utiliza **Configurar** en la integración.

Eliminar la integración retira el panel y desactiva sus comandos de catálogo.

## Desarrollo y comprobaciones

La integración Python registra la configuración, el panel y los comandos WebSocket autenticados del catálogo. `catalog.py` valida y guarda el catálogo con `Store`; no depende de ningún proveedor de listas. La interfaz utiliza Web Components sin proceso de compilación. `todo-client.js` encapsula las llamadas nativas y la gestión de suscripciones; no duplica el almacenamiento del proveedor. `catalog-panel.js` y `catalog-client.js` implementan la vista y el acceso al catálogo.

```sh
npm ci
npm run check
npm test
npx playwright install chromium
npm run test:ui
python -m compileall -q custom_components
```

Las pruebas de navegador utilizan una API de Home Assistant simulada. Comprueban la interfaz y sus llamadas, pero no sustituyen la prueba final en una instancia real con Bring! u otro proveedor. Las capturas se generan en `test-results/`.

GitHub Actions añade las validaciones de Hassfest y HACS. También ejecuta pruebas de configuración, registro del panel, cambios de opciones, recarga y entrega de archivos usando Home Assistant Core 2026.10.2 real sobre Linux. Para ejecutarlas localmente necesitas Python 3.14.2 o posterior: `pip install -r requirements_test.txt` y `pytest -q`.

La instalación real en Home Assistant debe comprobarse con el recorrido siguiente:

1. Configurar la integración con Bring! y abrir el panel.
2. Añadir un producto y comprobar que aparece en Bring!.
3. Marcarlo como comprado y devolverlo a pendientes.
4. Editar la lista desde Bring!, esperar a que su integración reciba el cambio y comprobar el panel.
5. Cambiar a otra entidad `todo.*` y comprobar que no se mezclan sus productos.
6. Cambiar la lista predeterminada desde Configurar y reiniciar Home Assistant.

## Licencia

MIT. Consulta [LICENSE](LICENSE).
