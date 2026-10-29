# Catálogos de tiendas

En Ajustes → Tiendas → Catálogos, Alcampo está desactivado por defecto. Activarlo utiliza las coincidencias exactas de EAN del diccionario público para añadir opciones de Alcampo a los productos del catálogo y recuperar sus datos desde la ficha oficial.

El proceso muestra un popup con progreso, producto actual e incidencias. Continúa en Home Assistant al cerrar el popup o recargar la página; el botón de progreso permite consultarlo de nuevo. No reinicia una revisión que ya está en curso.

El resumen de Logs → Tiendas conserva los detalles técnicos de cada incidencia: referencia, URL, fase de consulta (ficha o API), código HTTP y motivo de rechazo o falta de datos. Una página sin datos estructurados no se identifica automáticamente como un bloqueo por frecuencia. Los bloqueos confirmados detienen el lote y conservan la pausa de reintento.

Las peticiones automáticas se separan al menos veinte segundos, incluidas las redirecciones y consultas complementarias de una misma ficha. La reserva se guarda antes de cada petición y se conserva tras reiniciar. Se reutiliza la caché del recuperador y se respetan las pausas ante bloqueos. Los datos recuperados correctamente no se vuelven a consultar en cada cambio del catálogo. Las coincidencias nuevas se procesan automáticamente mientras la opción siga activada.

Se conserva la URL introducida manualmente y no se reactiva una opción que el usuario haya desvinculado. El EAN devuelto por la web, cuando existe, debe coincidir. El enlace del diccionario ya se ha verificado por EAN; tampoco se acepta una respuesta que corresponda a otra referencia interna.

El precio recuperado se guarda en la opción de Alcampo con fecha de consulta. No sustituye el precio pagado en otras tiendas. Marca, contenido, unidades y Nutri-Score completan los campos vacíos de las opciones del mismo EAN; se conservan los datos ya informados. No se cambia el nombre genérico del catálogo, la cantidad comprada ni el Stock.

Al desactivar el catálogo se cancela la consulta pendiente y se detienen las asociaciones y consultas nuevas. Los enlaces, datos y precios ya guardados permanecen disponibles. No requiere conectar una cuenta de Alcampo ni añadir dependencias.

En la ficha del producto → Opciones, las referencias que comparten EAN aparecen dentro de un bloque común, comprimido por defecto, con las opciones de cada tienda en su interior. Los EAN distintos permanecen separados y las opciones sin EAN no se consideran equivalentes entre sí.
