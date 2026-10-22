# Improved Shopping List

<img src="custom_components/improved_shopping_list/brand/icon.png" alt="Improved Shopping List" width="96">

Una interfaz propia para gestionar las listas de la compra que ya tienes integradas en Home Assistant.

Versión actual: **0.24.0**. Interfaz en español, pensada para móvil y ordenador. Requiere **Home Assistant Core 2026.10 o posterior**. La referencia de desarrollo es Core 2026.10.2.

Vinculaciones con Mercadona, Carrefour, Alcampo, Consum, La Sirena, Eroski y DIA, y consultas
directas desde Home Assistant. Se ha retirado el feed
de precios de GitHub y la dependencia de Aguacatec.

En Información adicional se elige una tienda y se añade el enlace o referencia del
artículo. Sus EAN se conservan como metadatos de tienda; los códigos configurados para
los lectores no se reasignan automáticamente. El precio manual sigue siendo independiente.

La revisión diaria empieza a las 01:00 por defecto, en la zona horaria de Home Assistant,
y puede configurarse desde el icono del reloj en Ajustes → Tiendas. Solo entra en la cola lo pendiente en las listas
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

- Seleccionar cualquier entidad `todo.*` disponible para tu usuario, incluida Bring!, Shopping List u otros proveedores.
- Consultar productos pendientes y comprados.
- Pulsar el importe estimado para abrir un ticket por tienda con los precios guardados. Se muestran hasta cuatro tiendas activas, priorizando las que tienen más productos con precio y, en caso de empate, el menor importe conocido. Cada una muestra logo, importe y cobertura. Los productos sin precio se agrupan en un bloque plegado y cuentan como 0; los totales pueden incluir distintas cestas parciales. El badge del número de productos devuelve a la vista habitual.
- Añadir productos, marcarlos como comprados y volver a ponerlos por comprar.
- Recibir cambios del proveedor mediante la API nativa de listas de Home Assistant.
- Añadir o quitar entidades `todo` desde Ajustes y marcar una lista como principal.
- Crear y editar productos en un catálogo local compartido entre los usuarios de Home Assistant, con vistas Productos y Categorías.
- Asignar categorías, códigos de barras, etiquetas NFC, precios orientativos e imágenes.
- Buscar, filtrar y añadir productos del catálogo a la lista seleccionada.
- Agrupar el catálogo por categoría, Nutri-Score o «Vinculados»: un bloque por tienda, con el mismo producto en varias si corresponde, y «No vinculados» al final. Las vinculaciones se muestran aunque la tienda esté desactivada.

Cada lista conserva sus datos en su integración original. Las operaciones disponibles dependen de lo que admita ese proveedor. Por ejemplo, una lista de solo lectura se puede consultar, pero sus controles de edición aparecen desactivados. La frecuencia con la que Bring! u otro proveedor recibe cambios de su nube depende de su propia integración.

El panel se comunica con Home Assistant usando la sesión del usuario y las APIs nativas. La gestión local no necesita tokens adicionales ni cuentas nuevas; compartir datos con la comunidad requiere autorizar voluntariamente una cuenta de GitHub. Las funciones de consulta de productos e iconos utilizan Open Food Facts e Iconify respectivamente; la gestión de listas y del catálogo funciona sin esos servicios. El JavaScript se sirve localmente y no utiliza un CDN.

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

Solo es obligatorio el nombre. Las categorías se crean, editan y eliminan desde la vista Categorías, donde puedes elegir su icono MDI y su color. Renombrar una categoría actualiza sus productos; eliminarla los conserva sin categoría. Las categorías introducidas en instalaciones anteriores se recuperan automáticamente con un icono y un color predeterminados. La ficha se divide en Características principales (nombre, sugerencias de iconos, URL de imagen y categoría), Información adicional (precio y moneda) y Automatización (códigos de barras/QR, etiquetas NFC y acciones de lectores). Guardar conserva los datos de todas las vistas. Los campos Etiquetas, Icono del producto y Notas se han retirado del formulario; los valores de instalaciones anteriores se conservan al editar.

