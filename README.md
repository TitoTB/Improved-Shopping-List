# Improved Shopping List

<img src="custom_components/improved_shopping_list/brand/icon.png" alt="Improved Shopping List" width="96">

Una interfaz propia para gestionar las listas de la compra que ya tienes integradas en Home Assistant.

Versión actual: **0.27.0**. Interfaz en español, pensada para móvil y ordenador. Requiere **Home Assistant Core 2026.10 o posterior**. La referencia de desarrollo es Core 2026.10.2.

Vinculaciones con Mercadona, Carrefour, Alcampo, Consum, La Sirena, Eroski y DIA, y consultas
directas desde Home Assistant. Se ha retirado el feed
de precios de GitHub y la dependencia de Aguacatec.

En Información adicional se elige una tienda y se añade el enlace o referencia del
artículo. Sus EAN se conservan como metadatos de tienda; los códigos configurados para
los lectores no se reasignan automáticamente. El precio manual sigue siendo independiente.

La actualización automática se configura desde el icono del reloj en Ajustes → Tiendas.
La primera hora se asigna aleatoriamente y se guarda, en la zona horaria de Home Assistant;
las horas ya elegidas se conservan. La frecuencia mínima es un día y puede ampliarse
hasta 3650 días. Tiendas y diccionario comunitario respetan el periodo configurado.
Al desactivar la función se detienen las consultas de precios y se ocultan los importes,
conservando la caché local para una posible reactivación. Solo entra en la cola lo pendiente en las listas
configuradas, comparando nombres sin diferencias de acentos o mayúsculas. Se deduplican
referencias compartidas por varias listas y se dejan al menos cinco minutos entre todas
las peticiones, incluidas redirecciones. La cola y la reserva de peticiones persisten al
reiniciar. Si Home Assistant se inicia durante la hora siguiente a la programada recupera
esa ejecución; una cola ya iniciada puede continuar después de la madrugada.

Las fichas y los popups muestran exclusivamente precios guardados. Actualizar vista no
consulta las tiendas. El icono Actualizar ahora de Ajustes → Tiendas abre un popup con el progreso e inicia una revisión manual
de las referencias vinculadas pendientes en las listas de todas las tiendas activas, incluso si ya se revisaron hoy.
Respeta los cinco minutos entre peticiones y las pausas indicadas por el servidor, evita
duplicar una revisión en curso y registra los resultados como manuales en Ajustes → Logs → Tiendas.
Se conserva el último precio conocido para todo el catálogo aunque
el producto se compre, salga de la lista o falle una consulta posterior. Un HTTP 404 se
registra como referencia no disponible y un 403/429 pausa esa tienda el resto del día;
las demás pueden continuar. Los precios indican fecha y región cuando corresponde.

Alcampo utiliza la consulta JSON del flujo n8n con una región fija de referencia.
Mercadona consulta
su API por referencia y almacén. Carrefour utiliza la respuesta JSON del endpoint interno
`/cloud-api/pdp-food-analytics/v1/impressions`, con la referencia y la cabecera `sale_point`,
sin cookies ni identificadores de sesión para sus precios. Utiliza el centro fijo
`005704`. Los precios quedan separados por centro.
La respuesta confirma la referencia antes de guardar el precio; el EAN, cuando existe,
se conserva como metadato y no modifica los códigos del lector.

La consulta JSON de Carrefour ha devuelto HTTP 200 y 2,69 EUR para la referencia 491998
desde el entorno de desarrollo, tanto con enlace completo como con ID. Su ficha HTML
sigue devolviendo 403 y ya no se utiliza para obtener precios. Alcampo sigue sujeto al
403 observado. El acceso depende de cada tienda y debe comprobarse desde cada Home Assistant;
los errores se muestran en Ajustes → Logs → Tiendas y no borran precios. Los logs distinguen una
actualización puesta en cola de una petición de precio que ya ha comenzado.

## Qué puedes hacer

Stock incluye las vistas **Stock** y **Compras**, con un botón para subir tickets
PDF electrónicos de Carrefour (hasta 2 MB y 10 páginas). El documento se lee localmente;
los escaneos y otros formatos de tienda todavía no están disponibles. El popup guía
la revisión en tres pasos: **Vinculación**, **Stock** y **Precios**. Primero permite
asociar cada línea al catálogo desde un popup con buscador, abrir la ficha completa para crear un producto o ignorarla. Las filas muestran el nombre del ticket y tres botones: vincular (azul), crear (verde) e ignorar (X sin fondo que pasa a rojo al activarse y se puede desmarcar). En este paso no se muestran cantidades ni precios. Dos líneas del mismo ticket no pueden vincularse al mismo producto;
hay que liberar la asociación anterior antes de reutilizarlo. La similitud de nombres
solo propone correspondencias. Al continuar se guardan las vinculaciones localmente,
independientemente del stock y sin compartirlas con el diccionario comunitario.
**Guardar vinculaciones y cerrar** termina aquí, sin importar la compra ni modificar cantidades
o precios; se puede volver a subir el ticket más adelante.

En Vinculación, las líneas sin asociar aparecen primero y los productos vinculados se reúnen al final en un bloque plegado que permite desplegarlos y editarlos. No se muestra el subtítulo «Vincular productos».

En Stock vienen seleccionados los productos identificados que ya están en el inventario, dentro de otro bloque plegado al final. Las demás líneas aparecen primero, con el icono de stock desmarcado. Cada fila reúne el nombre del ticket y del catálogo, cantidad, unidades y el icono de stock, que se vuelve naranja al seleccionar la reposición. En este paso se omiten el título, la ayuda y los precios de cada línea.
Los demás se pueden incorporar, confirmando cantidades y unidades antes de sumarlas.
Las conversiones confirmadas se recuerdan para próximos tickets. **Volver a vinculación** conserva la revisión; **Añadir stock y cerrar** confirma la compra y las cantidades elegidas sin actualizar precios. Los botones para guardar y cerrar son verdes y **Continuar** es azul. En Precios se eligen
individualmente los importes que se quieren guardar, con opción de seleccionar todos,
y se muestra un resumen antes de confirmar la compra. Las cantidades y el historial
no cambian hasta esta confirmación final; las vinculaciones del primer paso se conservan
aunque se cierre la revisión después.

Compras conserva fecha, tienda, importe, descuentos generales y detalle de
los tickets confirmados. Subir o cerrar la revisión no modifica el stock. Al confirmar,
el historial y las cantidades se guardan juntos y se detectan tickets duplicados. Si ya
se registró una reposición al marcar el producto como comprado, se puede seleccionarla
para aplicar únicamente la diferencia, conservando consumos posteriores. Si el ticket
se importa antes, cubre la entrada pendiente correspondiente para que su posterior
marcado como comprado no vuelva a sumar la reposición predeterminada.

La revisión permite guardar el precio por unidad/envase del ticket como último precio
conocido de esa tienda, sin sustituir observaciones más recientes ni repartir cupones
generales entre artículos. No se convierte el precio de un envase a precio por gramo
por el hecho de llevar el stock en gramos. Los tickets, datos de pago y fidelización
no se envían al diccionario comunitario; el PDF original no se conserva y del documento
solo se guardan las líneas de compra y metadatos necesarios. El historial está disponible
para administradores de Home Assistant.

