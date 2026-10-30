# Catálogo opcional de El Corte Inglés

Disponible en Ajustes → Tiendas → Catálogos. Está desactivado inicialmente y utiliza el logo indicado para El Corte Inglés.

Al activarlo, se buscan los EAN del catálogo local, incluidos los añadidos posteriormente. La búsqueda pública se confirma en la ficha: solo una coincidencia inequívoca con el mismo EAN puede crear o completar una alternativa. No se utiliza parecido de nombres ni publicidad de la página para asociar productos.

Se conservan URL, referencia interna, nombre comercial, marca, contenido neto y unidades, precio individual y precio por unidad de medida cuando estén disponibles. Las promociones condicionadas a comprar varias unidades no sustituyen al precio individual. Los datos comunes ya informados para ese EAN y los precios guardados más recientes se conservan.

La consulta utiliza las respuestas JSON públicas de la web, sin cuentas ni cookies del usuario. Mantiene una sesión anónima propia con las cookies públicas que entrega la portada, usando HTTP/2, con la ubicación predeterminada del catálogo público. Cada petición del proceso respeta una espera mínima de veinte segundos, incluida la consulta de búsqueda y la de la ficha. La caché se conserva entre reinicios, los EAN sin resultado o con errores no se repiten durante veinticuatro horas y un bloqueo confirmado pausa las siguientes consultas.

El progreso aparece al activar el catálogo. El proceso continúa en Home Assistant y deja un resumen técnico al terminar. Desactivarlo detiene las consultas y conserva las alternativas incorporadas. No añade iconos de acceso al progreso a los bloques de tiendas.

No requiere tarjetas de HACS ni cuentas externas. La dependencia `h2>=4.4.1` habilita HTTP/2 y Home Assistant la instala automáticamente; HTTPX forma parte de Home Assistant. Las cookies de esta sesión son propias de la integración, permanecen en memoria y no se exportan ni aparecen en los logs.

El engranaje situado a la derecha del interruptor abre «Mostrar tienda en el catálogo», desactivado inicialmente e independiente para cada fuente. Sin esta opción se completan únicamente los datos comunes del EAN; no se añade la tienda ni su precio como alternativa. Al activarla se incorporan también sus alternativas de compra con los datos guardados disponibles. Al desactivarla, las alternativas automáticas se archivan localmente para poder recuperarlas, conservando la marca y contenido del EAN. Las vinculaciones manuales y de tickets se mantienen. Este comportamiento se aplica también a Alcampo.

El popup recibe el progreso por suscripción y, mientras está abierto, consulta además el estado de Home Assistant cada dos segundos como respaldo (cada diez si hay una pausa). Estas lecturas no reinician el proceso ni consultan la web de la tienda. Las respuestas antiguas no sustituyen actualizaciones más recientes; durante la preparación sin total conocido se muestra actividad indeterminada, y las pausas se identifican como tales. El refresco de respaldo se detiene al cerrar la ventana, salir de la vista o finalizar la revisión.

Las coincidencias verificadas se conservan aunque «Mostrar tienda en el catálogo» esté desactivado o no se haya obtenido un precio. Al cambiar esa opción y al arrancar Home Assistant se aplican los resultados guardados sin consultar de nuevo la web. Si el ajuste cambia mientras hay una petición en curso, el guardado usa el valor vigente de la opción. Una incidencia al completar los datos locales no descarta la coincidencia recuperada.
