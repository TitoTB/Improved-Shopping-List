# Historial de cambios

## 0.11.1

- Sustituida la búsqueda de Mercadona que devolvía HTTP 403 por Algolia, la alternativa incluida en su cliente web público. No requiere cuenta, claves del usuario ni asociaciones manuales. Se buscan candidatos por el nombre del catálogo y, cuando ya está guardado, por el nombre comercial de Open Food Facts; cada referencia se comprueba en la API directa y solo se incorpora si coincide exactamente el EAN.
- Las consultas correctas sin coincidencias se muestran como resultados sin coincidencia, sin errores ni penalización. Un código sin revisar o con una búsqueda incompleta no se considera no encontrado. La comprobación se limita a los candidatos obtenidos; no prueba la ausencia del producto en toda la tienda.
- Búsquedas paginadas con avance persistente, caché de fichas por almacén y continuación de lotes sin reiniciar los códigos ya revisados. Las referencias identificadas actualizan su precio directamente y vuelven a verificar su EAN. Se mantienen cinco segundos entre peticiones y el progreso en directo incluye las referencias comprobadas.
- Una pausa guardada del antiguo buscador no bloquea al proveedor nuevo. Los errores de las consultas actuales conservan los precios previos y sus pausas de reintento; después de un 403, abrir el popup no vuelve a consultar automáticamente ni alarga la espera.
- Verificado con consultas reales desde el entorno de desarrollo: coincidencia exacta para 8430543025611 y resultado sin coincidencia para 8721201901058. El acceso sigue dependiendo de los servicios externos y debe comprobarse desde cada Home Assistant.
- Pruebas ampliadas de coincidencias exactas, ausencia de candidatos, referencias ambiguas, paginación, continuación tras reinicio, migración de pausas, cambios de configuración y errores HTTP.

## 0.11.0

- Recurrencia en Automatización de la ficha del producto: permite comprar cada X días en la lista principal. Funciona con el panel cerrado, conserva el calendario tras reiniciar, evita duplicados pendientes y recupera entradas completadas cuando el proveedor lo permite. Registra los resultados y los errores en Logs.
- Mercadona respeta un mínimo de cinco segundos entre todas las peticiones, incluidas las búsquedas alternativas por nombre, igualando la pausa del flujo original de n8n.
- Ante errores de Mercadona se conserva el precio anterior y se pausa progresivamente la consulta: inicialmente 15 minutos para HTTP 403, cinco minutos para HTTP 429 y un minuto para otros errores, respetando esperas mayores indicadas por el servidor. La pausa persiste tras reiniciar y bloquea el botón manual hasta la hora indicada.
- Barra de progreso en directo al forzar la actualización: códigos revisados, estado de búsqueda y tiempo estimado del lote. Se mantienen los lotes de hasta 20 códigos y unos 35 segundos; un error o un lote parcial no se presenta como revisión completa.
- Nuevo filtro Tiendas en Logs e información técnica desplegable de consultas, errores y reintentos: estado HTTP, almacén, EAN, tiempos y referencias de bloqueo disponibles, sin conservar cuerpos de respuesta, cookies ni credenciales. Un HTTP 403 sigue siendo un rechazo de acceso del servicio externo; las pausas no garantizan que Mercadona permita consultar su buscador.
- Sugerencias de iconos en una sola fila adaptable e iconos representativos en las vistas de la ficha del producto.
- Comunidad incluye el enlace al repositorio para aportar diccionarios mediante Issues y los enlaces de Telegram y Patreon de Aguacatec. Texto de exportación y botón alineados en una fila.
- Engranaje de tiendas sin contenedor visible y logos con mayor padding sobre fondo blanco, adaptado a móvil.
- Pruebas ampliadas de recurrencia, antirrepetición, pausas persistentes, diagnóstico seguro, progreso WebSocket en directo, permisos y presentación móvil.

## 0.10.0

- Tiendas se presenta en bloques horizontales con logo, nombre, interruptor y engranaje. Mercadona utiliza el logo indicado y abre un popup con las vistas Productos y Configuración.
- Consulta de productos del catálogo con EAN/GTIN válido coincidente exactamente con Mercadona, mostrando precio, referencia, disponibilidad y fecha de consulta por almacén. Caché de seis horas, lotes de hasta 20 códigos y actualización manual para administradores. No sustituye el precio manual de las fichas ni ejecuta consultas periódicas en segundo plano.
- Los errores de consulta conservan los precios anteriores y aplican una espera antes de reintentar. La prueba real desde el entorno de desarrollo devuelve HTTP 403 de Mercadona; la conectividad debe comprobarse desde Home Assistant. No se garantiza el acceso al buscador externo.
- Configuración de código postal en el popup, también con la tienda deshabilitada, conservando los ajustes ante errores.
- Botón azul para vincular códigos escaneados. Abre un popup con buscador predictivo sin diferencias de tildes o mayúsculas y botones Asignar y Cancelar. Solo Asignar guarda el código; conserva los demás datos y acciones del producto y no ejecuta lecturas pasadas.
- Icono de papelera delante de Limpiar productos en Compras recientes.
- Eliminado el espacio reservado por sugerencias de iconos vacías. Actualizado el texto de procedencia y retirado el botón Buscar en Flaticon.
- Pruebas ampliadas de interfaz móvil, configuración, selección predictiva, persistencia de precios, coincidencias de EAN, permisos y errores externos.