- Seleccionar cualquier entidad `todo.*` disponible para tu usuario, incluida Bring!, Shopping List u otros proveedores.
- Consultar productos pendientes y comprados.
- Pulsar el importe estimado para abrir un ticket por tienda con los precios guardados. Se muestran hasta cuatro tiendas activas, priorizando las que tienen más productos con precio y, en caso de empate, el menor importe conocido. Cada una muestra logo, importe y cobertura. Los productos sin precio se agrupan en un bloque plegado y cuentan como 0; los totales pueden incluir distintas cestas parciales. El badge del número de productos devuelve a la vista habitual.
- Añadir productos, marcarlos como comprados y volver a ponerlos por comprar.
- Recibir cambios del proveedor mediante la API nativa de listas de Home Assistant.
- Añadir o quitar entidades `todo` desde Ajustes y marcar una lista como principal.
- Crear y editar productos en un catálogo local compartido entre los usuarios de Home Assistant, con vistas Productos, Categorías, Recetas, Sugerencias y Nuevos.
- Asignar categorías, códigos de barras, etiquetas NFC, precios orientativos e imágenes.
- Buscar, filtrar y añadir productos del catálogo a la lista seleccionada.
- Agrupar el catálogo por categoría o Sugerencias. Al agrupar por Sugerencias solo se muestran productos asociados a un grupo de sugerencias activo.

Cada lista conserva sus datos en su integración original. Las operaciones disponibles dependen de lo que admita ese proveedor. Por ejemplo, una lista de solo lectura se puede consultar, pero sus controles de edición aparecen desactivados. La frecuencia con la que Bring! u otro proveedor recibe cambios de su nube depende de su propia integración.

El panel se comunica con Home Assistant usando la sesión del usuario y las APIs nativas. La gestión local no necesita tokens adicionales ni cuentas nuevas; compartir datos con la comunidad requiere autorizar voluntariamente una cuenta de GitHub. Las funciones de consulta de productos e iconos utilizan Open Food Facts e Iconify respectivamente; la gestión de listas y del catálogo funciona sin esos servicios. El JavaScript se sirve localmente y no utiliza un CDN.

## Requisitos y dependencias

**No necesitas instalar otras tarjetas de HACS ni complementos de Home Assistant.** El panel es propio y sus archivos JavaScript y CSS se sirven desde Home Assistant. No requiere Mushroom, button-card, card-mod, browser_mod ni añadir recursos al dashboard.

### Requisitos de instalación

| Dependencia | Para qué se utiliza | Cómo se obtiene |
| --- | --- | --- |
| Home Assistant Core **2026.10.0 o posterior** | Ejecutar la integración y su interfaz. La versión de referencia de las pruebas es 2026.10.2. | Tu instalación de Home Assistant; compatible con Home Assistant OS. |
| Una integración que proporcione entidades `todo.*` | Gestionar las listas de la compra. Puede ser Shopping List de Home Assistant, Bring! u otro proveedor compatible. Las operaciones disponibles dependen de sus capacidades. | Configura el proveedor que prefieras en Home Assistant. Bring! no es obligatorio. |
| `frontend`, `http`, `panel_custom` y `todo` | Componentes nativos de Home Assistant que utiliza el panel y la gestión de listas. `panel_custom` no es una tarjeta de HACS. | Home Assistant los gestiona automáticamente según `manifest.json`. |
| `pypdf==6.21.2` | Extraer el texto de los tickets PDF. Es la única librería Python externa declarada por esta integración. | Home Assistant la instala automáticamente al cargar la integración, aunque no utilices tickets. No necesitas ejecutar `pip` ni instalar un complemento. |

HACS es el método de instalación y actualización descrito abajo. No se necesita ningún otro repositorio personalizado para usar la interfaz. La instalación inicial de la librería Python requiere acceso a su servidor de paquetes.

### Funciones opcionales y servicios externos

| Función | Dependencia opcional | Qué necesita el usuario |
| --- | --- | --- |
| Identificar códigos de barras y obtener Nutri-Score | Open Food Facts | Acceso a Internet; no requiere clave de API. |
| Sugerir iconos y traducir nombres para buscarlos | Iconify y MyMemory | Acceso a Internet; no requiere configurar claves de API. Las traducciones se guardan para reutilizarlas. |
| Consultar el diccionario comunitario | Archivos públicos del repositorio en GitHub | Acceso a Internet; la consulta pública no requiere una cuenta. |
| Compartir datos con la comunidad | GitHub y la GitHub App de Improved Shopping List | Activar la opción y autorizar una cuenta de GitHub. La autorización es independiente de HACS: no se reutilizan sus credenciales. |
| Actualizar precios | Webs y endpoints de las tiendas habilitadas | Acceso a Internet y vinculaciones de productos. No requiere n8n, Google Sheets, credenciales de Awin ni otro proyecto de Aguacatec. El acceso puede fallar por cambios o bloqueos de la tienda; se conserva el último precio conocido. |
| Mostrar imágenes remotas y algunos logos de tiendas | El servidor de cada imagen | El navegador necesita poder acceder a la URL. Las imágenes locales y los iconos descargados no dependen de ese servidor para mostrarse. Flaticon no es una API necesaria para la integración. |
| Usar lectores de códigos o NFC | Un dispositivo ya integrado que exponga la entidad de lectura compatible | Configurar su entidad en Ajustes → Lectores. ESPHome es una opción para el dispositivo, no un requisito de Improved Shopping List. |
| Descontar stock por consumo registrado | Una entidad de Home Assistant que represente el uso | Seleccionar la entidad y el estado correspondiente. |
| Enviar notificaciones | Un destino de notificación configurado en Home Assistant | Seleccionar uno o varios destinos en Ajustes → Notificaciones. Para avisos al móvil puedes usar la aplicación Companion; también se admiten otros proveedores de notificación compatibles. |
| Importar tickets PDF | La librería `pypdf` indicada arriba | Actualmente admite tickets electrónicos de Carrefour con texto. No necesita OCR, Tesseract ni un servicio externo; los PDF escaneados no están soportados. |

El catálogo, categorías, recetas, sugerencias manuales y stock se guardan en Home Assistant. No necesitan las APIs de productos, iconos o precios para su gestión local. La disponibilidad de las listas depende además de su proveedor: una lista local puede funcionar sin Internet y un proveedor en la nube puede necesitar conexión.

### Dependencias solo de desarrollo

Node.js, npm, Playwright y `@webcomponents/scoped-custom-element-registry` se utilizan para las comprobaciones y pruebas del repositorio. Las dependencias de `requirements_test.txt`, Hassfest y la validación de HACS también son herramientas de desarrollo. **El usuario no debe instalarlas en Home Assistant.** Los iconos de Font Awesome de los botones están incluidos como SVG; no requieren un kit, fuente o script externo.

## Instalación con HACS

Este repositorio se instala como repositorio personalizado; no está incluido en el catálogo predeterminado de HACS.

1. En HACS, abre el menú de los tres puntos → **Repositorios personalizados**.
2. Añade `https://github.com/TitoTB/Improved-Shopping-List` con tipo **Integración**.
3. Busca **Improved Shopping List**, descarga la última versión y reinicia Home Assistant.
4. Abre **Ajustes → Dispositivos y servicios → Añadir integración**.
5. Busca **Improved Shopping List** y selecciona tu lista de la compra predeterminada.
6. Abre **Improved Shopping List** desde la barra lateral.

