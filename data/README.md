# Enlaces de productos por EAN

[ean-links.csv](ean-links.csv) contiene las columnas `EAN` y `Carrefour`. Cada fila relaciona un código comercial válido con el enlace de ese producto en la tienda. Se podrán añadir columnas para otros supermercados sin cambiar la identidad de la fila.

Esta primera carga procede del feed de Awin de Carrefour facilitado por el mantenedor y procesado el 20/10/2026. Contiene 15.764 EAN válidos; se han excluido 480 registros con códigos no válidos. No incluye precios, nombres de usuarios, compras ni credenciales. No hay descarga programada del feed ni actualización automática de este archivo.

La copia conservada del feed contiene enlaces de Awin. La integración consulta únicamente los correspondientes a EAN de su catálogo: hace una petición HEAD, extrae el destino oficial de Carrefour de la redirección y guarda la URL sin parámetros de seguimiento. No sigue los enlaces intermedios de publicidad ni descarga fichas o precios como parte de este proceso. Los enlaces de consulta visibles de Carrefour mantienen el comportamiento de afiliación documentado en el README.

Home Assistant descarga el índice cuando tiene algún EAN que consultar, conserva una copia local y comprueba cambios como máximo una vez cada 24 horas mediante ETag. Las resoluciones se espacian al menos cinco segundos y los fallos se reintentan como máximo al día. Si GitHub no está disponible, conserva los datos locales. Se completan por EAN exacto opciones nuevas, confirmadas en tickets y anteriores, sin sobrescribir URL manuales ni reactivar opciones desactivadas. La incorporación inicial ocurre en segundo plano; los enlaces ya resueltos se aplican al guardar. Este índice no modifica stock, formatos, Nutri-Score ni precios.

El catálogo comunitario de iconos es independiente. Este archivo es público y de solo lectura para la integración: no recibe datos de los usuarios ni necesita autorización de GitHub.
