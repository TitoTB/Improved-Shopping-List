# Enlaces de productos por EAN

[ean-links-v2.csv](ean-links-v2.csv) contiene las columnas `EAN`, `Carrefour` y `Alcampo`. Cada fila relaciona un código comercial válido con los enlaces confirmados de ese producto. Una celda vacía significa que no hay una coincidencia verificada; no demuestra que la tienda no venda ese producto.

La ampliación de Alcampo del 29/10/2026 incorpora 11 URL cuyo EAN se ha comprobado en la ficha oficial. Se excluyen los resultados con EAN diferente y aquellos cuya ficha no permite confirmarlo. [alcampo-verification.json](alcampo-verification.json) conserva únicamente los códigos y enlaces públicos verificados. No se publican catálogos personales, nombres internos, compras ni precios de los usuarios.

El índice ampliado contiene 15.767 EAN: los 15.764 de la carga original de Carrefour y tres con enlace únicamente en Alcampo. [ean-links.csv](ean-links.csv) conserva las 15.764 filas originales, con la columna Alcampo añadida cuando existe coincidencia, para que las versiones instaladas que exigen un enlace Carrefour en cada fila sigan funcionando. Las versiones que usan el índice v2 pueden incorporar también las filas exclusivas de Alcampo.

Esta primera carga procede del feed de Awin de Carrefour facilitado por el mantenedor y procesado el 20/10/2026. Contiene 15.764 EAN válidos; se han excluido 480 registros con códigos no válidos. No incluye precios, nombres de usuarios, compras ni credenciales. No hay descarga programada del feed ni actualización automática de este archivo.

La copia conservada del feed contiene enlaces de Awin. La integración consulta únicamente los correspondientes a EAN de su catálogo: hace una petición HEAD, extrae el destino oficial de Carrefour de la redirección y guarda la URL sin parámetros de seguimiento. No sigue los enlaces intermedios de publicidad ni descarga fichas o precios como parte de este proceso. Los enlaces de consulta visibles de Carrefour mantienen el comportamiento de afiliación documentado en el README.

Home Assistant descarga el índice cuando tiene algún EAN que consultar, conserva una copia local y comprueba cambios como máximo una vez cada 24 horas mediante ETag. Las resoluciones se espacian al menos cinco segundos y los fallos se reintentan como máximo al día. Si GitHub no está disponible, conserva los datos locales. Se completan por EAN exacto opciones nuevas, confirmadas en tickets y anteriores, sin sobrescribir URL manuales ni reactivar opciones desactivadas. La incorporación inicial ocurre en segundo plano; los enlaces ya resueltos se aplican al guardar. Este índice no modifica stock, formatos, Nutri-Score ni precios.

Las URL oficiales de Alcampo se incorporan por coincidencia exacta de EAN solo al activar Ajustes → Tiendas → Catálogos → Alcampo. El diccionario no requiere búsquedas en Google desde Home Assistant. La búsqueda y comprobación de esta carga se han realizado una sola vez; no se programa un rastreo automático. Se conservan las URL manuales y las opciones desactivadas. La recuperación opcional de precios y datos desde las fichas, con progreso y veinte segundos entre peticiones, se explica en [Catálogos de tiendas](../docs/store-catalogs.md).

El catálogo comunitario de iconos es independiente. Estos archivos son públicos y de solo lectura para la integración: no reciben datos de los usuarios ni necesitan autorización de GitHub.