Si no tienes ninguna entidad `todo.*`, configura antes Bring!, Shopping List u otra integración que proporcione listas. No necesitas añadir YAML ni recursos de dashboard manualmente. Si solo hay una lista de compra configurada, el botón de seleccionar lista se oculta tanto en Lista como en Stock; las listas pasarela no cuentan. Con varias listas configuradas vuelve a mostrarse automáticamente.

Si el panel no aparece después de instalar, recarga la página o cierra y abre la aplicación de Home Assistant. Tras actualizar, una recarga completa también permite descartar una versión antigua del JavaScript.

## Actualizaciones

Las versiones se publican en GitHub. HACS permite detectar y descargar las nuevas versiones. Por defecto, decide tú cuándo instalarlas y reiniciar Home Assistant; esta integración no activa instalaciones automáticas.

Para publicar una versión, los mantenedores actualizan la versión en `manifest.json`, `const.py`, `package.json`, la referencia de módulo y el texto de versión en `frontend/panel.js`, el lockfile y `CHANGELOG.md`. Después suben una etiqueta `vX.Y.Z`. GitHub Actions ejecuta las comprobaciones y publica la release si pasan. Los cambios en la rama principal sin una nueva versión no se publican automáticamente como una actualización estable.

## Alcance de esta primera versión

El catálogo se guarda en el almacenamiento de Home Assistant, no en el navegador. Todos los usuarios autenticados que utilicen el panel comparten el mismo catálogo. Las listas siguen perteneciendo a sus proveedores originales; se añade el nombre del producto a la lista, y las propiedades adicionales permanecen en su ficha del catálogo.

Solo es obligatorio el nombre. Las categorías se crean, editan y eliminan desde la vista Categorías, donde puedes elegir su icono MDI y su color. Renombrar una categoría actualiza sus productos; eliminarla los conserva sin categoría. Las categorías introducidas en instalaciones anteriores se recuperan automáticamente con un icono y un color predeterminados. La ficha se divide en Características (nombre, sugerencias de iconos, URL de imagen, categoría y etiquetas), Información adicional (unidades, vinculaciones con tiendas, precios guardados y Nutri-Score) y Automatización (códigos de barras/QR, etiquetas NFC, acciones de lectores y recurrencia). Guardar conserva los datos de todas las vistas. Etiquetas vuelve a estar disponible en Características para indicar marcas, tiendas y otros términos de búsqueda. Admite hasta 20 etiquetas de 40 caracteres, separadas por comas, conservando las etiquetas de instalaciones anteriores. Las búsquedas del catálogo y las sugerencias predictivas de Lista encuentran estas etiquetas sin distinguir tildes ni mayúsculas. Icono del producto y Notas siguen fuera del formulario; sus valores anteriores se conservan al editar.

Las tarjetas muestran primero la imagen o el icono del producto y debajo su nombre, centrados. Si no hay imagen se utiliza el icono propio del producto; si tampoco tiene icono propio, se utiliza el de su categoría y, cuando no tiene categoría, `mdi:shopping`. Este criterio también se aplica en Lista y en sus sugerencias de búsqueda. En Lista, la categoría se representa con un icono blanco sobre un círculo de su color en la esquina superior derecha, sin borde y con sombra. En Catálogo → Productos, las tarjetas son cuadradas: pulsar su superficie añade el producto a la lista seleccionada, también con Enter o espacio. Al pulsar una tarjeta no se muestra un mensaje de confirmación; el degradado indica que el producto está pendiente. Las tarjetas de productos ya pendientes no vuelven a añadirlos. Antes de añadir se consulta el contenido actual de la lista, comparando sin tildes ni mayúsculas y agrupando pulsaciones simultáneas del mismo producto en el panel. Si ya estaba comprado, se recupera su entrada por identificador; si el proveedor no permite recuperarla, se muestra el error sin crear un duplicado. Los dos controles circulares de la esquina permiten editar (fondo naranja/amarillo) y eliminar (fondo negro), sin activar la acción de añadir. El borrado pide confirmación, elimina la ficha y sus códigos del catálogo y conserva los elementos de las listas. El selector de categorías permite filtrar los productos. El campo **URL Imagen/Icono**, situado debajo de las sugerencias, permite introducir libremente una URL http/https o una ruta local como `/local/cacao.png`. El navegador carga las imágenes manuales desde la ubicación indicada; no se descargan al servidor ni hay subida de archivos.

La ficha del producto muestra automáticamente hasta seis iconos sugeridos en una misma fila, sin buscador ni botón de más resultados. Las propuestas del diccionario comunitario tienen prioridad y, si faltan alternativas, se completan con Iconify. Se actualizan al abrir la ficha y al cambiar el nombre del producto, con una pausa de medio segundo para agrupar las pulsaciones. Elegir un icono rellena la URL Imagen/Icono y conserva su autor y licencia. La URL también puede indicarse manualmente. Las respuestas de búsquedas o descargas anteriores no sobrescriben una ficha distinta ni una URL manual.

La vista **Catálogo → Recetas** permite crear, editar y eliminar recetas con ingredientes del catálogo, cantidades concretas y las unidades propias de cada producto. El botón **+** abre su ficha; el icono de editar de cada bloque permite modificarla. Pulsar un bloque añade los ingredientes a la lista seleccionada: si ya están pendientes se suma la cantidad de la receta sobre su entrada, y si son nuevos o se recuperan de comprados se utiliza exactamente la cantidad indicada en la receta. No se crean duplicados ni se modifica el stock al añadir la receta; al marcar la compra se mantiene el comportamiento habitual del stock. Las recetas usan un degradado verde configurable en **Ajustes → Personalización**. Pueden asociarse a categorías manuales de sugerencias y a meses del calendario de temporada. Las fichas y asociaciones permanecen locales en Home Assistant. Si cambia la unidad de un ingrediente, hay que revisar la receta; no se convierten gramos y kilogramos automáticamente. Un error parcial al añadir ingredientes indica los ya procesados para evitar repetir la operación sin revisar la lista.

Desde el botón **+** de **Catálogo → Sugerencias** puedes crear categorías de sugerencias con nombre, icono MDI y color, y elegir cualquier producto del catálogo mediante una lista con buscador. Son asociaciones manuales: sus productos siempre están disponibles como sugerencias. Un producto puede pertenecer a varias de estas categorías sin cambiar su categoría habitual. Pulsa el bloque de una categoría de sugerencias para editar sus datos o productos; su botón Eliminar categoría pide confirmación y conserva los productos y las listas. Las asociaciones se guardan en Home Assistant, se conservan al renombrar productos y se retiran al eliminar la ficha del catálogo. Se mantienen separadas del diccionario comunitario.