## 0.9.1

- Botón azul con `mdi:eye-outline` a la izquierda de Editar en cada lector. Abre la información de su entidad en el popup nativo de Home Assistant, con el estado actualizado en directo.
- Los lectores NFC basados en eventos, sin entidad propia, muestran un popup con código, producto identificado, resultado y hora de la última lectura, actualizado en directo.
- La consulta está disponible también para usuarios sin permisos de administración. Pruebas de apertura desde el panel, actualizaciones de lecturas y presentación segura de los códigos.

## 0.9.0

- Nueva vista Ajustes → Tiendas con Mercadona. Permite habilitarla, consultar por código postal el almacén asignado y conservarlo tras reiniciar. La tienda habilitada queda como favorita. Los errores conservan la configuración anterior; no se asignan almacenes por defecto. Solo los administradores pueden cambiarla. Esta versión prepara la configuración; todavía no consulta precios ni vincula referencias de Mercadona con productos del catálogo.
- Nutri-Score de Open Food Facts en Información adicional cuando existe para un código de barras válido, con caché, procedencia y resultados separados si hay varios códigos.
- Ficha de producto dividida en Características principales, Información adicional y Automatización. Retirados los campos Etiquetas, Icono y Notas del formulario, conservando sus datos antiguos.
- Ajustes → Comunidad permite exportar un ZIP con el diccionario de iconos local para revisión del mantenedor. Las sugerencias del diccionario comunitario de GitHub se muestran antes de Iconify, por aportaciones revisadas; no hay envíos automáticos ni recuento de usos globales.
- Hasta cinco sugerencias automáticas de iconos a color y un botón + para recorrer alternativas, junto con búsqueda manual en Flaticon por nombre. Cuando no hay resultados se oculta + y se indica que puede escribirse otro término o una URL.
- Botón Limpiar productos junto a Compras recientes para eliminar los completados de la lista seleccionada, si el proveedor lo permite.
- Corregido el centrado de las acciones de categorías y unificado su estilo con las tarjetas de productos. Iconos representativos en las vistas de Ajustes. Ocultadas las confirmaciones de éxito en Catálogo → Productos.
- Pruebas ampliadas de interfaz, permisos, persistencia, exportación, consultas externas y respuestas tardías.

## 0.8.1

- Iconos y círculos de categoría más grandes en los productos de Lista, conservando el formato circular, la sombra y el escalado adaptable.
- El botón «+» de las sugerencias de iconos muestra otras tres propuestas en los mismos contenedores, sin abrir páginas externas. Reutiliza los resultados disponibles y carga más cuando hace falta, sin saltarse opciones entre lotes.
- Campo «URL Imagen/Icono» junto a las sugerencias para indicar una imagen propia. La URL escrita manualmente se respeta aunque termine después una descarga de icono pendiente.
- Pruebas ampliadas de navegación entre iconos, recuperación tras errores y guardado de imágenes manuales.

## 0.8.0

- Nuevo apartado Logs (`mdi:format-list-group`), con historial persistente de las últimas 1.000 entradas, búsqueda y filtros por actividad y origen. Registra cambios reales de listas, compras y recuperaciones, catálogo, categorías, configuración y uso de lectores; identifica automatizaciones cuando Home Assistant conserva el contexto y muestra los orígenes desconocidos como tales.
- Sugerencias de iconos directamente en la ficha, debajo del nombre del producto, sin botón ni popup adicional. Se actualizan automáticamente al escribir, agrupan las pulsaciones y muestran tres propuestas a color sin nombres visibles y un cuarto bloque `+` que abre la búsqueda completa en Iconify en otra pestaña o ventana.
- Corregida la búsqueda de productos antiguos sin traducción: se obtiene y guarda el nombre inglés al mostrar sus sugerencias, sin exigir guardar otra vez ni provocar conflictos con la ficha abierta. Las búsquedas escritas manualmente se respetan.
- Selección de imágenes con protección frente a respuestas tardías y bloqueo de Guardar mientras se descarga el icono. Las imágenes y su atribución siguen guardándose en Home Assistant.
- Añadir desde Catálogo no muestra mensajes de confirmación y bloquea las tarjetas de productos ya pendientes. Antes de añadir se comprueba el contenido actual, se agrupan pulsaciones equivalentes y se recupera por identificador una entrada comprada para evitar duplicados.
- Texto «Por comprar» sustituido por «Lista de la compra» y «Comprados» por «Compras recientes» en la vista Lista.
- Productos del catálogo con el botón de editar siempre naranja/amarillo y el contenido centrado verticalmente sin reservar espacio para las acciones. Botones de editar y eliminar categorías juntos en la esquina superior derecha.
- Pruebas ampliadas del historial, persistencia y orígenes, traducción y selección automática de iconos, duplicados y disposición móvil.

