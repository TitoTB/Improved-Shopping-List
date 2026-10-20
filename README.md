# Improved Shopping List

<img src="custom_components/improved_shopping_list/brand/icon.png" alt="Improved Shopping List" width="96">

Una interfaz propia para gestionar las listas de la compra que ya tienes integradas en Home Assistant.

Versión actual: **0.10.0**. Interfaz en español, pensada para móvil y ordenador. Requiere **Home Assistant Core 2026.10 o posterior**. La referencia de desarrollo es Core 2026.10.2.

## Qué puedes hacer

- Seleccionar cualquier entidad `todo.*` disponible para tu usuario, incluida Bring!, Shopping List u otros proveedores.
- Consultar productos pendientes y comprados.
- Añadir productos, marcarlos como comprados y volver a ponerlos por comprar.
- Recibir cambios del proveedor mediante la API nativa de listas de Home Assistant.
- Añadir o quitar entidades `todo` desde Ajustes y marcar una lista como principal.
- Crear y editar productos en un catálogo local compartido entre los usuarios de Home Assistant, con vistas Productos y Categorías.
- Asignar categorías, códigos de barras, etiquetas NFC, precios orientativos e imágenes.
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

El apartado **Lectores** (`mdi:barcode-scan`) permite añadir, editar, desactivar o quitar lectores. Cada lector tiene un nombre, tipo (barras/QR o NFC), lista de destino y protección antirrepetición; la lista principal y 60 segundos son los valores predeterminados. Configurar lectores requiere una cuenta administradora. Quitar un lector no elimina su entidad ni los productos del catálogo.

El botón azul con `mdi:eye-outline`, a la izquierda de Editar, abre la información de la entidad en el popup nativo de Home Assistant, cuyo estado se actualiza al recibir lecturas. Para los lectores NFC que utilizan eventos y no tienen entidad, abre un popup con el último código, producto identificado, resultado y hora, actualizado en directo. Consultar esta información no requiere ser administrador ni ejecuta acciones del lector.

Puedes utilizar el estado de cualquier entidad existente, como `sensor.lector_cb_codigo_leido`, o indicar el atributo que contiene el código. Para lectores que generan eventos `tag_scanned`, elige NFC, esa fuente y el `device_id` del dispositivo. Los identificadores se tratan como texto, conservando ceros iniciales; los QR se usan como identificadores literales, sin abrir sus enlaces ni consultar APIs. Los identificadores NFC hexadecimales admiten diferencias de mayúsculas y separadores `:` o `-`.

En la ficha del producto puedes añadir un código principal, hasta 50 códigos adicionales de barras/QR y hasta 50 identificadores NFC, uno por línea. Un mismo código no puede corresponder a dos productos del mismo tipo. Para cada lector puedes elegir **Sin acción**, **Añadir a la lista de la compra**, **Quitar una unidad al stock** o **Añadir una unidad al stock**. Las acciones de stock se guardan para una fase posterior y, por ahora, solo informan de que el inventario está pendiente de implementar.

Las lecturas se procesan en Home Assistant aunque el panel esté cerrado. El intervalo antirrepetición se aplica a cada pareja lector/producto y también al código leído, se guarda para sobrevivir a recargas y no impide leer otros productos. No se ejecutan lecturas antiguas al arrancar ni cambios de atributos ajenos al código. Para repetir exactamente el mismo código tras el intervalo, la entidad debe generar una nueva lectura/evento; conservar su valor sin emitir nada no es una nueva lectura.

Una lectura desconocida aparece en **Catálogo → Sugerencias**, donde puedes abrir la ficha de un producto nuevo o seleccionar uno existente para asociar el código. El formulario permite completar los datos y elegir las acciones de sus lectores antes de guardar. Asociar una lectura pasada no ejecuta su acción automáticamente. También puedes descartar un código desconocido de forma persistente.

El botón azul de vincular abre un popup con buscador predictivo de productos del catálogo. Filtra mientras escribes sin distinguir tildes ni mayúsculas y muestra primero las posibles coincidencias sugeridas por Open Food Facts. Puedes elegir con un clic o con las flechas y Enter; Escape cierra las propuestas. Elegir un producto no guarda cambios: pulsa **Asignar** para vincular el código, o **Cancelar** para salir sin guardar. El resto de los datos y las acciones de lectores se conservan y no se ejecuta la lectura pasada. El texto y el cursor se conservan si llegan nuevas lecturas mientras buscas.

