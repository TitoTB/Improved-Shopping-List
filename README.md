# Improved Shopping List

<img src="custom_components/improved_shopping_list/brand/icon.png" alt="Improved Shopping List" width="96">

Una interfaz propia para gestionar las listas de la compra que ya tienes integradas en Home Assistant.

Versión actual: **0.6.0**. Interfaz en español, pensada para móvil y ordenador. Requiere **Home Assistant Core 2026.10 o posterior**. La referencia de desarrollo es Core 2026.10.2.

## Qué puedes hacer

- Seleccionar cualquier entidad `todo.*` disponible para tu usuario, incluida Bring!, Shopping List u otros proveedores.
- Consultar productos pendientes y comprados.
- Añadir productos, marcarlos como comprados y volver a ponerlos por comprar.
- Recibir cambios del proveedor mediante la API nativa de listas de Home Assistant.
- Añadir o quitar entidades `todo` desde Ajustes y marcar una lista como principal.
- Crear y editar productos en un catálogo local compartido entre los usuarios de Home Assistant, con vistas Productos y Categorías.
- Asignar categorías, etiquetas, códigos de barras, precios orientativos, imágenes y notas.
- Buscar, filtrar y añadir productos del catálogo a la lista seleccionada.

Cada lista conserva sus datos en su integración original. Las operaciones disponibles dependen de lo que admita ese proveedor. Por ejemplo, una lista de solo lectura se puede consultar, pero sus controles de edición aparecen desactivados. La frecuencia con la que Bring! u otro proveedor recibe cambios de su nube depende de su propia integración.

El panel se comunica con Home Assistant usando la sesión del usuario y las APIs nativas. No necesita tokens adicionales ni cuentas nuevas. Las funciones de consulta de productos e iconos utilizan Open Food Facts e Iconify respectivamente; la gestión de listas y del catálogo funciona sin esos servicios. El JavaScript se sirve localmente y no utiliza un CDN.

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

Las tarjetas muestran primero la imagen o el icono del producto y debajo su nombre, centrados. Si no hay imagen se utiliza el icono propio del producto; si tampoco tiene icono propio, se utiliza el de su categoría y, cuando no tiene categoría, `mdi:shopping`. Este criterio también se aplica en Lista y en sus sugerencias de búsqueda. En Lista, la categoría se representa con un icono blanco sobre un círculo de su color en la esquina superior derecha, sin borde y con sombra. En Catálogo → Productos, las tarjetas son cuadradas: pulsar su superficie añade el producto a la lista seleccionada, también con Enter o espacio. Los dos controles circulares de la esquina permiten editar (con el color de la categoría, o gris si no tiene) y eliminar (fondo negro), sin activar la acción de añadir. El borrado pide confirmación, elimina la ficha y sus códigos del catálogo y conserva los elementos de las listas. El selector de categorías permite filtrar los productos. Las imágenes se pueden asignar mediante una URL http/https o una ruta local como `/local/cacao.png`. El navegador carga las imágenes manuales desde la ubicación indicada; no se descargan al servidor ni hay subida de archivos.

