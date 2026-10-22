# Historial de cambios

## Pendiente de publicación

- Quince entidades nativas de Home Assistant: datos de la lista principal y estimación de compra por cobertura de tienda, catálogo, categorías, stock bajo, último ticket, lectores y tiendas. Incluye interruptor, frecuencia y hora para la actualización de precios, y sensor binario del consentimiento comunitario. Se actualizan con datos locales y comparten los mismos ajustes que el panel.

- Listas pasarela en Ajustes → Listas: cada entidad todo envía las nuevas incorporaciones pendientes a una lista de compra vinculada, sin duplicados por acentos o mayúsculas. Permite conservarlas o eliminarlas del origen tras transferirlas, con reintentos, estado persistente y registro en Logs. Los productos anteriores a su configuración no se importan.

- Lectores pasa de la navegación principal a una vista de Ajustes, con el mismo icono y controles de configuración, activación y lectura en directo. La gestión de lectores en segundo plano se mantiene activa.

## 0.26.0

- Asistente de revisión de tickets en tres pasos: vinculación con el catálogo, reposición de stock y selección individual de precios. Permite crear productos con su ficha completa, ignorar líneas y guardar solo vinculaciones locales, independientes del stock y excluidas del diccionario comunitario.
- Un producto del catálogo solo puede vincularse a una línea del mismo ticket. El buscador excluye los ya asignados y Home Assistant valida la restricción antes de guardar.
- Los productos identificados que ya están en Stock vienen marcados para reponer; se pueden incorporar otros con cantidades y unidades confirmadas, sin sumar una unidad adicional al crearlos. Se conserva la corrección de reposiciones anteriores y el control de duplicados.
- Stock recupera el botón de añadir manualmente mediante un popup con nombres del catálogo y entrada libre. Retirado el título adicional; las vistas se alinean a la izquierda y sus controles a la derecha en una fila compacta. Subir ticket aparece solo en Últimas compras.

## 0.25.0

- Stock incluye las vistas Stock y Últimas compras, con subida local de tickets PDF electrónicos de Carrefour y revisión antes de confirmar. El historial conserva fecha, tienda, importe, descuentos generales y detalle de los productos; los escaneos y otros formatos todavía no están disponibles.
- Reposición con cantidades reales del ticket, conversión de unidades confirmada por el usuario, correspondencias aprendidas y detección de tickets duplicados. Permite corregir una reposición anterior sin volver a sumarla ni perder consumos posteriores, y evita duplicaciones si la compra se marca después de importar el ticket o durante la confirmación.
- Precios de tickets opcionales como último precio conocido por tienda, sin sobrescribir observaciones más recientes ni repartir cupones generales. Los tickets se procesan localmente y sus precios no se comparten con la comunidad; no se conserva el PDF original ni los datos de pago o fidelización.
- Retirados el buscador y su botón de añadir en Stock. Se conservan los controles de ordenación, lista, vista y subida de tickets; el buscador de Lista mantiene su funcionamiento.

- Popup Actualización de precios con interruptor global, frecuencia desde un día y hora inicial aleatoria persistente. Tiendas y diccionario respetan el periodo; desactivarlo detiene consultas de precios y oculta importes sin borrar el historial. Campos en filas con etiqueta izquierda y control derecho, y botón Guardar.
- Vistas de Ajustes en la misma fila del título, alineadas a la derecha, con navegación compacta y desplazamiento horizontal en pantallas pequeñas.
- Autorización comunitaria en un popup con código e instrucciones. Activar la casilla abre GitHub automáticamente desde la pulsación, conserva un enlace alternativo y cierra el popup al completar la autorización; puede reabrirse sin reiniciar el código.
- Lectores oculta la entidad o Device ID en sus tarjetas y muestra el último uso con formato dd/mm hh:mm. Si no existe una lectura registrada, muestra Último uso: —.
- Stock muestra cantidad y unidades en negrita seguidas del porcentaje entre paréntesis, en texto normal al 50 % de opacidad, en todos los modos de control.
- Stock se ordena de menor a mayor porcentaje por defecto. El criterio numérico compara todos los modos respecto a su cantidad de reposición, sin mezclar porcentajes con cantidades absolutas; los empates se resuelven alfabéticamente y se conserva la elección del usuario.
- En Lista, contador de productos en negrita al mostrar el ticket e importe aproximado en negrita en la vista normal.

## 0.24.0