Al añadir a una lista se comprueba si el producto ya está pendiente, comparando el nombre sin diferencias de tildes, mayúsculas o espacios. En ese caso se mantiene una sola entrada. Si está comprado, se recupera el mismo elemento cuando el proveedor admite actualizarlo. Una lista explícita que se haya quitado de Ajustes o que esté indisponible produce un error en el registro de Home Assistant; no se sustituye silenciosamente por otra. El apartado Lectores muestra el icono del tipo, el nombre, la entidad o dispositivo y el tiempo desde el último uso registrado durante la ejecución. Cada tarjeta permite activar o desactivar el lector con un interruptor. Tras un error puedes efectuar una nueva lectura una vez transcurrido el intervalo.

Eliminar la integración retira el panel y desactiva sus comandos de catálogo.

## Historial de actividad

El apartado **Logs** (`mdi:format-list-group`) conserva las últimas 1.000 entradas en Home Assistant, de más reciente a más antigua. Incluye altas y bajas de productos en las listas configuradas, compras, recuperación de productos como pendientes, cambios de nombre y otros datos de la lista, creación/edición/borrado de productos y categorías, cambios de lectores y ajustes, y el resultado de las lecturas (incluidos códigos desconocidos, errores y lecturas repetidas ignoradas). Muestra fecha y hora, producto, lista y lector cuando están disponibles. Los cambios del catálogo indican los campos modificados y el nombre anterior cuando corresponda.

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

### Comunidad: exportación voluntaria de iconos

En **Ajustes → Comunidad → Exportar mis iconos** se descarga un ZIP con un diccionario JSON e imágenes locales. No hay envíos automáticos: puedes facilitarlo al mantenedor para revisar traducciones, permisos y duplicados antes de incorporarlo al [catálogo comunitario](community/README.md). Las URL externas y licencias desconocidas requieren revisión. El archivo no contiene listas, códigos ni notas.

Las imágenes comunitarias revisadas se consultan desde este repositorio, se muestran antes que Iconify y se ordenan por presencia en aportaciones revisadas, sin estadísticas globales de usuarios. El índice empieza vacío y puede actualizarse sin publicar otra versión de la integración. Las traducciones que falten se completan al revisar la aportación.

### Nutri-Score en la ficha

La vista **Información adicional** consulta Open Food Facts para los códigos de barras válidos de la ficha y muestra el Nutri-Score A–E cuando está disponible. Cada resultado indica el producto concreto, su código, la fecha de consulta y la fuente. Si una ficha genérica agrupa varios códigos, los resultados se presentan por separado. Las etiquetas NFC, los QR y los códigos con dígito de control incorrecto no se envían.

Se reutiliza la caché persistente de identificación (30 días para productos encontrados); los resultados sin calificación y los fallos no impiden guardar la ficha. Las consultas se limitan y agrupan por código, incluidas las variantes UPC/EAN equivalentes. No se calcula una nota propia ni se asigna una calificación genérica a todos los códigos del producto. Los distintivos se cargan desde los recursos oficiales publicados por Open Food Facts; la letra también se muestra como texto.


## Tiendas: Mercadona

En **Ajustes → Tiendas**, cada tienda se muestra en un bloque horizontal con su logo, nombre, interruptor y botón de configuración. El logo de Mercadona se carga desde la URL externa indicada; los precios no dependen de esa imagen. El interruptor habilita o deshabilita la tienda. Si todavía no tiene ubicación, al habilitarla se abre la configuración para introducir un código postal.

El botón de engranaje abre un popup con dos vistas:

- **Productos**: productos del catálogo con un EAN/GTIN válido encontrado exactamente en Mercadona para el almacén configurado. Muestra nombre, EAN, referencia comercial, precio en euros, precio por unidad de referencia cuando existe, disponibilidad y fecha de consulta. Los precios aproximados se indican con ≈. El botón **Forzar actualización** vuelve a consultar los precios y requiere permisos de administrador.
- **Configuración**: código postal y almacén asignado. **Comprobar y guardar** consulta a Mercadona sin iniciar sesión. También permite preparar la ubicación mientras la tienda está deshabilitada. La tienda habilitada queda como favorita al ser la única disponible.

