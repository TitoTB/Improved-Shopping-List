# Catálogos de tiendas

En Ajustes → Tiendas → Catálogos, Alcampo está desactivado por defecto. Activarlo utiliza las coincidencias exactas de EAN del diccionario público para añadir opciones de Alcampo a los productos del catálogo y recuperar sus datos desde la ficha oficial.

El proceso muestra un popup con progreso, producto actual e incidencias. Continúa en Home Assistant al cerrar el popup o recargar la página; el botón de progreso permite consultarlo de nuevo. No reinicia una revisión que ya está en curso.

El resumen de Logs → Tiendas conserva los detalles técnicos de cada incidencia: referencia, URL, fase de consulta (ficha o API), código HTTP y motivo de rechazo o falta de datos. Una página sin datos estructurados no se identifica automáticamente como un bloqueo por frecuencia. Los bloqueos confirmados detienen el lote y conservan la pausa de reintento.

Las peticiones automáticas se separan al menos veinte segundos, incluidas las redirecciones y consultas complementarias de una misma ficha. La reserva se guarda antes de cada petición y se conserva tras reiniciar. Se reutiliza la caché del recuperador y se respetan las pausas ante bloqueos. Los datos recuperados correctamente no se vuelven a consultar en cada cambio del catálogo. Las coincidencias nuevas se procesan automáticamente mientras la opción siga activada.

Se conserva la URL introducida manualmente y no se reactiva una opción que el usuario haya desvinculado. El EAN devuelto por la web, cuando existe, debe coincidir. El enlace del diccionario ya se ha verificado por EAN; tampoco se acepta una respuesta que corresponda a otra referencia interna.

El precio recuperado se guarda en la opción de Alcampo con fecha de consulta. No sustituye el precio pagado en otras tiendas. Marca, contenido, unidades y Nutri-Score completan los campos vacíos de las opciones del mismo EAN; se conservan los datos ya informados. No se cambia el nombre genérico del catálogo, la cantidad comprada ni el Stock.

Al desactivar el catálogo se cancela la consulta pendiente y se detienen las asociaciones y consultas nuevas. Los enlaces, datos y precios ya guardados permanecen disponibles. No requiere conectar una cuenta de Alcampo ni añadir dependencias.

En la ficha del producto → Alternativas, las referencias que comparten EAN aparecen dentro de un bloque común, comprimido por defecto. La marca, el contenido por envase y las unidades se editan en la parte superior para todas las opciones de ese EAN. Dentro de cada tienda quedan su nombre comercial, URL, referencia interna y precio por envase. Los cambios se conservan al guardar el producto. Los EAN distintos permanecen separados y las opciones sin EAN no se consideran equivalentes entre sí.

Catálogo → Productos → Agrupar por tienda incluye las opciones de compra activas guardadas, también las de Alcampo. No requiere conectar una cuenta ni mantener activada la descarga de datos. Las opciones desvinculadas no generan grupos.

En esa agrupación, el precio del bloque de producto corresponde únicamente a la tienda de su grupo. Si no tiene un precio registrado en esa tienda, no aparece el badge. Fuera de la agrupación por tienda se conserva la prioridad de la tienda favorita.

Al recuperar manualmente una URL en Alternativas, si la web devuelve otro EAN válido, sus datos se incorporan a una alternativa independiente. Se conserva el envase original; si tenía guardado ese enlace incorrecto, se desvincula de él. Repetir la consulta reutiliza la alternativa encontrada, sin duplicarla. Los cambios se guardan al pulsar Guardar producto. Las consultas automáticas siguen exigiendo coincidencia exacta de EAN.


## Masymas, BM y Consum

Cada catálogo está desactivado por defecto en Ajustes → Tiendas → Catálogos. Al activarlo se completan campos vacíos de productos que ya tienen EAN; nunca se crean productos ajenos al catálogo. El engranaje permite activar «Mostrar tienda en el catálogo» (desactivado por defecto): las alternativas y precios verificados se conservan para poder mostrarlos después sin repetir consultas.

Las búsquedas respetan este orden: coincidencias del diccionario por EAN, búsqueda directa por EAN en Masymas y búsquedas por nombres comerciales de alternativas ya vinculadas para BM y Consum. Estas últimas solo aceptan resultados cuyo EAN coincida exactamente. No se usan nombres genéricos del catálogo como sustituto de una identificación comercial ni se asocian productos por parecido. Si falta el nombre comercial o no hay coincidencia, se puede introducir la URL oficial en Alternativas y recuperar sus datos manualmente. Los códigos escaneados consultan los catálogos activos antes de Open Food Facts; activar un catálogo no asocia por sí solo un escaneo a un producto.

El diccionario ean-links-v5.csv añade columnas Masymas, BM y Consum; incluye únicamente las URL que se hayan verificado. Las coincidencias encontradas por cada instancia se conservan en su caché local, sin publicarse automáticamente en GitHub. Una URL evita repetir la búsqueda, pero recuperar información puede requerir consultar la ficha. Las búsquedas sin resultado se conservan un día; se permiten como máximo dos consultas de nombre por tienda y EAN en cada revisión. Los datos positivos se reutilizan hasta treinta días. Se esperan veinte segundos entre peticiones a la misma tienda, también en consultas manuales y después de un reinicio, y los bloqueos HTTP 403/429/503 detienen temporalmente la fuente.

El popup muestra progreso e incidencias y el resumen se registra en Logs → Tiendas. Desactivar una fuente detiene su trabajo; conserva lo ya guardado. No se requiere cuenta de esas tiendas ni dependencias adicionales.


## Recuperar información pendiente

En Catálogo → Pendiente → Productos pendientes de información, «Recuperar datos» inicia una revisión de las alternativas activas con URL de los productos de ese bloque. Los productos con al menos una alternativa completa quedan fuera del lote, igual que los que no tienen URL. Se fuerza la consulta de la ficha y se guardan los datos recuperados sin tener que abrir y guardar cada producto.

El proceso espera veinte segundos entre peticiones, también cuando una ficha necesita consultas complementarias. Respeta las pausas de las tiendas y conserva los datos anteriores ante errores. El popup muestra porcentaje, alternativa actual y errores con el nombre del producto. Cerrar el popup o recargar no cancela el trabajo; volver a pulsar el botón muestra el lote en curso. La cola y la espera se conservan tras reiniciar Home Assistant. Los cambios concurrentes se incorporan desde la ficha actual, sin volver a crear productos eliminados ni recuperar alternativas desvinculadas durante el proceso. Si una URL devuelve otro EAN, se crea una alternativa independiente, como en la recuperación manual.
