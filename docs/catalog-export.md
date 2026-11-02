# Exportación del catálogo

En Ajustes → Comunidad, **Exportar mi catálogo** descarga `improved-shopping-list-catalog.json`. Solo está disponible para administradores y no requiere conectar GitHub.

Incluye todos los productos, aunque no tengan icono: nombre, traducción disponible, categoría, icono o URL pública de imagen, códigos de barras y opciones comerciales con tienda, EAN, referencia, URL, marca, contenido, precios guardados y Nutri-Score disponible. También incluye el bloque nutricional por EAN ya guardado en caché: Nutri-Score, versión del cálculo cuando existe, NOVA, fuente y fecha de consulta. Las imágenes locales no se adjuntan. No contiene listas, Stock, compras, tickets, cuentas, credenciales, etiquetas NFC ni automatizaciones.

La descarga no envía datos a GitHub ni activa la participación comunitaria. El usuario puede enviar el archivo a Aguacatec para completar los diccionarios de productos y enlaces por EAN. Debe tener en cuenta que el archivo contiene los nombres y precios de su catálogo.

Para el [diccionario de datos comunes por EAN](ean-common.md), el importador selecciona marca, contenido, unidades y unidades por pack de las referencias válidas, además de las clasificaciones del bloque nutricional con procedencia de Open Food Facts. No publica nombres internos, precios ni otros campos de la exportación.

La vista Comunidad permite exportar el archivo y consultar los enlaces de Aguacatec. Ya no muestra controles de autenticación ni el estado de sincronización con GitHub.