- Activar Compartir mis datos solicita el envío inmediato del catálogo tras autorizar GitHub, aunque haya una revisión de precios en curso. Conserva el límite de un lote cada 24 horas y las pausas de reintento; las activaciones simultáneas se agrupan sin perder la solicitud.
- Consumo registrado muestra la barra de progreso en sus tarjetas, con la cantidad de reposición como 100 %, y simplifica su nombre en el selector de la ficha.
- Los botones Eliminar producto del stock y Guardar comparten el ancho del pie de su ficha a partes iguales, también en móvil.
- Porcentaje de Stock perecedero calculado como cantidad actual / cantidad de reposición (20 g de 250 g = 8 %), también para el mínimo de compra y la ordenación. La caducidad conserva su plazo independiente y pone el stock a cero al vencer. Caducidad y reposición comparten fila; la casilla y su mínimo también, incluido en móvil.
- En el ticket, cada tienda muestra el importe en negrita y el contador de productos entre paréntesis con un 60 % de opacidad.

## 0.23.0

- Comunidad explica el diccionario automático y sustituye el botón de exportación por la casilla de compartir datos, integrada en el mismo espacio e iniciando la autorización de GitHub al activarla.
- Stock perecedero con fondo de progreso descendente del tiempo restante y color de naranja a rojizo. Mínimo de reposición en porcentaje para perecederos y en unidades para el resto; orden alternativo por menor stock, controles de cantidad y unidad centrados y retirados los contadores generales y la ayuda de recurrencia.
- Ticket de compra con las cuatro tiendas de mayor cobertura en una fila, selección inicial por número de productos con precio y productos sin precio plegados. Badges de importe blanco y contador rojo al seleccionar el ticket; retirado el texto explicativo final.
- Protección de precios comunitarios: variaciones superiores al 50 % respecto al último precio aceptado quedan pendientes hasta recibir tres coincidencias independientes. Recuperación de un commit de datos mediante GitHub Actions, con revocación de precios sustituidos y restauración de la observación local anterior cuando exista.
- Votos compactados por elección y registro comunitario dividido en 16 archivos; límites de 8 MiB por archivo de registro y 16 MiB para el diccionario publicado. Las instalaciones no descargan el registro de votos ni el historial Git.
- Preferencias explícitas de iconos separadas de las confirmaciones independientes, para ordenar recomendaciones sin convertir datos copiados de la comunidad en nuevas verificaciones.
- Sincronización comunitaria con la GitHub App Improved Shopping List Community: consentimiento explícito en Ajustes → Comunidad, autorización mediante código, renovación de tokens y almacenamiento privado sin reutilizar credenciales de HACS.
- Diccionario único de productos en la rama `data`, con consulta diaria anónima, envío diario del catálogo permitido y recuperación de lotes fragmentados sin duplicarlos. Se excluyen listas, stock, NFC, lectores, categorías personales, notas y automatizaciones.
- Validación automática en GitHub Actions con identidad del autor comprobada, límite de un lote por cuenta cada 24 horas, consenso de tres cuentas, exclusión de datos copiados del diccionario, licencias de Iconify contrastadas y lista de bloqueo administrada desde el repositorio.
- Los precios comunitarios se utilizan por referencia exacta durante 24 horas, conservan su fecha original y evitan consultar de nuevo la tienda. El primer precio válido permanece hasta caducar. Se completan traducciones y vinculaciones confirmadas que falten sin sobrescribir elecciones locales; los iconos comunitarios aparecen primero.
- Centros fijos de referencia para todas las tiendas. Retirado el botón y popup del código postal; las instalaciones anteriores migran conservando tiendas activas, favorita, listas y preferencias, sin reutilizar los errores de cobertura de la ubicación anterior.
- Habilitar tiendas ya no consulta la cobertura. Consum utiliza el centro 301 de 46409; las consultas de productos siguen respetando las pausas y los bloqueos del servidor. Los precios de otros centros permanecen guardados con su ámbito original y no se mezclan con los de referencia.

## 0.22.0