La vista **Nuevos** (`mdi:creation`) muestra los nombres de productos de la lista seleccionada que aún no están en el catálogo, incluidos los elementos comprados que siguen en la lista. Añadir al catálogo abre el formulario con el nombre ya rellenado, para completar categoría, etiquetas y otros datos antes de guardar. Si corriges el nombre en ese formulario, al guardar se renombra el elemento original de la lista, conservando su estado y demás datos; también se actualizan las variantes equivalentes de esa sugerencia en la misma lista. La lista y los identificadores de origen se conservan aunque cambies de lista mientras está abierta la ficha. Si el proveedor no permite renombrar o falla la operación, la ficha informa del error: el producto queda guardado en el catálogo y puedes reintentar sin crear otra ficha. Cancelar conserva la sugerencia sin crear el producto. También puedes descartar sugerencias sin modificar la lista. Las sugerencias, las coincidencias con el catálogo y los descartes comparan los nombres ignorando tildes, mayúsculas, caracteres Unicode equivalentes y espacios sobrantes. Así, «Seitan», «Seitán» y «SEITÁN» no producen sugerencias distintas; los nombres guardados conservan su escritura original. Los descartes se guardan en Home Assistant, se comparten entre sesiones y listas y se conservan tras reiniciar. Para cambiar la lista de origen, utiliza el selector del apartado Lista.

Los precios guardados por tienda pueden proceder de las consultas configuradas o de tickets PDF confirmados, con su fecha de actualización. Las consultas externas son opcionales y la lectura del PDF se realiza localmente con `pypdf`. El código de barras se guarda como texto para conservar sus ceros iniciales. Los campos Marca y Formato se han retirado; las instalaciones anteriores eliminan esos campos al cargar el catálogo, conservando los productos y sus códigos.

Las ediciones simultáneas se detectan: si otra sesión ha cambiado una ficha, se pide volver a abrirla antes de guardar. No se borra el catálogo al cambiar de lista ni al recargar la integración. Se conserva también al retirar la integración para permitir reinstalarla; los productos de las listas originales tampoco se eliminan.

El apartado **Ajustes** (`mdi:cog`) permite añadir cualquier entidad `todo` de Home Assistant, quitar listas de esta interfaz y marcar una como principal. El popup de Lista muestra únicamente las listas añadidas; la principal se abre al iniciar el panel. Quitar una lista conserva su entidad y sus productos originales. Si quitas la principal, pasa a ser principal la primera restante; si quitas todas, puedes volver a añadir una desde Ajustes.

La selección de listas y la principal se guardan en las opciones de la integración en Home Assistant, se comparten entre dispositivos y se sincronizan en los paneles abiertos. Las instalaciones anteriores conservan las listas que tenían disponibles al actualizar. Un administrador puede modificar estos ajustes; el resto de usuarios pueden consultar y utilizar las listas según los permisos de Home Assistant. **Configurar** en la integración también permite cambiar la principal sin perder las listas añadidas. Cambiar de lista desde el popup solo cambia la selección de esa sesión.

## Lectores de códigos y NFC