Las tarjetas muestran primero la imagen o el icono del producto y debajo su nombre, centrados. Si no hay imagen se utiliza el icono propio del producto; si tampoco tiene icono propio, se utiliza el de su categoría y, cuando no tiene categoría, `mdi:shopping`. Este criterio también se aplica en Lista y en sus sugerencias de búsqueda. En Lista, la categoría se representa con un icono blanco sobre un círculo de su color en la esquina superior derecha, sin borde y con sombra. En Catálogo → Productos, las tarjetas son cuadradas: pulsar su superficie añade el producto a la lista seleccionada, también con Enter o espacio. Al pulsar una tarjeta no se muestra un mensaje de confirmación; el degradado indica que el producto está pendiente. Las tarjetas de productos ya pendientes no vuelven a añadirlos. Antes de añadir se consulta el contenido actual de la lista, comparando sin tildes ni mayúsculas y agrupando pulsaciones simultáneas del mismo producto en el panel. Si ya estaba comprado, se recupera su entrada por identificador; si el proveedor no permite recuperarla, se muestra el error sin crear un duplicado. Los dos controles circulares de la esquina permiten editar (fondo naranja/amarillo) y eliminar (fondo negro), sin activar la acción de añadir. El borrado pide confirmación, elimina la ficha y sus códigos del catálogo y conserva los elementos de las listas. El selector de categorías permite filtrar los productos. El campo **URL Imagen/Icono**, situado debajo de las sugerencias, permite introducir libremente una URL http/https o una ruta local como `/local/cacao.png`. El navegador carga las imágenes manuales desde la ubicación indicada; no se descargan al servidor ni hay subida de archivos.