- Actualizar ahora vuelve a abrir la revisión activa sin reiniciar ni ampliar la cola, incluso después de una recarga, durante la preparación o mientras hay una petición en curso. La protección se aplica también en Home Assistant si el navegador todavía no ha recibido el estado inicial.
- Guardado confirmado e idempotente del resumen final de precios en Logs, con recuperación tras fallo de almacenamiento o reinicio y protección frente a iniciar otro lote antes de guardarlo. Las referencias bloqueadas por una tienda se descartan sin esperar otros cinco minutos.
- El progreso conserva el estado de revisión finalizada después de recargar, diferencia el resumen pendiente del ya guardado y permite volver a abrir una revisión en curso sin solicitar otra.
- Recurrencia del catálogo y modo Perecedero de Stock coordinados en ambos sentidos, con los mismos días y un único temporizador. Al vencer se pone el stock a cero y se solicita compra sin duplicados; al comprar se suma la reposición configurada y se reinicia el plazo. Se conservan cantidades, preferencias y vencimientos anteriores, y las ediciones pendientes se recuperan tras fallos de almacenamiento o reinicios.
- Los cuatro colores de Personalización comparten una fila: los de pendientes a la izquierda y los de comprados a la derecha, encima de la vista previa correspondiente.
- Retirado el mensaje final «No hay sugerencias nuevas en esta lista» de Catálogo → Nuevos.
- Vistas Productos, Categorías y Nuevos alineadas a la derecha del título Catálogo en la misma fila, también en móvil.
- Buscador del catálogo sin rótulo visible y controles compactos a su derecha en una sola fila también en móvil, conservando el nombre accesible del campo.
- Nuevo criterio «Vinculados» para agrupar el catálogo por tienda. Los productos con varias vinculaciones aparecen en cada tienda correspondiente; los que no tienen ninguna se reúnen en «No vinculados». Compatible con búsqueda, cuadrícula, filas y preferencia guardada, incluso con tiendas desactivadas.
- Vista de ticket al pulsar el importe estimado de la lista: tiendas activas con precios guardados, ordenadas por total conocido, selección de tienda, productos en orden alfabético y separación de productos sin precio. El badge muestra el logo de la tienda seleccionada; el número de productos permite volver a la vista habitual sin cambiar su formato.
- Totales calculados con los últimos precios guardados, sin actualizar tiendas, indicando la cobertura de precios de cada tienda y conservando el importe 0 para los productos sin precio.

## 0.21.0

- Actualizaciones de precios agrupadas en una única entrada final de Logs, con totales, resultados por tienda, referencias, incidencias y diagnóstico técnico. La información del proceso se conserva entre reinicios; la barra de progreso sigue actualizándose en directo.
- Las tiendas sin referencias pendientes no comprueban cobertura. Los nuevos intentos revisan los errores de ubicación guardados en lugar de quedar bloqueados; se conserva el diagnóstico HTTP y se distingue falta de cobertura de un rechazo de red. Avisos sin nombres de tienda repetidos.
- Unificado el fondo rojo de los botones de eliminar en toda la interfaz, incluidos códigos, vinculaciones, listas, lectores, sugerencias, limpieza de compras recientes y confirmaciones.
- Stock pasa a situarse entre Catálogo y Lectores. Cada tarjeta abre una ficha con cantidades decimales, unidades estándar o personalizadas y eliminación con confirmación; retirados los botones de carrito y eliminar de las tarjetas. Los controles rápidos de cantidad solo aparecen en filas.
- Control manual/con lectores, caducidad de perecederos y consumo registrado mediante entidad y estado de Home Assistant. La caducidad pone el stock a cero y solicita reposición; cada uso descuenta la cantidad configurada sin contar arranques ni recuperaciones de disponibilidad.
- Cantidad de reposición configurable al marcar la compra, umbral de stock y lista de destino por producto. Se conservan las cantidades y preferencias existentes, se evitan duplicados en las listas y se registran los movimientos automáticos en Logs.

## 0.20.0

- Nuevo apartado Stock, con inventario común persistente, búsqueda predictiva, cantidades por producto, vistas de cuadrícula y filas, degradado naranja y envío a la lista de compra seleccionada sin duplicados.
- Las acciones de lectores para sumar y restar stock ya modifican el inventario, con protección antirrepetición y registro de movimientos.
- Códigos de barras/QR y NFC en líneas capturadas desde lectores, sin campos manuales. La captura temporal no ejecuta acciones habituales y se libera al cerrar o desconectarse.
- Las acciones de cada producto heredan las del lector salvo excepción elegida por el usuario. Eliminados los badges de categoría de las tarjetas del catálogo.

