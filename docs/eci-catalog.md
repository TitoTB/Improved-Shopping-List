# Catálogo opcional de El Corte Inglés

Disponible en Ajustes → Tiendas → Catálogos. Está desactivado inicialmente y utiliza el logo indicado para El Corte Inglés.

Al activarlo, se buscan los EAN del catálogo local, incluidos los añadidos posteriormente. La búsqueda pública se confirma en la ficha: solo una coincidencia inequívoca con el mismo EAN puede crear o completar una alternativa. No se utiliza parecido de nombres ni publicidad de la página para asociar productos.

Se conservan URL, referencia interna, nombre comercial, marca, contenido neto y unidades, precio individual y precio por unidad de medida cuando estén disponibles. Las promociones condicionadas a comprar varias unidades no sustituyen al precio individual. Los datos comunes ya informados para ese EAN y los precios guardados más recientes se conservan.

La consulta utiliza las respuestas JSON públicas de la web, sin cuentas ni cookies del usuario, con la ubicación predeterminada del catálogo público. Cada petición del proceso respeta una espera mínima de veinte segundos, incluida la consulta de búsqueda y la de la ficha. La caché se conserva entre reinicios, los EAN sin resultado o con errores no se repiten durante veinticuatro horas y un bloqueo confirmado pausa las siguientes consultas.

El progreso aparece al activar el catálogo. El proceso continúa en Home Assistant y deja un resumen técnico al terminar. Desactivarlo detiene las consultas y conserva las alternativas incorporadas. No añade iconos de acceso al progreso a los bloques de tiendas.

No requiere tarjetas de HACS, cuentas externas ni nuevas dependencias.