La ficha del producto muestra directamente las sugerencias de [Iconify](https://iconify.design/), gratuitamente y sin clave, debajo del nombre. No hay botón de Buscar icono ni popup adicional. Las propuestas se cargan al abrir la ficha y se actualizan automáticamente al escribir o cambiar el nombre, esperando medio segundo para agrupar las pulsaciones. El selector tiene seis bloques sin nombres visibles: hasta cinco imágenes de colecciones a color (Noto Emoji, Fluent Emoji Flat y OpenMoji), y un bloque adicional con `mdi:plus-thick` que sustituye las cinco propuestas por otras del mismo término, sin salir de la ficha. Si hay menos de cinco resultados, se conservan los huecos; el bloque + se oculta si no hay resultados. Puedes ajustar el término desde el campo Buscar iconos; se actualiza al escribir o al pulsar Enter. Las propuestas se recorren en grupos de cinco; se reutilizan los resultados ya cargados y solo se consulta otro lote cuando hace falta. Al agotar los resultados, + vuelve al primer grupo; si solo hay cinco propuestas o menos, queda desactivado. Elegir una propuesta rellena la imagen en la ficha y mantiene las sugerencias visibles; la imagen se asigna al producto al guardar. Mientras se descarga el icono se bloquea Guardar producto para no guardar una imagen anterior. Cancelar o cambiar de nombre impide que una descarga tardía cambie otra ficha. Escribir una URL manual también cancela la asignación pendiente del icono: la descarga tardía no sobrescribe la dirección elegida.

Al guardar un producto, Home Assistant consulta [MyMemory](https://mymemory.translated.net/doc/spec.php) para traducir su nombre del español al inglés y guarda el resultado en `name_en`, junto con la ficha. El nombre visible sigue en español. Las sugerencias automáticas utilizan esa traducción guardada; si una ficha antigua no tiene traducción, se obtiene y guarda al abrirla, sin exigir volver a guardar ni invalidar la ficha abierta. Los borradores también se traducen para la búsqueda inicial; la ficha se crea solo al guardar. El campo Buscar iconos muestra el término inglés utilizado, por ejemplo `Rice` para «Arroz». Las búsquedas escritas manualmente se respetan sin traducir otra vez. Si cambia el nombre del producto, se renueva la traducción. No se traducen todos los productos en bloque al iniciar la integración.

Solo se envía el nombre del producto a MyMemory, sin clave ni cuenta; se aplican los límites del servicio gratuito. Un fallo, tiempo de espera o límite de cuota no impide guardar el producto: la búsqueda usa el nombre original y se reintenta traducir la próxima vez que se guarde o se abra una búsqueda automática sin traducción. La espera de traducción se limita a cinco segundos. Las traducciones se conservan tras reiniciar y no se vuelve a consultar el servicio al guardar otros cambios si ya hay una traducción para ese nombre.

Las búsquedas se realizan desde Home Assistant y las vistas previas se cargan desde Iconify en el navegador. Al elegir un icono se descarga y valida un SVG estático, se guarda en `.storage/improved_shopping_list_icons` y su ruta local se coloca en el campo de imagen. La imagen del producto solo cambia al pulsar **Guardar producto**. El archivo elegido sigue disponible sin Internet y después de reiniciar Home Assistant. El autor, la colección, la fuente y la licencia se conservan en `.storage/improved_shopping_list.icon_assets` y se muestran en la ficha. Los archivos son recursos públicos del panel, igual que su logo, y no contienen información de productos ni credenciales. Cancelar una ficha puede dejar un icono en la caché local sin asignarlo al producto; una traducción obtenida para una ficha existente se conserva. Las consultas se guardan temporalmente en memoria durante seis horas; no se envían códigos de barras ni otros datos de la ficha a Iconify, solo el término de búsqueda y el identificador elegido.

Los productos pendientes en la lista seleccionada se resaltan con un degradado rojo. La coincidencia se realiza por nombre, sin distinguir mayúsculas ni diferencias de espacios; los elementos comprados no se resaltan. Cambiar de lista actualiza este estado visual y conserva el catálogo común.

El apartado Lista también presenta los productos en una cuadrícula de tarjetas, con imagen o icono y nombre centrados. Si el nombre coincide con una ficha del catálogo, utiliza su imagen, icono, etiquetas y distintivo de categoría. Para productos sin ficha se muestra `mdi:shopping`. Pulsa una tarjeta completa para marcar o desmarcar su compra; también funciona con Enter o espacio. Se conserva el apartado desplegable de comprados, sin mostrar precios ni un control de compra dentro de cada tarjeta.

En **Ajustes → Personalización** puedes elegir por separado los dos colores del degradado de productos pendientes y los de Comprados, además del número de tarjetas por fila, de 1 a 6 en ordenador y de 1 a 4 en móvil. Por defecto los pendientes usan `linear-gradient(rgba(238, 82, 79, 1), rgba(181, 42, 39, 1))` y los comprados `linear-gradient(rgba(79, 171, 162, 1), rgba(38, 133, 124, 1))`, con 3 productos por fila en ordenador y 1 en móvil. Pulsa la tarjeta de un producto comprado para devolverlo a Por comprar; se actualiza el mismo elemento, sin duplicarlo ni mostrar un control adicional dentro de la tarjeta. Los cambios se aplican al guardar, persisten en Home Assistant y se comparten entre dispositivos. Con los degradados predeterminados, el texto y los iconos son blancos; con colores personalizados, el texto se adapta a los colores elegidos. Restablecer valores permite recuperar estos valores y guardarlos de nuevo.

El campo Añadir producto ofrece hasta ocho coincidencias del catálogo mientras escribes, por nombre, código de barras o etiquetas, sin distinguir tildes ni mayúsculas. Puedes tocar una coincidencia o seleccionarla con las flechas y Enter para añadir su nombre a la lista. Escape cierra el desplegable. También puedes escribir y añadir un producto nuevo libremente.

En **Catálogo → Productos**, el botón entre Añadir producto y Cambiar vista alterna el orden alfabético con la agrupación por categorías. Muestra `mdi:label` para agrupar y `mdi:sort-alphabetical-ascending` para volver al orden alfabético. Los grupos y sus productos se ordenan alfabéticamente; **Sin categoría** aparece al final. La búsqueda se mantiene en ambos modos, también en filas o cuadrícula. Se recuerda el modo elegido en el navegador. Retirado el selector de categorías. Mientras está agrupado, el botón de criterio abre un popup para elegir **Categoría** o **Nutri-Score**. Este último ordena los grupos de A a E, con **Sin Nutri-Score** al final, y mantiene el orden alfabético dentro de cada grupo. La elección se recuerda en el navegador. La consulta nutricional utiliza los EAN válidos del catálogo y la caché existente de Open Food Facts; solo se solicita mientras está abierta esta vista y el criterio nutricional está seleccionado. Los códigos QR/NFC no se consultan como productos. Un dato no disponible no impide utilizar el catálogo.

El número de tarjetas por fila configurado en Personalización se aplica a Lista y Catálogo → Productos, con valores separados para móvil y ordenador. Catálogo → Categorías utiliza esos valores con un máximo de 5 columnas en ordenador y 2 en móvil. Sus tarjetas y sus botones de editar y eliminar tienen proporción 1:1. Los botones se sitúan juntos en la esquina superior derecha, independientes del contenido centrado; los nombres largos se limitan a dos líneas y se pueden consultar completos al situar el cursor encima.

La barra de Lista reúne en una sola fila el buscador, el botón de añadir (`mdi:plus-thick`) y el selector de listas (`mdi:format-list-checks`). Este último abre un popup con las listas integradas en Home Assistant y marca la seleccionada; toca otra lista para cambiar. La opción de actualizar la lista está dentro de ese popup.

La vista **Sugerencias** (`mdi:creation`) muestra los nombres de productos de la lista seleccionada que aún no están en el catálogo, incluidos los elementos comprados que siguen en la lista. Añadir al catálogo abre el formulario con el nombre ya rellenado, para completar categoría, etiquetas y otros datos antes de guardar. Si corriges el nombre en ese formulario, al guardar se renombra el elemento original de la lista, conservando su estado y demás datos; también se actualizan las variantes equivalentes de esa sugerencia en la misma lista. La lista y los identificadores de origen se conservan aunque cambies de lista mientras está abierta la ficha. Si el proveedor no permite renombrar o falla la operación, la ficha informa del error: el producto queda guardado en el catálogo y puedes reintentar sin crear otra ficha. Cancelar conserva la sugerencia sin crear el producto. También puedes descartar sugerencias sin modificar la lista. Las sugerencias, las coincidencias con el catálogo y los descartes comparan los nombres ignorando tildes, mayúsculas, caracteres Unicode equivalentes y espacios sobrantes. Así, «Seitan», «Seitán» y «SEITÁN» no producen sugerencias distintas; los nombres guardados conservan su escritura original. Los descartes se guardan en Home Assistant, se comparten entre sesiones y listas y se conservan tras reiniciar. Para cambiar la lista de origen, utiliza el selector del apartado Lista.

El precio es manual y orientativo, asociado al producto y la moneda indicados, con su fecha de actualización. Se conserva en la ficha de edición, pero no se muestra en las tarjetas. Todavía no hay comparación de ofertas por supermercado, consulta automática de precios, scrapeo ni importación de PDF. El código de barras se guarda como texto para conservar sus ceros iniciales. Los campos Marca y Formato se han retirado; las instalaciones anteriores eliminan esos campos al cargar el catálogo, conservando los productos y sus códigos.

Las ediciones simultáneas se detectan: si otra sesión ha cambiado una ficha, se pide volver a abrirla antes de guardar. No se borra el catálogo al cambiar de lista ni al recargar la integración. Se conserva también al retirar la integración para permitir reinstalarla; los productos de las listas originales tampoco se eliminan.

El apartado **Ajustes** (`mdi:cog`) permite añadir cualquier entidad `todo` de Home Assistant, quitar listas de esta interfaz y marcar una como principal. El popup de Lista muestra únicamente las listas añadidas; la principal se abre al iniciar el panel. Quitar una lista conserva su entidad y sus productos originales. Si quitas la principal, pasa a ser principal la primera restante; si quitas todas, puedes volver a añadir una desde Ajustes.

La selección de listas y la principal se guardan en las opciones de la integración en Home Assistant, se comparten entre dispositivos y se sincronizan en los paneles abiertos. Las instalaciones anteriores conservan las listas que tenían disponibles al actualizar. Un administrador puede modificar estos ajustes; el resto de usuarios pueden consultar y utilizar las listas según los permisos de Home Assistant. **Configurar** en la integración también permite cambiar la principal sin perder las listas añadidas. Cambiar de lista desde el popup solo cambia la selección de esa sesión.

## Lectores de códigos y NFC

Los códigos de producto desconocidos se consultan en [Open Food Facts](https://world.openfoodfacts.org/), desde Home Assistant y en segundo plano. Solo se envían códigos numéricos GTIN de 8, 12, 13 o 14 cifras con dígito de control válido; los identificadores NFC, los QR con texto o URL y los códigos ya asociados no se consultan. No se necesita una clave API.

En **Catálogo → Sugerencias → Productos escaneados** se muestran el nombre encontrado (priorizando el nombre común en español) y la atribución a Open Food Facts (datos bajo ODbL), cuando estén disponibles. El botón **+** rellena una ficha nueva con el nombre y una nota de procedencia. Las coincidencias de nombre con el catálogo son aproximadas: el botón de cuadrícula permite elegir un producto y revisar su ficha antes de guardar el código. No se crean productos, se modifican fichas ni se asocian códigos automáticamente; los datos externos tampoco sustituyen los de un producto existente.

La caché local persiste entre reinicios: resultados encontrados durante 30 días, sin resultado durante un día y errores durante cinco minutos. Las consultas se serializan con una separación mínima de 4,1 segundos y espera adicional si el servicio limita las peticiones. Los fallos de conexión no bloquean los lectores ni la identificación manual. Al reiniciar o volver a escanear se renuevan resultados caducados; las respuestas guardadas se limitan a 500 códigos. No se descargan imágenes ni se consultan precios.

El apartado **Lectores** (`mdi:barcode-scan`) permite añadir, editar, desactivar o quitar lectores. Cada lector tiene un nombre, tipo (barras/QR o NFC), lista de destino, acción por defecto y protección antirrepetición; la lista principal y 60 segundos son los valores predeterminados. El interruptor de la tarjeta controla si está activo; editar su ficha conserva ese estado. Configurar lectores requiere una cuenta administradora. Quitar un lector no elimina su entidad ni los productos del catálogo.

El botón azul con `mdi:eye-outline`, a la izquierda de Editar, abre la información de la entidad en el popup nativo de Home Assistant, cuyo estado se actualiza al recibir lecturas. Para los lectores NFC que utilizan eventos y no tienen entidad, abre un popup con el último código, producto identificado, resultado y hora, actualizado en directo. Consultar esta información no requiere ser administrador ni ejecuta acciones del lector.

Puedes utilizar el estado de cualquier entidad existente, como `sensor.lector_cb_codigo_leido`, o indicar el atributo que contiene el código. Para lectores que generan eventos `tag_scanned`, elige NFC, esa fuente y el `device_id` del dispositivo. Los identificadores se tratan como texto, conservando ceros iniciales; los QR se usan como identificadores literales, sin abrir sus enlaces ni consultar APIs. Los identificadores NFC hexadecimales admiten diferencias de mayúsculas y separadores `:` o `-`.

En la ficha del producto, **Automatización** reúne los códigos en dos apartados: **Códigos de barras/QR** y **Etiquetas NFC**. Selecciona un lector activo del tipo correspondiente y pulsa **Escanear**. Cada lectura aparece en una línea, sin campos de escritura manual; puedes quitarla individualmente y capturar hasta 50 códigos de cada tipo. Los códigos ya existentes se conservan y las nuevas asociaciones se aplican al guardar el producto. Un mismo código no puede corresponder a dos productos del mismo tipo.

La captura dura hasta 60 segundos y puede detenerse manualmente. Se libera al cerrar la ficha, cambiar de apartado, desconectarse, modificar el lector o detener la integración. Durante la captura, ese lector no ejecuta acciones, no genera sugerencias de códigos desconocidos y no actualiza el periodo antirrepetición. Solo una ficha puede capturarlo a la vez; se requiere una cuenta administradora.

Para cada lector puedes elegir **Usar acción por defecto del lector**, **Sin acción**, **Añadir a la lista de la compra**, **Quitar una unidad al stock** o **Añadir una unidad al stock**. Si no hay una acción específica, se aplica la del lector al reconocer el producto; cambiarla afecta también a los productos que la heredan. Una acción específica tiene prioridad, incluido **Sin acción**. Las selecciones anteriores se conservan y los lectores existentes empiezan sin acción por defecto. Las acciones de stock suman o restan una unidad de la despensa común, conservan la protección antirrepetición y no modifican listas de compra.

Las lecturas se procesan en Home Assistant aunque el panel esté cerrado. El intervalo antirrepetición se aplica a cada pareja lector/producto y también al código leído, se guarda para sobrevivir a recargas y no impide leer otros productos. No se ejecutan lecturas antiguas al arrancar ni cambios de atributos ajenos al código. Para repetir exactamente el mismo código tras el intervalo, la entidad debe generar una nueva lectura/evento; conservar su valor sin emitir nada no es una nueva lectura.

Una lectura desconocida aparece en **Catálogo → Sugerencias**, donde puedes abrir la ficha de un producto nuevo o seleccionar uno existente para asociar el código. El formulario permite completar los datos y elegir las acciones de sus lectores antes de guardar. Asociar una lectura pasada no ejecuta su acción automáticamente. También puedes descartar un código desconocido de forma persistente.

El botón azul de vincular abre un popup con buscador predictivo de productos del catálogo. Filtra mientras escribes sin distinguir tildes ni mayúsculas y muestra primero las posibles coincidencias sugeridas por Open Food Facts. Puedes elegir con un clic o con las flechas y Enter; Escape cierra las propuestas. Elegir un producto no guarda cambios: pulsa **Asignar** para vincular el código, o **Cancelar** para salir sin guardar. El resto de los datos y las acciones de lectores se conservan y no se ejecuta la lectura pasada. El texto y el cursor se conservan si llegan nuevas lecturas mientras buscas.

Al añadir a una lista se comprueba si el producto ya está pendiente, comparando el nombre sin diferencias de tildes, mayúsculas o espacios. En ese caso se mantiene una sola entrada. Si está comprado, se recupera el mismo elemento cuando el proveedor admite actualizarlo. Una lista explícita que se haya quitado de Ajustes o que esté indisponible produce un error en el registro de Home Assistant; no se sustituye silenciosamente por otra. El apartado Lectores muestra el icono del tipo, el nombre, la entidad o dispositivo y el tiempo desde el último uso registrado durante la ejecución. Cada tarjeta permite activar o desactivar el lector con un interruptor. Tras un error puedes efectuar una nueva lectura una vez transcurrido el intervalo.

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

En **Ajustes → Comunidad**, activa **Compartir mis datos de productos** para iniciar la autorización con la GitHub App. Abre el enlace de GitHub e introduce el código mostrado. Al completarla se solicita el envío inmediato de los datos disponibles, aunque haya una revisión de precios en curso, respetando el límite de un lote cada 24 horas y las pausas de reintento. Volver a marcar la casilla no reinicia ese límite. La integración guarda sus credenciales de forma privada y no utiliza las de HACS. Desmarcar la casilla detiene las aportaciones.

El diccionario público se consulta una vez al día, sin cuenta y sin actualizar la integración. Permite completar traducciones y vinculaciones confirmadas que falten, sugerir nombres e iconos y reutilizar precios por referencia exacta durante 24 horas, conservando la fecha original. No sobrescribe elecciones locales ni crea automáticamente productos del catálogo.

Con el consentimiento activado se aportan los datos permitidos de todo el catálogo: nombres, traducciones, EAN, vinculaciones con tiendas, Nutri-Score, precios e iconos admitidos. Las aportaciones son públicas y están asociadas a la cuenta de GitHub, con un lote por cuenta cada 24 horas. Se excluyen listas, stock, NFC, lectores, categorías personales, notas y automatizaciones.

GitHub Actions valida los datos automáticamente: consenso de tres cuentas independientes para los campos confirmados, comprobación de licencias de Iconify y control de variaciones de precios superiores al 50 %. Las preferencias de iconos se cuentan por separado. El mantenedor puede bloquear cuentas y recuperar una versión anterior del diccionario. Consulta [el funcionamiento y la política del catálogo comunitario](community/README.md).

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
independiente de las listas de compra. La barra permite escribir un nombre o elegir
una coincidencia del catálogo y sumar una unidad con **+**. Repetir un producto
suma unidades; las cantidades no bajan de cero. Cada tarjeta utiliza la imagen o
icono del catálogo cuando existe y un degradado naranja. Los controles rápidos
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