- Tiendas muestra un badge con el número de productos vinculados y el icono de carrito; al pulsarlo se abre directamente su listado de precios guardados, incluso si la tienda está desactivada. Retiradas las pestañas Productos y Configuración de los siete popups.
- Reparación automática de ubicaciones incompletas antes de actualizar precios manualmente o en la revisión diaria. Si no se indica código postal común se resuelven las ubicaciones predeterminadas, incluidas Consum 46409 y Eroski 48001; los códigos indicados por el usuario se respetan.
- Carrefour admite referencias `R-prod…` cuyo identificador numérico de analítica es diferente de la referencia interna. Se mantiene la comprobación de identidad única y se amplía el diagnóstico de respuestas no coincidentes.
- Fichas sin campos de precio orientativo ni moneda. Las vinculaciones se añaden con + o Enter, muestran logo y nombre de la tienda junto al enlace y usan un botón rojo para eliminar. Se conservan los precios manuales anteriores al editar.
- Personalización sitúa los selectores de productos por fila debajo de las vistas previas. Ajustes → Listas elimina el texto explicativo y la etiqueta Principal redundante; el botón amarillo identifica la lista principal.
- Código postal con texto simplificado y cierre automático tras guardar, sin aviso de confirmación. Retirado el contador de productos del catálogo.
- Pruebas ampliadas de Stock, lectores, captura de códigos, ubicaciones predeterminadas, referencias de Carrefour, vinculaciones con Enter y presentación móvil y de escritorio.

## 0.19.0

- Código postal común para todas las tiendas desde un nuevo botón de ubicación junto al reloj de Ajustes → Tiendas. Se comprueban las tiendas activas al guardar; las desactivadas lo usan al habilitarlas. Eliminados los campos de ubicación independientes de los popups.
- Resolución automática del almacén de Mercadona, centro de Carrefour y región de Alcampo. Alcampo utiliza una sesión anónima temporal y el token CSRF que proporciona su web; verificado con el código postal 28024, sin guardar cookies ni tokens ni usar cuentas de usuario.
- Sin código postal se usan ubicaciones de referencia indicadas en el popup. Si se indica uno y falla una tienda, se muestra el error, se conservan los precios anteriores y no se consulta una ubicación diferente. Cambiar la ubicación no actualiza los precios.
- Ajustes → Listas con botón rojo de eliminar y estrella para seleccionar una única lista principal, resaltada en amarillo. Vistas previas de productos pendientes y comprados en la misma fila en Personalización.
- Más espacio bajo el título del popup de agrupación del catálogo.
- Pruebas de ubicación común, sesiones anónimas, persistencia, permisos, errores de cobertura, conservación de caché e interfaz móvil y de escritorio.

## 0.18.0

- Nuevas tiendas Consum, La Sirena, Eroski y DIA, con configuración por código postal, logos y precios separados por ubicación. Se integran en la revisión diaria y manual de los productos pendientes, conservando el último precio conocido ante errores.
- Consum y La Sirena admiten enlaces o ID; La Sirena comprueba la variante y el precio de entrega del centro elegido. Eroski utiliza una sesión anónima propia y selección de centro de recogida; necesita el enlace completo de la ficha. DIA admite enlaces o ID y utiliza urllib estándar en el executor de Home Assistant para realizar las consultas que recibían 403 con aiohttp. No requieren cuentas ni claves; todas las peticiones de precios respetan cinco minutos de separación.
- Retirado Lidl de las tiendas y las consultas. La migración conserva los productos, códigos de lectores, listas y datos de las demás tiendas.
- Catálogo con orden alfabético o agrupación por categoría o Nutri-Score. El selector de categorías se sustituye por los controles de agrupación.
- Lectores con acción por defecto y posibilidad de sobrescribirla en cada producto. El estado activo se maneja desde el toggle de la tarjeta; retirado el acceso directo a sugerencias. Las acciones de stock siguen reservadas para un desarrollo posterior.
- Logs pasa a ser una vista de Ajustes. Popups de tiendas con navegación uniforme de Productos y Configuración; retirados los contadores de las tarjetas. Se evita preparar una revisión nocturna cuando todas las tiendas están desactivadas.
- Pruebas ampliadas de interfaz, permisos, selección regional, sesiones anónimas, ejecución sin bloquear Home Assistant, caché, migraciones y pausas de actualización.

## 0.17.0