Los códigos de producto desconocidos se consultan en [Open Food Facts](https://world.openfoodfacts.org/), desde Home Assistant y en segundo plano. Solo se envían códigos numéricos GTIN de 8, 12, 13 o 14 cifras con dígito de control válido; los identificadores NFC, los QR con texto o URL y los códigos ya asociados no se consultan. No se necesita una clave API.

En **Catálogo → Nuevos → Productos escaneados** se muestran el nombre encontrado (priorizando el nombre común en español) y la atribución a Open Food Facts (datos bajo ODbL), cuando estén disponibles. El botón **+** rellena una ficha nueva con el nombre y una nota de procedencia. Las coincidencias de nombre con el catálogo son aproximadas: el botón de cuadrícula permite elegir un producto y revisar su ficha antes de guardar el código. No se crean productos, se modifican fichas ni se asocian códigos automáticamente; los datos externos tampoco sustituyen los de un producto existente.

La caché local persiste entre reinicios: resultados encontrados durante 30 días, sin resultado durante un día y errores durante cinco minutos. Las consultas se serializan con una separación mínima de 4,1 segundos y espera adicional si el servicio limita las peticiones. Los fallos de conexión no bloquean los lectores ni la identificación manual. Al reiniciar o volver a escanear se renuevan resultados caducados; las respuestas guardadas se limitan a 500 códigos. No se descargan imágenes ni se consultan precios.

La vista **Ajustes → Lectores** (`mdi:barcode-scan`) permite añadir, editar, desactivar o quitar lectores. Cada lector tiene un nombre, tipo (barras/QR o NFC), lista de destino, acción por defecto y protección antirrepetición; la lista principal y 60 segundos son los valores predeterminados. El interruptor de la tarjeta controla si está activo; editar su ficha conserva ese estado. Configurar lectores requiere una cuenta administradora. Quitar un lector no elimina su entidad ni los productos del catálogo.

El botón azul con `mdi:eye-outline`, a la izquierda de Editar, abre la información de la entidad en el popup nativo de Home Assistant, cuyo estado se actualiza al recibir lecturas. Para los lectores NFC que utilizan eventos y no tienen entidad, abre un popup con el último código, producto identificado, resultado y hora, actualizado en directo. Consultar esta información no requiere ser administrador ni ejecuta acciones del lector.

Puedes utilizar el estado de cualquier entidad existente, como `sensor.lector_cb_codigo_leido`, o indicar el atributo que contiene el código. Para lectores que generan eventos `tag_scanned`, elige NFC, esa fuente y el `device_id` del dispositivo. Los identificadores se tratan como texto, conservando ceros iniciales; los QR se usan como identificadores literales, sin abrir sus enlaces ni consultar APIs. Los identificadores NFC hexadecimales admiten diferencias de mayúsculas y separadores `:` o `-`.

En la ficha del producto, **Automatización** reúne los códigos en dos apartados: **Códigos de barras/QR** y **Etiquetas NFC**. Selecciona un lector activo del tipo correspondiente y pulsa **Escanear**. Cada lectura aparece en una línea, sin campos de escritura manual; puedes quitarla individualmente y capturar hasta 50 códigos de cada tipo. Los códigos ya existentes se conservan y las nuevas asociaciones se aplican al guardar el producto. Un mismo código no puede corresponder a dos productos del mismo tipo.

La captura dura hasta 60 segundos y puede detenerse manualmente. Se libera al cerrar la ficha, cambiar de apartado, desconectarse, modificar el lector o detener la integración. Durante la captura, ese lector no ejecuta acciones, no genera sugerencias de códigos desconocidos y no actualiza el periodo antirrepetición. Solo una ficha puede capturarlo a la vez; se requiere una cuenta administradora.

Para cada lector puedes elegir **Usar acción por defecto del lector**, **Sin acción**, **Añadir a la lista de la compra**, **Quitar una unidad al stock** o **Añadir una unidad al stock**. Si no hay una acción específica, se aplica la del lector al reconocer el producto; cambiarla afecta también a los productos que la heredan. Una acción específica tiene prioridad, incluido **Sin acción**. Las selecciones anteriores se conservan y los lectores existentes empiezan sin acción por defecto. Las acciones de stock suman o restan una unidad de la despensa común, conservan la protección antirrepetición y no modifican listas de compra.

Las lecturas se procesan en Home Assistant aunque el panel esté cerrado. El intervalo antirrepetición se aplica a cada pareja lector/producto y también al código leído, se guarda para sobrevivir a recargas y no impide leer otros productos. No se ejecutan lecturas antiguas al arrancar ni cambios de atributos ajenos al código. Para repetir exactamente el mismo código tras el intervalo, la entidad debe generar una nueva lectura/evento; conservar su valor sin emitir nada no es una nueva lectura.

Una lectura desconocida aparece en **Catálogo → Nuevos**, donde puedes abrir la ficha de un producto nuevo o seleccionar uno existente para asociar el código. El formulario permite completar los datos y elegir las acciones de sus lectores antes de guardar. Asociar una lectura pasada no ejecuta su acción automáticamente. También puedes descartar un código desconocido de forma persistente.

El botón azul de vincular abre un popup con buscador predictivo de productos del catálogo. Filtra mientras escribes sin distinguir tildes ni mayúsculas y muestra primero las posibles coincidencias sugeridas por Open Food Facts. Puedes elegir con un clic o con las flechas y Enter; Escape cierra las propuestas. Elegir un producto no guarda cambios: pulsa **Asignar** para vincular el código, o **Cancelar** para salir sin guardar. El resto de los datos y las acciones de lectores se conservan y no se ejecuta la lectura pasada. El texto y el cursor se conservan si llegan nuevas lecturas mientras buscas.

Al añadir a una lista se comprueba si el producto ya está pendiente, comparando el nombre sin diferencias de tildes, mayúsculas o espacios. En ese caso se mantiene una sola entrada. Si está comprado, se recupera el mismo elemento cuando el proveedor admite actualizarlo. Una lista explícita que se haya quitado de Ajustes o que esté indisponible produce un error en el registro de Home Assistant; no se sustituye silenciosamente por otra. La vista Ajustes → Lectores muestra el icono del tipo, el nombre, la entidad o dispositivo y el tiempo desde el último uso registrado durante la ejecución. Cada tarjeta permite activar o desactivar el lector con un interruptor. Tras un error puedes efectuar una nueva lectura una vez transcurrido el intervalo.

Eliminar la integración retira el panel y desactiva sus comandos de catálogo.

## Historial de actividad

La vista **Logs** de **Ajustes** (`mdi:format-list-group`) conserva las últimas 1.000 entradas en Home Assistant, de más reciente a más antigua. Incluye altas y bajas de productos en las listas configuradas, compras, recuperación de productos como pendientes, cambios de nombre y otros datos de la lista, creación/edición/borrado de productos y categorías, cambios de lectores y ajustes, y el resultado de las lecturas (incluidos códigos desconocidos, errores y lecturas repetidas ignoradas). Muestra fecha y hora, producto, lista y lector cuando están disponibles. Los cambios del catálogo indican los campos modificados y el nombre anterior cuando corresponda.

El registro funciona sin tener la interfaz abierta. Las listas se observan con las suscripciones de elementos de Home Assistant, por lo que también se detectan cambios que no alteran la cantidad de productos. Las llamadas a servicios se utilizan para identificar el origen, pero no se registran como éxito hasta que cambia el contenido real. Los orígenes pueden ser Usuario / API, Automático · Home Assistant, Lector, Integración, Home Assistant sin origen identificado o Proveedor externo con origen desconocido. Las llamadas con credenciales de usuario se muestran como Usuario / API, pues también pueden proceder de una aplicación o sistema externo. La identificación automática depende del contexto que conserve Home Assistant; los cambios realizados en la aplicación del proveedor no siempre permiten conocer quién los hizo ni si fueron automáticos.

El historial permite buscar por producto, lista, categoría, lector o código y filtrar por actividad y origen. Se muestran inicialmente 100 entradas y **Ver más** carga las siguientes. Las entradas nuevas llegan en directo mientras la vista está abierta. Los datos se guardan en `.storage/improved_shopping_list.activity`, con escrituras agrupadas durante un segundo y guardado al descargar la integración. Se conservan después de reiniciar. No se reconstruye actividad anterior a la instalación ni ocurrida mientras Home Assistant estaba apagado. La carga inicial de una lista y su incorporación a Ajustes establecen una referencia y no generan altas ficticias de los productos que ya contenía. El historial es común a las listas de la integración.

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

### Diccionario comunitario y aportaciones automáticas

En **Ajustes → Comunidad**, activa **Compartir mis datos de productos** para iniciar la autorización con la GitHub App. GitHub se abre automáticamente en otra pestaña y Home Assistant muestra el código y las instrucciones en un popup. Introduce el código y confirma la autorización en GitHub; esperar sin autorizar no completa el proceso. Si el navegador bloquea la apertura, utiliza el enlace del popup. Puedes cerrar y reabrir las instrucciones con **Ver autorización**, sin reiniciar el código. El popup se cierra al confirmar GitHub. Al completarla se solicita el envío inmediato de los datos disponibles, aunque haya una revisión de precios en curso, respetando el límite de un lote cada 24 horas y las pausas de reintento. Volver a marcar la casilla no reinicia ese límite. La integración guarda sus credenciales de forma privada y no utiliza las de HACS. Desmarcar la casilla detiene las aportaciones.

El diccionario público se consulta una vez al día, sin cuenta y sin actualizar la integración. Permite completar traducciones y vinculaciones confirmadas que falten, sugerir nombres e iconos y reutilizar precios por referencia exacta durante 24 horas, conservando la fecha original. No sobrescribe elecciones locales ni crea automáticamente productos del catálogo.

Con el consentimiento activado se aportan los datos permitidos de todo el catálogo: nombres, traducciones, EAN, vinculaciones con tiendas, Nutri-Score, precios e iconos admitidos. Las aportaciones son públicas y están asociadas a la cuenta de GitHub, con un lote por cuenta cada 24 horas. Se excluyen listas, stock, NFC, lectores, categorías personales, notas y automatizaciones.

GitHub Actions valida los datos automáticamente: consenso de tres cuentas independientes para los campos confirmados, comprobación de licencias de Iconify y control de variaciones de precios superiores al 50 %. Las preferencias de iconos se cuentan por separado. El mantenedor puede bloquear cuentas y recuperar una versión anterior del diccionario. Consulta [el funcionamiento y la política del catálogo comunitario](community/README.md).

### Nutri-Score del catálogo

**Ajustes → Nutri-Score** muestra una gráfica de barras con los colores A–E, el número de productos y su porcentaje sobre los productos del catálogo con Nutri-Score conocido. Se utilizan exclusivamente los datos guardados de Open Food Facts o del diccionario comunitario; abrir la gráfica no consulta esas fuentes ni actualiza precios. Los productos sin una letra válida no entran en el cálculo. Cada ficha cuenta una sola vez; si tiene varios códigos con Nutri-Score, se toma el primer código con resultado, empezando por su código principal. Al volver a abrir la vista se vuelve a leer la información local disponible. No requiere tarjetas HACS ni librerías gráficas adicionales.

Nutri-Score deja de ser un criterio de «Agrupar productos por» en Catálogo → Productos. Una selección antigua de ese criterio pasa a agrupar por categoría.

### Nutri-Score en la ficha

La vista **Información adicional** consulta Open Food Facts para los códigos de barras válidos de la ficha y muestra el Nutri-Score A–E cuando está disponible. Cada resultado indica el producto concreto, su código, la fecha de consulta y la fuente. Si una ficha genérica agrupa varios códigos, los resultados se presentan por separado. Las etiquetas NFC, los QR y los códigos con dígito de control incorrecto no se envían.

Se reutiliza la caché persistente de identificación (30 días para productos encontrados); los resultados sin calificación y los fallos no impiden guardar la ficha. Las consultas se limitan y agrupan por código, incluidas las variantes UPC/EAN equivalentes. No se calcula una nota propia ni se asigna una calificación genérica a todos los códigos del producto. Los distintivos se cargan desde los recursos oficiales publicados por Open Food Facts; la letra también se muestra como texto.


## Tiendas y vinculaciones

En **Ajustes → Tiendas** se habilitan Mercadona, Carrefour, Alcampo, Consum, La Sirena, Eroski y DIA, se elige la
favorita y se configura la hora de revisión. Cada tienda utiliza un centro fijo de
referencia. No se pide ni se utiliza el código postal del usuario, y activar una
tienda no realiza peticiones de descubrimiento de cobertura.
El badge de cada tienda muestra el número de productos vinculados y un carrito;
al pulsarlo se abre directamente el listado de precios guardados, incluso con la tienda desactivada.

Referencias utilizadas:

| Tienda | Código postal de referencia | Centro |
| --- | --- | --- |
| Alcampo | 28024 | Región `deb03a69-3104-4451-9ffa-3a55dc156d9f` |
| Carrefour | 28024 | `005704` |
| Consum | 46409 | Área `301D`, zona `301` |
| DIA | 28024 | Sesión de precios para `28024` |
| Eroski | 48001 | Eroski Deusto, centro `244` |
| La Sirena | 28024 | `lasirena259` |
| Mercadona | 28024 | Almacén `mad1` |

Los precios son orientativos y pueden diferir de los de tu zona. Las instalaciones
anteriores se migran conservando las tiendas activas, favorita y demás preferencias,
pero retirando los códigos postales y errores de cobertura anteriores. La migración
no inicia consultas ni elimina precios: las ofertas de otro centro siguen guardadas
con su ámbito original y no se presentan como precios del centro nuevo.
Se conservan las pausas y protecciones frente a rechazos del servidor. Una ubicación
fija evita el descubrimiento de cobertura, pero no garantiza evitar un HTTP 403 al
iniciar sesión anónima o consultar un producto. Puedes desactivar una tienda y seguir
consultando los precios guardados para su centro de referencia.

Cada revisión genera una sola entrada final en **Ajustes → Logs → Tiendas**,
con el resultado por tienda, precios actualizados, referencias sin resultado,
incidencias y peticiones realizadas. Los detalles técnicos y la información de
la revisión en curso se guardan entre reinicios; la barra sigue mostrando el
avance mientras se procesan las referencias. No se crean entradas por cada petición.

Consum consulta su ficha JSON con las cabeceras de zona seleccionadas. La Sirena
resuelve la referencia a su variante y consulta el precio de entrega para el centro
y código postal elegidos. Ambas consultas de La Sirena respetan los cinco minutos
entre peticiones; un producto puede necesitar dos peticiones. No se usa una cuenta,
cookies de usuario ni su carrito. Las respuestas ambiguas, sin disponibilidad o con
errores conservan el precio anterior. Los EAN recibidos son metadatos del precio:
no modifican automáticamente las asociaciones de los lectores.

Eroski utiliza el centro de recogida fijo Eroski Deusto, confirmado previamente
en su selector público.
La integración inicia su propia sesión anónima, aplica el centro y verifica que la
sesión conserva ese centro antes de aceptar un precio. No reserva una franja de
recogida ni utiliza tu cuenta o carrito. Las vinculaciones de Eroski requieren el
**enlace completo de la ficha**, ya que no se ha verificado una ruta por ID sola.
La primera consulta necesita preparar la sesión (cuatro peticiones, separadas por
cinco minutos); las siguientes reutilizan esa sesión mientras conserve el centro.
Los precios de cada centro permanecen separados. Los errores conservan el último
precio conocido.

DIA admite enlace o ID. Utiliza el código postal de referencia 28024;
la tienda asigna su centro automáticamente. La integración utiliza el cliente
estándar `urllib` de Python, con su identidad predeterminada, en el executor de
Home Assistant para evitar bloquear el bucle de eventos. En las pruebas, ese
cliente permite consultar la API pública donde `aiohttp` recibía HTTP 403. No usa
un navegador, cuenta, claves, cookies del usuario ni dependencias externas.
La primera revisión configura una sesión anónima para el código postal y después
consulta la referencia exacta; ambas peticiones respetan los cinco minutos de
pausa. Cada respuesta debe confirmar el mismo código postal. Las siguientes
consultas reutilizan esa sesión; los rechazos, respuestas ambiguas y productos
sin resultado conservan el precio anterior. No se aplican precios exclusivos del club.

En **Catálogo → Información adicional**, selecciona una tienda, pega su enlace
o ID y pulsa **+** o **Enter**. Cada vínculo muestra el logo y nombre de la tienda
junto al enlace, con un botón rojo para quitarlo antes de guardar el producto.
Los campos de precio orientativo y moneda ya no se muestran; se conservan los
precios manuales que estuvieran guardados. Solo se admiten fichas HTTPS de las tiendas registradas,
sin credenciales, puertos arbitrarios ni redirecciones a otras tiendas o productos.
No se exige EAN para consultar el precio de una referencia seleccionada por el usuario.

La cola diaria consulta solo productos pendientes y sus referencias vinculadas.
Abrir una ficha, abrir Productos en una tienda o pulsar **Actualizar vista** solo
lee la caché local. Los precios se mantienen separados del precio orientativo manual
y de los EAN utilizados por los lectores. Las asociaciones exactas de Mercadona
ya descubiertas y los últimos precios del antiguo feed se recuperan de sus copias
locales, sin volver a consultar GitHub ni depender de Aguacatec.

## Compras recurrentes

Al final de **Automatización** en la ficha de un producto, activa **Comprar cada X días** e indica entre 1 y 3650 días. Esta opción comparte la configuración con el modo **Perecedero** de Stock: cambiar los días o activar/desactivar la recurrencia en una ficha actualiza la otra. Si el producto todavía no está en Stock se crea con cantidad 0; las cantidades, unidades y preferencias existentes se conservan. Pasar a manual o consumo registrado desde Stock desactiva esta recurrencia en el catálogo.

Home Assistant comprueba los vencimientos cada minuto aunque el panel esté cerrado. Al vencer, pone el stock a cero y solicita reposición en la lista elegida en Stock, o en la principal si no se ha elegido otra. Si el producto ya está pendiente, no crea otra entrada. Si está comprado, recupera el mismo elemento por su identificador cuando el proveedor lo permite; si no existe, lo añade. Marcarlo como comprado suma la cantidad de reposición configurada y reinicia el plazo desde la compra. Editar otros datos o asociar un código conserva el vencimiento.

La programación y las ediciones pendientes de sincronizar se guardan en Home Assistant y sobreviven a reinicios. Un único temporizador de Stock gestiona cada producto; la programación anterior del catálogo no añade una segunda compra. Las recurrencias existentes se migran conservando su siguiente vencimiento cuando está disponible. Si un plazo venció con Home Assistant apagado, se procesa al volver sin acumular compras atrasadas. Los errores del proveedor se reintentan después de cinco minutos, sin duplicar productos. Los movimientos y errores aparecen en **Ajustes → Logs → Stock**. Eliminar un producto de Stock desactiva su recurrencia para evitar que se vuelva a crear automáticamente.


## Diagnóstico de precios

Recargar la página o cerrar el popup no termina la revisión: la cola sigue en Home Assistant. Si hay una revisión en curso, el botón de actualizar vuelve a abrir su progreso sin iniciar otra. Al acabar, el popup indica «Revisión finalizada» y si el resumen está pendiente de guardarse o disponible en Ajustes → Logs → Tiendas. El resumen se guarda antes de darlo por entregado y se recupera sin duplicados tras errores de almacenamiento o reinicios. Los rechazos y la falta de cobertura se incluyen en esa única entrada final, aunque no se haya podido actualizar ningún precio.

La barra de progreso muestra las referencias procesadas de la cola nocturna y una
estimación basada en cinco minutos por petición. La cola puede durar varias horas;
el porcentaje no representa la antigüedad del precio ni garantiza cobertura de una tienda.
En **Ajustes → Logs → Tiendas** se registran la preparación de la cola, los precios obtenidos,
las referencias no disponibles y los errores HTTP. No se guardan cookies, claves
de acceso ni cuerpos HTML de errores. Un bloqueo 403 no se interpreta como ausencia
del producto ni provoca consultas repetidas al abrir la interfaz.

## Stock de la despensa

**Stock** (`mdi:package-variant`) guarda un inventario común en Home Assistant,
independiente de las listas de compra. Las pestañas Stock y Compras aparecen
a la izquierda y los controles de la vista a la derecha en la misma fila, sin título
adicional. Stock conserva la ordenación, el selector de lista y el cambio de vista;
el botón **+** abre un popup para añadir manualmente un nombre o elegir uno del catálogo,
sin buscador permanente. Subir ticket aparece únicamente en Compras.
Las cantidades no bajan de cero. Cada tarjeta utiliza la imagen o
icono del catálogo cuando existe y un degradado naranja configurable en **Ajustes → Personalización**, con colores inicial y final y vista previa junto a Recetas. Las barras de progreso usan estos colores y se tornan rojizas al agotarse. Los controles rápidos
para sumar o restar aparecen solo en filas. Se puede alternar entre cuadrícula y filas; la cuadrícula utiliza
el número de columnas configurado en Personalización. El botón de orden permite alternar entre orden alfabético y menor stock. El criterio numérico es el predeterminado y compara todos los productos por porcentaje de stock respecto a su cantidad de reposición, de menor a mayor; los empates se ordenan alfabéticamente. La elección se conserva al recargar.

Al pulsar una tarjeta se abre su ficha: cantidad, unidades (uds, kg, g, l, ml o
personalizadas, como Latas), cantidad que se suma por compra y umbral opcional
de reposición. Se admiten hasta tres decimales y las unidades se muestran junto
a la cantidad. El selector de lista de la barra sirve como destino inicial al
configurar la ficha; la lista de reposición queda guardada por producto.
Al llegar al mínimo indicado, se añade a esa lista sin duplicar pendientes o se
recupera su entrada comprada. El botón de eliminar está al final de la ficha,
pide confirmación y conserva catálogo y listas. Los productos con cero permanecen visibles.

Hay tres tipos de control: **Manual / lectores**, **Perecedero** y **Consumo
registrado en Home Assistant**. Los perecederos pasan a cero cuando se cumplen
los días desde la última compra y se añaden a la lista aunque quedase stock. Su fondo muestra la cantidad actual como porcentaje de la reposición configurada: 20 g de 250 g son un 8 %. El indicador está limitado al 100 % y cambia de naranja a rojizo al bajar. El umbral opcional de reposición usa ese mismo porcentaje; en los otros modos se expresa en unidades. La caducidad es independiente del porcentaje y pone el stock a cero al vencer el plazo.
El consumo registrado también muestra una barra de progreso tomando la cantidad de reposición como el 100 %. Descuenta la cantidad indicada cada vez que una entidad
entra en el estado configurado, por ejemplo al pasar una lavadora a `on`.
Las actualizaciones de atributos, el arranque y la recuperación desde
`unknown` o `unavailable` no cuentan como usos.

Al marcar un producto configurado como comprado en cualquiera de las listas
gestionadas, se suma su cantidad de reposición y se reinicia el plazo del perecedero.
Los productos que ya estuvieran comprados al arrancar o reconectar no se suman
otra vez. No se reconstruyen consumos ni compras ocurridos mientras Home Assistant
estaba apagado. Al activar un perecedero o cambiar su plazo o cantidad en la ficha,
el plazo empieza desde ese momento. Las automatizaciones funcionan con la interfaz cerrada;
la caducidad se comprueba cada minuto y también al iniciar la integración.

Los lectores pueden sumar o restar unidades, siguiendo su acción por defecto o
la excepción de cada producto y respetando el intervalo antirrepetición. La captura
de códigos para una ficha sigue suspendiendo estas acciones. Los movimientos y
eliminaciones quedan registrados en Ajustes → Logs → Stock. Las cantidades se
guardan tras cada cambio y se sincronizan entre paneles abiertos; administrar el
inventario requiere una cuenta administradora, mientras que su lectura está
disponible para las demás cuentas autenticadas.

### Listas pasarela

En **Ajustes → Listas**, añade una entidad `todo` como pasarela y selecciona su lista de compra de destino. Por ejemplo, un asistente de voz puede escribir en la pasarela y la integración trasladará los productos nuevos a Bring. Cada pasarela tiene un destino propio y puede conservar los productos o eliminarlos después de transferirlos. Si el producto ya está pendiente en destino, no se duplica; las comparaciones ignoran acentos, mayúsculas y espacios. Si solo existe como completado, se recupera como pendiente cuando el proveedor lo permite.

El contenido anterior a la configuración no se transfiere. Las pasarelas funcionan con la interfaz cerrada, guardan su estado entre reinicios y reintentan las transferencias fallidas sin eliminar el origen antes de tiempo. Las incidencias y transferencias aparecen en **Ajustes → Logs → Listas pasarela**. Una pasarela queda fuera del selector de listas de compra y no puede ser el destino de otra pasarela. Para quitar una lista de destino, cambia o elimina antes sus pasarelas.

### Entidades de Home Assistant

La integración crea un dispositivo Improved Shopping List con quince entidades, disponibles para paneles y automatizaciones. Los nombres se traducen al idioma de Home Assistant y sus identificadores permanecen estables entre reinicios.

| Entidad | Tipo | Criterio |
| --- | --- | --- |
| Productos en la lista de la compra | Sensor | Productos pendientes de la lista principal; excluye completados y pasarelas. |
| Importe aproximado de la próxima compra | Sensor monetario (EUR) | Últimos precios guardados de la tienda activa con más productos con precio. En empate, el menor importe. Sin precio cuenta como cero. Los atributos indican tienda y cobertura. |
| Productos en el catálogo | Sensor | Total del catálogo compartido. |
| Categorías en el catálogo | Sensor | Total de categorías. |
| Productos con stock bajo | Sensor | Mismo criterio que la reposición: mínimo alcanzado según unidades/porcentaje configurado, o producto caducado. |
| Fecha de la última compra | Sensor de fecha y hora | Fecha real del ticket más reciente, aunque se haya importado después un ticket anterior. |
| Importe de la última compra | Sensor monetario | Total del último ticket, con su moneda. |
| Tienda de la última compra | Sensor | Tienda del último ticket. |
| Lectores activos | Sensor | Lectores habilitados. |
| Tienda predeterminada | Sensor | Tienda marcada como favorita. |
| Tiendas activas | Sensor | Número de tiendas habilitadas; atributos `stores` y `store_names` con identificadores y nombres. |
| Actualización automática de precios | Interruptor | Activa o desactiva los precios, igual que el panel. |
| Frecuencia de actualización de precios | Número | Entre 1 y 3650 días enteros. |
| Hora de actualización de precios | Hora | Hora local de Home Assistant, con precisión de minutos. |
| Compartir con la comunidad | Sensor binario | Estado del consentimiento; atributo `authorized` para saber si GitHub está autorizado. La activación y autorización se hacen desde Ajustes → Comunidad. |

Los cambios de los controles también se reflejan en el panel y se guardan entre reinicios. Leer las entidades no consulta tiendas ni fuerza actualizaciones de precios. Si la lista principal no está disponible, su contador y estimación aparecen como no disponibles; el resto de datos se mantiene accesible. Al desactivar los precios, la estimación se oculta como no disponible. Sin tickets, las tres entidades de última compra aparecen como desconocidas.

### Cantidades de compra

La ficha del producto, en Información adicional, permite indicar **Unidades**, **Cantidad unitaria** y **Tamaño del paso**. Los valores iniciales son `uds`, `1` y `1`. Por ejemplo, Pavo con `g`, `250` y `50` aparece como **250 g** al incluirlo en la lista; los controles de filas permiten pasar a 300 g o 200 g. Se admiten unidades personalizadas y cantidades positivas de hasta tres decimales.

La cantidad 1 no muestra indicador. Las demás cantidades aparecen en un triángulo en la esquina superior izquierda en cuadrícula, o en el último badge de las filas. El color verde inicial se cambia desde **Ajustes → Personalización → Color del indicador de cantidad**. Los botones + y − solo se muestran en filas; disminuir nunca elimina el producto ni permite una cantidad cero.

Las cantidades se guardan por lista y UID en Home Assistant, se sincronizan entre sesiones de la integración y no se escriben en el nombre o la descripción del proveedor todo. Quitar una entrada de la lista elimina su ajuste local; los productos del catálogo mantienen sus valores predeterminados. Si se cambian las unidades del producto, los ajustes de cantidad con otras unidades no se reinterpretan automáticamente. Estos datos no se envían al diccionario comunitario.

El ticket, los badges de importe y el sensor de próxima compra aplican la proporción entre la cantidad solicitada y la cantidad unitaria del producto al último precio guardado. Al marcar como comprado, solo se repone Stock si el producto ya estaba añadido allí. Cuando coinciden las unidades se suma la cantidad de la lista; si no coinciden se conserva la cantidad de reposición configurada en Stock. Los tickets confirmados siguen teniendo prioridad para evitar reponer dos veces.


En **Ajustes → Notificaciones** puedes activar dos reglas independientes: avisar cuando una lista tenga **más de X productos pendientes** y cuando haya **más de X productos con stock bajo**. La primera vigila todas las listas configuradas y genera un aviso independiente por lista, sin contar los comprados ni sumar cantidades. La segunda utiliza el mismo criterio de mínimo y caducidad que el indicador de stock bajo. Cada regla permite seleccionar varios [destinos de notificación de Home Assistant](https://www.home-assistant.io/integrations/notify/), un título y un mensaje, con los marcadores `{lista}`, `{cantidad}`, `{limite}` y `{productos}`. Se admiten servicios específicos como `notify.mobile_app_…` y entidades `notify` mediante `notify.send_message`. Las reglas empiezan desactivadas y configurar estos avisos requiere una cuenta administradora.

Los avisos funcionan con el panel cerrado. Se intenta enviar un aviso por destino al superar el umbral y no se repite por cada producto adicional ni al reiniciar Home Assistant. Se reactiva cuando el recuento vuelve al umbral o por debajo. Al activar una regla o cambiar sus destinos o su límite se evalúa también el estado actual. Una lista no disponible no reinicia el aviso. Los envíos y los fallos quedan en **Ajustes → Logs → Notificaciones**; un destino que falle no impide enviar al resto. Los avisos fallidos no se reenvían automáticamente. No se ejecutan plantillas Jinja: los marcadores son sustituciones de texto.


### Agrupar Lista y Stock por categoría

Lista y Stock incluyen un botón con `mdi:label` para agrupar por categorías del catálogo y otro estado con `mdi:sort-alphabetical-ascending` para mostrar todos los productos sin agrupar. La elección se recuerda por separado en cada apartado y funciona en cuadrícula y filas. Las categorías se ordenan por nombre y «Sin categoría» aparece al final. En Lista, tanto pendientes como compras recientes se ordenan alfabéticamente dentro de cada grupo. En Stock, la agrupación conserva el criterio elegido: alfabético o porcentaje de stock de menor a mayor, también al quitar la agrupación. El botón no aparece en Compras; al utilizarlo desde el ticket de Lista vuelve a la vista habitual.


### Avisos de productos nuevos

En **Ajustes → Notificaciones → Productos nuevos** puedes activar un aviso con límite, dispositivos, título y mensaje propios. Cuenta los nombres presentes en las listas configuradas que aún no están en el catálogo (también los de compras recientes, como en Catálogo → Nuevos), unificando repeticiones entre listas sin distinguir tildes o mayúsculas, y suma los códigos desconocidos pendientes de los lectores. Excluye productos y códigos ya vinculados y sugerencias descartadas. Las listas pasarela no se incluyen. Un código pendiente es una propuesta independiente: no se presupone que coincida con un nombre sin vincular.

El límite inicial es 0: se avisa a partir de la primera propuesta si activas la regla. Se envía una vez al superar el límite; añadir al catálogo, vincular o descartar puede rearmar el aviso al reducir el total al límite o por debajo. El estado sobrevive a reinicios y una lista temporalmente no disponible no provoca avisos repetidos. Funciona en segundo plano, sin tener el panel abierto y sin consultas externas adicionales. Admite los mismos destinos nativos de notificación que los demás avisos.


En la vista de filas de Lista, cada producto muestra un único badge horizontal de cantidad: restar (`mdi:minus-thick`), cantidad con sus unidades y sumar (`mdi:plus-thick`). También muestra «1 uds» cuando corresponde, para poder ajustar la cantidad desde ese mismo control. El badge usa el color configurable del indicador de cantidad. Los botones respetan el paso del producto y los permisos, no marcan el producto como comprado y solo aparecen en filas; la cuadrícula conserva su triángulo de cantidad.


Los pasos de revisión del ticket muestran en azul el paso actual y en verde los anteriores completados. Puedes pulsar un paso anterior, también con teclado, para volver a él conservando vinculaciones, cantidades y selección de precios. Los pasos posteriores se habilitan mediante Continuar y durante el guardado la navegación permanece bloqueada.
