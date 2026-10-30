# Catálogo de Mercadona

En Ajustes → Tiendas → Catálogos, Mercadona se activa por separado de Alcampo y está desactivada por defecto. Usa el almacén de referencia `mad1`, sin cuenta ni dirección del usuario.

Al activarla, busca los EAN del catálogo local en el índice público completo de Mercadona, sin limitarse a los 195 enlaces iniciales que coinciden con Carrefour. Se mantiene también el diccionario `data/ean-links-v4.csv` como respaldo. Cada coincidencia proporciona una referencia interna. Consulta directamente `https://tienda.mercadona.es/api/products/<referencia>/?lang=es&wh=mad1` y exige que tanto la referencia como el EAN devueltos coincidan antes de crear una alternativa o guardar datos y precios. No busca por nombre durante el funcionamiento de la integración ni utiliza el antiguo buscador Tornillos.

## Índice público completo y caché

El índice inicial contiene 5.158 EAN válidos con una referencia inequívoca y ocupa aproximadamente 165 KB. No contiene precios, imágenes ni productos del usuario. Consultarlo no incorpora todos esos productos al catálogo: únicamente se consideran los EAN que ya existen en las fichas del usuario.

El workflow `mercadona-index.yml` comprueba diariamente el catálogo público de Datania, sin ejecutar código de ese repositorio. `scripts/build-mercadona-index.py` extrae solo EAN y referencia, valida los códigos y excluye las coincidencias ambiguas. Publica el resultado en la rama `data`, en `catalogs/mercadona-index.json`. Si el origen falla o queda incompleto, se conserva la publicación anterior. La actualización no modifica el código ni requiere publicar otra versión de la integración.

Home Assistant descarga ese índice compacto desde nuestro repositorio como máximo una vez cada 24 horas, usando ETag. Conserva una copia local entre reinicios y busca nuevas coincidencias en memoria al añadir EAN al catálogo. Si no hay publicación en la rama de datos, puede usar la copia inicial de `main/data/mercadona-index.json`. Si GitHub falla, se conserva el índice anterior y se deja constancia en el progreso y diagnóstico; los intentos fallidos se espacian al menos una hora. No se envían los EAN ni nombres del usuario a ningún servicio.

El índice solo localiza candidatos. Los datos actuales y el precio se obtienen de la API de Mercadona, con la validación exacta del EAN y las esperas indicadas a continuación. No se consulta individualmente en Mercadona ningún producto ajeno al catálogo del usuario.

Recupera nombre comercial, marca cuando esté informada, precio individual en EUR, contenido por envase y unidades, y precio por kilogramo, litro o unidad cuando estén disponibles. `unit_size` es el contenido total del envase vendible; no se vuelve a multiplicar por el número de unidades del pack. En productos a granel, de peso variable o con tamaño aproximado, no se presenta ese tamaño como contenido fijo. La cantidad comprada y Stock no se modifican.

Las peticiones automáticas se separan veinte segundos, con reserva persistente antes de cada llamada. Se conserva la caché y se detiene el lote ante 403, 429 o 503, respetando la pausa del servidor cuando existe. La revisión continúa en Home Assistant al cerrar el popup y emite un resumen en Logs → Tiendas. Las lecturas de progreso no consultan Mercadona ni reinician la revisión.

El engranaje abre **Mostrar tienda en el catálogo**, desactivado por defecto. Sin marcarlo solo se completan los datos comunes del EAN que falten. Marcándolo se incorpora además la alternativa de Mercadona y su precio. La información recuperada se conserva para aplicar el cambio sin volver a descargarla. Se respetan las URLs manuales, los datos ya informados y las alternativas desvinculadas. Desactivar el catálogo detiene las consultas; no elimina los datos del usuario.

También se puede introducir una URL de Mercadona en la ficha del producto → Alternativas → Recuperar datos. Se utiliza la misma API de producto.

## Diccionario inicial y procedencia

El diccionario v4 conserva las columnas Carrefour, Alcampo y Lidl y añade **195 enlaces de Mercadona**. Se obtuvieron por coincidencia exacta de EAN entre el diccionario público existente y las respuestas de productos conservadas en [datania/mercadona-catalog](https://huggingface.co/datasets/datania/mercadona-catalog), revisión `b0ac2530018080341bddd64b43728c4b4b45c39f` del 26/10/2026 (licencia MIT). Solo se incorporan EAN y URL oficial; no se copian imágenes, precios ni datos de los usuarios. El índice completo se prepara a partir de la misma fuente, eliminando la restricción de que el EAN deba existir en el feed de Carrefour. Home Assistant descarga el índice compacto y verifica de nuevo el EAN en la API antes de completar datos o precios.

La exportación de catálogo facilitada para preparar esta carga contiene 79 EAN válidos distintos. Ninguno coincide con los EAN de esa revisión pública de Mercadona; no se inventan equivalencias entre marcas o formatos. Los EAN sin correspondencia permanecen sin enlace. Los CSV v1, v2 y v3 se conservan para los clientes anteriores, que siguen usando sus URLs originales.

La consulta de la API y el parser de la integración se comprueban manualmente con `scripts/probe-mercadona.py` en la imagen oficial de Home Assistant Core 2026.10.2. La opción `--index-only` comprueba la descarga y lectura del índice con el cliente HTTP real sin consultar fichas de Mercadona. No requiere tarjetas HACS ni dependencias adicionales: utiliza aiohttp y el cliente HTTP de Home Assistant. La prueba en un contenedor aislado no implica acceso ni cambios en una instalación del usuario.