- Lidl en Ajustes → Tiendas, con selección de región, tienda favorita y vinculaciones por enlace o ID en las fichas de productos. Consulta su API pública sin cuenta, cookies ni claves y utiliza el precio general vigente de la región elegida, excluyendo ofertas futuras y precios exclusivos de Lidl Plus. Respeta la cola de productos pendientes y los cinco minutos entre peticiones; conserva el último precio conocido y señala las ofertas finalizadas. Verificado desde desarrollo con la referencia 11107037 para Madrid: 2,89 EUR.
- Importe aproximado junto al contador de la lista de la compra, calculado con los últimos precios guardados, sin consultas externas. Los productos sin precio cuentan como cero.
- Filas de Lista con nombres alineados a la izquierda, logo de la tienda en el precio y badge de Nutri-Score. En móvil, la categoría muestra solo su icono. Catálogo adopta la misma alineación y limita el botón de editar a la vista de filas.
- Fichas de productos y categorías sin botón Cancelar; Eliminar aparece junto a Guardar y sigue solicitando confirmación. Texto de recurrencia simplificado.
- Popups de tiendas con precios guardados accesibles aunque estén deshabilitadas, contador en el pie y sin botones individuales de actualización ni Cerrar. Tiendas ordenadas alfabéticamente, menos opacidad al deshabilitarlas y fondo verdoso al activarlas. Ajustado el espaciado del horario de revisión.
- Logo local de Mercadona aportado por el usuario y logo local de Lidl. Botones de Comunidad con iconos más pequeños y contenido alineado a la izquierda.
- Pruebas ampliadas de Lidl, selección regional, vigencia, identidad de productos, consultas anónimas, permisos, caché, pausas y presentación de la interfaz.

## 0.16.0

- Nueva vista de filas en Lista y Catálogo → Productos, alternable con la cuadrícula y recordada en el navegador. Muestra imagen o icono, nombre, categoría y último precio guardado; prioriza la tienda favorita, después el precio más reciente de otras tiendas y finalmente el precio manual. No provoca consultas a los supermercados. Se mantienen las acciones de compra y edición.
- En el catálogo, los botones de añadir producto y cambiar vista se sitúan a la derecha del selector de categorías. Retirado el botón de actualizar catálogo y renombrada la vista Sugerencias como Nuevos.
- Alcampo utiliza las cabeceras anónimas verificadas de su API pública para corregir el rechazo HTTP 403 observado. Comprobado desde desarrollo con el producto 10739: precio, disponibilidad y EAN. Conserva la región configurada, los intervalos y el último precio ante errores; el acceso desde Home Assistant debe verificarse en cada instalación.
- La eliminación de productos y categorías se realiza desde el final de sus fichas, con confirmación. Retirados los botones de eliminar de las tarjetas; borrar un producto del catálogo conserva los elementos de las listas.
- Tiendas abre el progreso de actualización en un popup y permite configurar la hora diaria desde un botón de reloj. Dos tiendas por fila en pantallas grandes, nuevos logos y última actualización en el pie.
- Comunidad incorpora los textos revisados, botón negro de Patreon y botones de igual ancho con iconos Font Awesome del mismo tamaño.
- Pruebas ampliadas de consultas de Alcampo, precios guardados, cambio de vistas, controles del catálogo, edición, eliminación y presentación en móvil y ordenador.

## 0.15.0

- Carrefour consulta precios mediante el endpoint JSON de su web, con referencia y centro `sale_point`, sin cookies ni identificadores de sesión. Sustituye la descarga de HTML que devolvía 403. Verificado desde desarrollo con HTTP 200 y 2,69 EUR para la referencia 491998, tanto con enlace como con ID; el acceso desde cada Home Assistant sigue dependiendo de la tienda.
- Nueva vista Configuración en el popup de Carrefour para guardar un centro de seis dígitos, inicialmente `005290`. Se conservan los ceros iniciales y la selección al activar o desactivar la tienda. Las cachés quedan separadas por centro y se descartan respuestas tardías de una configuración anterior.
- Validación de referencia y precio en EUR antes de guardar. Los EAN recibidos son metadatos y no cambian los códigos del lector. Las respuestas vacías, ambiguas o inválidas y los errores conservan los precios anteriores. Logs → Tiendas registra cuándo comienza una consulta, diferenciándola de la cola.
- Un único botón Actualizar ahora en la cabecera de Tiendas revisa las tiendas activas, solo para productos vinculados pendientes en las listas. Retirados los botones individuales y las confirmaciones de referencias en cola. Se mantienen las pausas de cinco minutos y los errores visibles.
- Fecha de la última actualización correcta a la izquierda del botón, en formato dd/mm hh:mm y zona horaria de Home Assistant, actualizada en directo. Icono de actualizar dentro del botón.
- Comunidad añade el icono de descarga a Exportar mis iconos y un botón azul de Telegram para unirse a la comunidad en una nueva pestaña.
- Pruebas ampliadas de consulta JSON sin credenciales, coincidencias de producto, centros, persistencia, caché, permisos e interfaz.