## 0.7.0

- Traducción automática del nombre del producto del español al inglés mediante MyMemory al guardar la ficha. La traducción se conserva en Home Assistant y se reutiliza para buscar iconos; se actualiza al cambiar el nombre. Los fallos o límites del servicio no impiden guardar el producto.
- Al corregir el nombre de un producto desde Sugerencias, se actualiza también en la lista original, conservando su estado y demás datos. Los errores del proveedor permiten reintentar sin duplicar la ficha del catálogo.
- Coincidencias de productos y descartes sin distinguir tildes, mayúsculas, caracteres equivalentes ni espacios sobrantes.
- Tarjetas cuadradas en Catálogo → Productos: pulsar el bloque añade a la lista; los controles circulares permiten editar con el color de la categoría o eliminar con fondo negro y confirmación.
- Tarjetas y botones de categorías cuadrados, con un máximo de cinco columnas en ordenador y dos en móvil.
- Nombres de productos más grandes y con el mismo tamaño en Lista y Catálogo. Distintivos de categoría de Lista circulares, sin borde, con sombra e icono centrado.
- Pestañas del catálogo compactas en móvil: solo la vista activa muestra texto, conservando los iconos de las demás vistas.
- Pruebas ampliadas de persistencia de traducciones, errores y cuotas, corrección de nombres, eliminación de productos y disposición de tarjetas y pestañas.

## 0.6.0

- Buscador gratuito de iconos de Iconify desde la ficha del producto, sin clave API: cinco alternativas por página, búsqueda editable y navegación entre resultados. Los términos no se traducen automáticamente.
- Guardado local del icono seleccionado, con autor, colección, procedencia y licencia. Los archivos elegidos siguen disponibles sin Internet y tras reiniciar Home Assistant.
- Cabecera móvil compacta: logo de la integración y nombre del apartado activo; los demás apartados muestran solo su icono.
- Vistas del catálogo con los iconos mdi:view-grid para Productos y mdi:label para Categorías.
- Imágenes, iconos y nombres del catálogo adaptados al número de columnas, siguiendo el escalado de la lista.
- Distintivos de categoría del catálogo circulares, sin borde, con sombra e icono centrado.
- Botones de editar en amarillo/naranja y de eliminar o descartar en rojo, sin bordes. Las acciones de cada categoría permanecen en una sola fila incluso en tarjetas estrechas.
- Interruptores de lectores con fondo rojo cuando están apagados y verde cuando están encendidos.
- Corregido el contraste automático que mostraba en negro los productos comprados: el degradado predeterminado mantiene texto e iconos blancos, también en la vista previa de Ajustes.
- Nuevas pruebas de búsqueda y descarga de iconos, almacenamiento, permisos de acceso, respuestas tardías y disposición de tarjetas en móvil y ordenador.

## 0.5.0

- Consulta de códigos de barras desconocidos en Open Food Facts para sugerir un nombre y posibles coincidencias con productos del catálogo, con caché y límites de consultas. La incorporación o asociación requiere confirmación.
- Sugerencias agrupadas en productos de la lista y productos escaneados, con secciones plegadas inicialmente y acciones mediante iconos.
- Tarjetas cuadradas de la lista con tamaño de imagen, icono y nombre adaptado al número de columnas. Catálogo y categorías comparten la configuración de columnas de Ajustes.
- Productos del catálogo incluidos en la lista con el mismo degradado configurado para los pendientes y texto e iconos blancos.
- Icono de categoría como alternativa para los productos sin imagen ni icono propio; distintivos del catálogo con sombra y de la lista con borde blanco.
- Botones de productos y categorías solo con iconos, navegación con iconos y barra de acciones alineada a la derecha. Eliminado el filtro de etiquetas.
- Creación de categorías desde la ficha de un producto, conservando los datos introducidos.
- Eliminados los campos Marca y Formato de los productos, con migración de los datos anteriores.
- Lectores con icono de tipo, nombre y entidad centrados, interruptor de activación y tiempo desde el último uso. Acceso directo a Sugerencias y acciones solo con iconos.
- Ampliadas las pruebas de interfaz, permisos, consultas externas y migración del catálogo.