En la ficha del producto, **Buscar icono** permite consultar [Iconify](https://iconify.design/) gratuitamente y sin clave. Se muestran cinco alternativas por página, con **Ver más** y **Anteriores**, entre colecciones MDI, Tabler, OpenMoji, Noto Emoji y Fluent Emoji Flat. La búsqueda empieza con el nombre del producto y se puede modificar; los nombres de muchos iconos están en inglés y no se realiza traducción automática. Si no hay resultados, prueba con un término inglés como `milk` o `bread`.

Las búsquedas se realizan desde Home Assistant y las vistas previas se cargan desde Iconify en el navegador. Al elegir un icono se descarga y valida un SVG estático, se guarda en `.storage/improved_shopping_list_icons` y su ruta local se coloca en el campo de imagen. El producto solo cambia al pulsar **Guardar producto**. El archivo elegido sigue disponible sin Internet y después de reiniciar Home Assistant. El autor, la colección, la fuente y la licencia se conservan en `.storage/improved_shopping_list.icon_assets` y se muestran en la ficha. Los archivos son recursos públicos del panel, igual que su logo, y no contienen información de productos ni credenciales. Cancelar una ficha puede dejar un icono en la caché local, sin cambiar el catálogo. Las consultas se guardan temporalmente en memoria durante seis horas; no se envían códigos de barras ni otros datos de la ficha a Iconify, solo el término de búsqueda y el identificador elegido.

Los productos pendientes en la lista seleccionada se resaltan con un degradado rojo. La coincidencia se realiza por nombre, sin distinguir mayúsculas ni diferencias de espacios; los elementos comprados no se resaltan. Cambiar de lista actualiza este estado visual y conserva el catálogo común.

El apartado Lista también presenta los productos en una cuadrícula de tarjetas, con imagen o icono y nombre centrados. Si el nombre coincide con una ficha del catálogo, utiliza su imagen, icono, etiquetas y distintivo de categoría. Para productos sin ficha se muestra `mdi:shopping`. Pulsa una tarjeta completa para marcar o desmarcar su compra; también funciona con Enter o espacio. Se conserva el apartado desplegable de comprados, sin mostrar precios ni un control de compra dentro de cada tarjeta.

En **Ajustes → Personalización** puedes elegir por separado los dos colores del degradado de productos pendientes y los de Comprados, además del número de tarjetas por fila, de 1 a 6 en ordenador y de 1 a 4 en móvil. Por defecto los pendientes usan `linear-gradient(rgba(238, 82, 79, 1), rgba(181, 42, 39, 1))` y los comprados `linear-gradient(rgba(79, 171, 162, 1), rgba(38, 133, 124, 1))`, con 3 productos por fila en ordenador y 1 en móvil. Pulsa la tarjeta de un producto comprado para devolverlo a Por comprar; se actualiza el mismo elemento, sin duplicarlo ni mostrar un control adicional dentro de la tarjeta. Los cambios se aplican al guardar, persisten en Home Assistant y se comparten entre dispositivos. Con los degradados predeterminados, el texto y los iconos son blancos; con colores personalizados, el texto se adapta a los colores elegidos. Restablecer valores permite recuperar estos valores y guardarlos de nuevo.

El campo Añadir producto ofrece hasta ocho coincidencias del catálogo mientras escribes, por nombre, marca, código de barras o etiquetas, sin distinguir tildes ni mayúsculas. Puedes tocar una coincidencia o seleccionarla con las flechas y Enter para añadir su nombre a la lista. Escape cierra el desplegable. También puedes escribir y añadir un producto nuevo libremente.

El número de tarjetas por fila configurado en Personalización se aplica a Lista, Catálogo → Productos y Catálogo → Categorías, con valores separados para móvil y ordenador.

La barra de Lista reúne en una sola fila el buscador, el botón de añadir (`mdi:plus-thick`) y el selector de listas (`mdi:format-list-checks`). Este último abre un popup con las listas integradas en Home Assistant y marca la seleccionada; toca otra lista para cambiar. La opción de actualizar la lista está dentro de ese popup.

La vista **Sugerencias** (`mdi:creation`) muestra los nombres de productos de la lista seleccionada que aún no están en el catálogo, incluidos los elementos comprados que siguen en la lista. Añadir al catálogo abre el formulario con el nombre ya rellenado, para completar categoría, marca, etiquetas y otros datos antes de guardar. Cancelar conserva la sugerencia sin crear el producto. También puedes descartar sugerencias sin modificar la lista. Los nombres repetidos se agrupan ignorando mayúsculas y espacios sobrantes. Los descartes se guardan en Home Assistant, se comparten entre sesiones y listas y se conservan tras reiniciar. Para cambiar la lista de origen, utiliza el selector del apartado Lista.

El precio es manual y orientativo, asociado al producto y la moneda indicados, con su fecha de actualización. Se conserva en la ficha de edición, pero no se muestra en las tarjetas. Todavía no hay comparación de ofertas por supermercado, consulta automática de precios, scrapeo ni importación de PDF. El código de barras se guarda como texto para conservar sus ceros iniciales. Los campos Marca y Formato se han retirado; las instalaciones anteriores eliminan esos campos al cargar el catálogo, conservando los productos y sus códigos.

Las ediciones simultáneas se detectan: si otra sesión ha cambiado una ficha, se pide volver a abrirla antes de guardar. No se borra el catálogo al cambiar de lista ni al recargar la integración. Se conserva también al retirar la integración para permitir reinstalarla; los productos de las listas originales tampoco se eliminan.

El apartado **Ajustes** (`mdi:cog`) permite añadir cualquier entidad `todo` de Home Assistant, quitar listas de esta interfaz y marcar una como principal. El popup de Lista muestra únicamente las listas añadidas; la principal se abre al iniciar el panel. Quitar una lista conserva su entidad y sus productos originales. Si quitas la principal, pasa a ser principal la primera restante; si quitas todas, puedes volver a añadir una desde Ajustes.

La selección de listas y la principal se guardan en las opciones de la integración en Home Assistant, se comparten entre dispositivos y se sincronizan en los paneles abiertos. Las instalaciones anteriores conservan las listas que tenían disponibles al actualizar. Un administrador puede modificar estos ajustes; el resto de usuarios pueden consultar y utilizar las listas según los permisos de Home Assistant. **Configurar** en la integración también permite cambiar la principal sin perder las listas añadidas. Cambiar de lista desde el popup solo cambia la selección de esa sesión.

## Lectores de códigos y NFC

Los códigos de producto desconocidos se consultan en [Open Food Facts](https://world.openfoodfacts.org/), desde Home Assistant y en segundo plano. Solo se envían códigos numéricos GTIN de 8, 12, 13 o 14 cifras con dígito de control válido; los identificadores NFC, los QR con texto o URL y los códigos ya asociados no se consultan. No se necesita una clave API.

En **Catálogo → Sugerencias → Productos escaneados** se muestran el nombre encontrado (priorizando el nombre común en español) y la atribución a Open Food Facts (datos bajo ODbL), cuando estén disponibles. El botón **+** rellena una ficha nueva con el nombre y una nota de procedencia. Las coincidencias de nombre con el catálogo son aproximadas: el botón de cuadrícula permite elegir un producto y revisar su ficha antes de guardar el código. No se crean productos, se modifican fichas ni se asocian códigos automáticamente; los datos externos tampoco sustituyen los de un producto existente.

La caché local persiste entre reinicios: resultados encontrados durante 30 días, sin resultado durante un día y errores durante cinco minutos. Las consultas se serializan con una separación mínima de 4,1 segundos y espera adicional si el servicio limita las peticiones. Los fallos de conexión no bloquean los lectores ni la identificación manual. Al reiniciar o volver a escanear se renuevan resultados caducados; las respuestas guardadas se limitan a 500 códigos. No se descargan imágenes ni se consultan precios.

El apartado **Lectores** (`mdi:barcode-scan`) permite añadir, editar, desactivar o quitar lectores. Cada lector tiene un nombre, tipo (barras/QR o NFC), lista de destino y protección antirrepetición; la lista principal y 60 segundos son los valores predeterminados. Configurar lectores requiere una cuenta administradora. Quitar un lector no elimina su entidad ni los productos del catálogo.

Puedes utilizar el estado de cualquier entidad existente, como `sensor.lector_cb_codigo_leido`, o indicar el atributo que contiene el código. Para lectores que generan eventos `tag_scanned`, elige NFC, esa fuente y el `device_id` del dispositivo. Los identificadores se tratan como texto, conservando ceros iniciales; los QR se usan como identificadores literales, sin abrir sus enlaces ni consultar APIs. Los identificadores NFC hexadecimales admiten diferencias de mayúsculas y separadores `:` o `-`.

En la ficha del producto puedes añadir un código principal, hasta 50 códigos adicionales de barras/QR y hasta 50 identificadores NFC, uno por línea. Un mismo código no puede corresponder a dos productos del mismo tipo. Para cada lector puedes elegir **Sin acción**, **Añadir a la lista de la compra**, **Quitar una unidad al stock** o **Añadir una unidad al stock**. Las acciones de stock se guardan para una fase posterior y, por ahora, solo informan de que el inventario está pendiente de implementar.

Las lecturas se procesan en Home Assistant aunque el panel esté cerrado. El intervalo antirrepetición se aplica a cada pareja lector/producto y también al código leído, se guarda para sobrevivir a recargas y no impide leer otros productos. No se ejecutan lecturas antiguas al arrancar ni cambios de atributos ajenos al código. Para repetir exactamente el mismo código tras el intervalo, la entidad debe generar una nueva lectura/evento; conservar su valor sin emitir nada no es una nueva lectura.

Una lectura desconocida aparece en **Catálogo → Sugerencias**, donde puedes abrir la ficha de un producto nuevo o seleccionar uno existente para asociar el código. El formulario permite completar los datos y elegir las acciones de sus lectores antes de guardar. Asociar una lectura pasada no ejecuta su acción automáticamente. También puedes descartar un código desconocido de forma persistente.

Al añadir a una lista se comprueba si el producto ya está pendiente, comparando el nombre sin diferencias de mayúsculas o espacios. En ese caso se mantiene una sola entrada. Si está comprado, se recupera el mismo elemento cuando el proveedor admite actualizarlo. Una lista explícita que se haya quitado de Ajustes o que esté indisponible produce un error en el registro de Home Assistant; no se sustituye silenciosamente por otra. El apartado Lectores muestra el icono del tipo, el nombre, la entidad o dispositivo y el tiempo desde el último uso registrado durante la ejecución. Cada tarjeta permite activar o desactivar el lector con un interruptor. Tras un error puedes efectuar una nueva lectura una vez transcurrido el intervalo.

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