## 0.14.0

- Botón Actualizar ahora en cada tienda para revisar los precios de sus referencias vinculadas pendientes en las listas, incluso si ya se consultaron hoy. Respeta los cinco minutos entre peticiones y las pausas indicadas por la tienda, evita duplicar una cola activa y conserva los precios anteriores ante errores.
- Contador de productos del catálogo vinculados a cada tienda junto a su interruptor. Nombres centrados verticalmente y nuevo logo de Alcampo.
- Selección de una única tienda favorita mediante corazones a la derecha del engranaje: corazón rojo relleno para la favorita y contorno para las demás. Retirados el desplegable y el texto Favorita.
- Selector de tienda, enlace o ID y botón de añadir en una sola fila de la ficha del producto, con alturas iguales, icono centrado y flecha del desplegable separada del borde. Retirados los textos explicativos indicados de la ficha y de Ajustes → Tiendas.
- Pruebas ampliadas de actualización manual, permisos, deduplicación, pausas, recuperación tras reinicio, conservación de precios, selección de favorita e interfaz móvil.

## 0.13.0

- Vinculaciones por enlace o ID con Mercadona, Carrefour y Alcampo en Información adicional del producto, sin exigir EAN. Los códigos de los lectores se conservan de forma independiente.
- Actualización diaria desde Home Assistant a las 01:00 por defecto, con horario configurable y un mínimo de cinco minutos entre peticiones. Solo se consultan productos pendientes en las listas configuradas; las referencias compartidas se consultan una sola vez.
- Cola y pausas persistentes tras reiniciar, comprobación de productos todavía pendientes y recuperación de listas temporalmente no disponibles. Se conserva el último precio conocido para todo el catálogo ante compras, retiradas de la lista o errores.
- Retirados el feed de Carrefour en GitHub y su dependencia de Aguacatec. Las referencias anteriores y sus precios guardados se recuperan cuando están disponibles. Abrir las fichas o actualizar su vista solo consulta datos guardados.
- Alcampo permite configurar una región opcional. Progreso de la revisión nocturna en directo y diagnóstico en Logs; los errores 403/429 pausan la tienda sin borrar precios. Los 403 observados en Alcampo y Carrefour durante las pruebas siguen siendo una limitación del acceso externo.
- Logo de Carrefour y separación entre los bloques de tiendas. Botón de cierre en los popups y ajustes de textos, vistas y presentación de precios.
- Pruebas ampliadas de vinculaciones, conservación de precios, horario, permisos, recuperación tras reinicio, respuestas tardías e interfaz móvil.

## 0.12.0

- Carrefour en Ajustes → Tiendas, con activación independiente y selección de tienda favorita cuando hay varias habilitadas. Su popup muestra los productos del catálogo con coincidencia exacta de EAN, precio, moneda y enlace original de afiliado.
- Precios de Carrefour en Información adicional de la ficha del producto, con fecha de publicación y aviso cuando se conserva una descarga anterior. No sustituyen el precio manual ni el Nutri-Score de Open Food Facts. El feed no tiene precios por código postal.
- Consulta diaria de un catálogo de cinco campos alojado en la rama de datos de GitHub, sin credenciales de Awin o GitHub en Home Assistant. Utiliza ETag, deltas y descarga completa de recuperación, valida la integridad y conserva la última copia válida ante errores. Actualizar los precios no requiere nuevas versiones de HACS.
- Exportador validado, publicador atómico y enlace de referencia con Aguacatec para preparar la descarga periódica del feed. La disponibilidad de precios requiere configurar y publicar ese catálogo desde Aguacatec; esta versión no activa el servidor ni publica datos reales por sí sola.
- Mercadona continúa automáticamente todos los códigos del lote tanto en revisiones manuales como automáticas, manteniendo las pausas entre peticiones. Los puntos internos de continuación ya no requieren volver a pulsar el botón. Barra de progreso más gruesa y visible durante ambas revisiones.
- Pruebas ampliadas de exportación limitada a los cinco campos, validación de códigos, deltas, integridad, conservación de precios, permisos, selección de favorita y precios en la ficha del producto.

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