## 0.4.1

- Corregido un error de compatibilidad con Home Assistant que interrumpía el arranque del panel, dejaba Ajustes cargando e impedía mostrar las listas y sus productos.
- Pruebas de interfaz con la misma capa de compatibilidad de elementos personalizados utilizada por Home Assistant, incluyendo carga de listas, personalización y operaciones de compra.

## 0.4.0

- Nuevo apartado Lectores para configurar lectores de códigos de barras, QR y NFC mediante entidades de Home Assistant o eventos de etiquetas NFC.
- Asociación de varios códigos a cada producto y selección de una acción por producto y lector, con lista de destino configurable y la principal por defecto.
- Protección contra lecturas repetidas, sin duplicar productos pendientes y recuperando los comprados cuando el proveedor lo permite.
- Códigos desconocidos como sugerencias para crear un producto o asociarlos a uno existente, con descartes persistentes.
- Acciones de añadir o quitar stock disponibles para configurar; su ejecución queda pendiente de implementar el inventario.
- Personalización de los degradados de productos pendientes y comprados y del número de columnas en móvil y ordenador.
- Tarjetas de la lista que cambian entre pendiente y comprado al pulsarlas, sin botones interiores.
- Alta desde sugerencias mediante la ficha completa del producto y botones Añadir y Editar del catálogo con texto más pequeño y el mismo ancho.
- Filtro de categoría al pulsar su icono en las tarjetas del catálogo.
- Eliminado el texto introductorio de la vista Lista.

## 0.3.0

- Nuevo apartado Ajustes (`mdi:cog`) para añadir entidades `todo`, quitar listas de la interfaz y elegir una principal, con configuración compartida y persistente en Home Assistant.
- Barra compacta en Lista con buscador predictivo, botón de añadir (`mdi:plus-thick`) y popup de selección de listas (`mdi:format-list-checks`).
- Búsqueda predictiva en el catálogo por nombre, marca, código de barras o etiquetas, con selección mediante teclado o toque.
- Productos de Lista y Catálogo en cuadrícula, con imagen o icono y nombre centrados, icono `mdi:shopping` por defecto y distintivo de categoría con su color.
- Gestión de categorías: crear, editar y eliminar, asignando icono MDI y color. Se conservan los productos al quitar una categoría.
- Vista Sugerencias (`mdi:creation`) para incorporar rápidamente al catálogo productos de la lista seleccionada, con descartes persistentes y sin repetir nombres.
- Degradado rojo para productos pendientes en la lista seleccionada y precio oculto en las tarjetas, manteniendo los datos guardados.
- Catálogo compartido sin selector de listas, botones Añadir y Editar con sus iconos y eliminación de los textos auxiliares solicitados.
- Migración de categorías y listas de instalaciones anteriores, sincronización entre sesiones y comprobaciones de permisos en Ajustes.

## 0.2.0

- Cabecera con logo, título y versión juntos, sin un fondo diferente al del panel.
- Navegación a la derecha entre Lista y Catálogo, con el icono `mdi:view-grid`.
- Catálogo local compartido, guardado en el almacenamiento de Home Assistant.
- Alta y edición de productos con categoría, etiquetas, marca, formato, código de barras, precio orientativo, moneda, imagen mediante URL y notas.
- Búsqueda y filtros por categoría y etiqueta.
- Añadir productos del catálogo a la entidad `todo.*` seleccionada.
- Actualizaciones del catálogo entre sesiones y detección de ediciones simultáneas.

## 0.1.2

- Icono `mdi:shopping` para el acceso al panel desde el menú lateral.

## 0.1.1

- Logo propio de la integración, incluido localmente para Home Assistant.
- Logo en la cabecera del panel y en la documentación del repositorio.
- Se conserva el archivo original facilitado por TitoTB.

## 0.1.0

- Primera versión de la integración Improved Shopping List.
- Configuración visual para seleccionar una entidad `todo.*` existente.
- Panel propio en español, adaptado a móvil y accesible desde la barra lateral.
- Selección de lista, consulta de productos pendientes y comprados, alta de productos y cambio de estado.
- Actualización del panel mediante las suscripciones nativas de Home Assistant.
- Controles adaptados a las operaciones que admite cada proveedor.
- Estructura de instalación para HACS y publicación de versiones mediante etiquetas Git.

Esta versión todavía no incluye lector de códigos, catálogo propio, precios ni procesamiento de PDF.