Los precios se consultan al abrir Productos y se reutilizan durante seis horas. El refresco revisa hasta 20 códigos por lote, empezando por los más antiguos, y permite continuar con el botón manual. No se descargan todos los productos de la tienda ni se ejecuta un proceso periódico en segundo plano. Primero se busca el EAN y, si no hay coincidencia, el nombre; un resultado solo se incorpora si su EAN coincide, nunca por similitud del nombre. Los códigos QR y las etiquetas NFC no se envían para buscar precios.

Las consultas utilizan el buscador web de Mercadona, que puede rechazar peticiones externas (por ejemplo, HTTP 403). Estos errores se muestran y conservan los precios anteriores con su fecha de consulta; se aplica una pausa progresiva antes de reintentar: al menos 15 minutos ante HTTP 403, cinco minutos ante HTTP 429 y un minuto en otros errores. Se respeta `Retry-After` cuando indica una espera mayor. La pausa se conserva al reiniciar y el botón manual no la omite. Los resultados se guardan en Home Assistant, separados por almacén, y no se muestran como precios de otra región ni de una tienda deshabilitada. Esta función todavía no sustituye el precio manual de la ficha del producto.

El código postal se guarda en las opciones de Home Assistant y solo se envía a Mercadona al comprobar la ubicación; no se publican códigos postales ni capturas HAR en GitHub. Los errores conservan la configuración anterior y no asignan un almacén de sustitución.


## Compras recurrentes

Al final de **Automatización** en la ficha de un producto, activa **Comprar cada X días** e indica entre 1 y 3650 días. La recurrencia utiliza la lista principal configurada en Ajustes. El primer plazo empieza al guardar su activación; cambiar los días o desactivarla y volver a activarla inicia un plazo nuevo. Editar otros datos o asociar un código conserva el periodo.

Home Assistant comprueba los vencimientos cada minuto aunque el panel esté cerrado. Al vencer, consulta el contenido actual de la lista sin distinguir tildes, mayúsculas ni espacios sobrantes. Si el producto ya está pendiente, no crea otra entrada. Si está comprado, recupera el mismo elemento por su identificador cuando el proveedor lo permite; si no existe, lo añade. Al terminar, incluso si ya estaba pendiente, reinicia el plazo desde ese momento. No se reinicia al marcar una compra como completada.

La programación se guarda en Home Assistant y sobrevive a reinicios. Si un plazo ha vencido mientras estaba apagado, se procesa una sola vez al volver, sin acumular compras atrasadas. Si la lista no está disponible o el proveedor rechaza la operación, se conserva el vencimiento y se reintenta después de cinco minutos. No se crea un duplicado de una entrada comprada si el proveedor no permite recuperarla. Las acciones, los periodos reiniciados y los errores se registran en **Logs → Recurrencias**, con origen automático.


Las peticiones de precios de Mercadona se separan por al menos dos segundos desde el final de la petición anterior, incluida la alternativa de buscar por nombre. Un rechazo detiene el lote; no se sigue consultando el resto de los EAN. La interfaz muestra que la actualización está pausada, su hora de reanudación y los códigos revisados, sin interpretar un error como ausencia de productos.

En **Logs → Tiendas**, cada actualización registra inicio y resumen; los errores incluyen un bloque desplegable **Información técnica**. Contiene endpoint y método, almacén, EAN, tipo de búsqueda, número de petición y lote, estado HTTP, duración, tipo de respuesta, referencia de petición si el servidor la proporciona y plazo de reintento. Los errores también se escriben en los registros de Home Assistant. No se guardan cookies, cabeceras de autenticación, direcciones IP ni el cuerpo HTML. La página de «uso indebido del servicio» se clasifica sin copiar su contenido. Un HTTP 403 puede ser un rechazo de acceso desde la primera petición: las pausas evitan ráfagas, pero no garantizan levantar ese bloqueo.
