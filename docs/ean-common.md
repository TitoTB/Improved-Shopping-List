# Datos comunes de productos por EAN

El diccionario general [ean-common.json](../data/ean-common.json) contiene marca, contenido total por envase, unidad de medida y unidades por pack cuando hay datos explícitos para un EAN válido. Es independiente de la tienda: se aplica a alternativas de Carrefour, Alcampo, Lidl, Mercadona, Consum, BM, Masymas, La Sirena, Eroski y cualquier otra tienda admitida. No contiene precios, imágenes, nombres internos de productos, compras ni cuentas de los usuarios.

La carga inicial tiene 4.926 EAN con algún dato disponible, incorporando 87 EAN del catálogo exportado facilitado por el usuario y los datos comunes del índice de Mercadona. Esto amplía las fuentes; no significa que todos los EAN del diccionario de enlaces tengan todos sus campos informados. Los datos ausentes permanecen vacíos. En especial, un IAN de Lidl no se convierte en un EAN.

Home Assistant descarga el índice compacto, mantiene una copia local y comprueba actualizaciones como máximo una vez cada 24 horas, con ETag. Si GitHub falla, conserva los datos guardados. Solo considera los EAN presentes en el catálogo del usuario y completa campos vacíos: no incorpora productos ajenos, no activa tiendas ni crea alternativas de tiendas deshabilitadas. Para un EAN nuevo se consultan primero los datos comunes; si ya aportan marca y contenido, no se buscan de nuevo esos campos en supermercados. Open Food Facts puede aportar el nombre o Nutri-Score que falten; si no dispone del nombre, se mantiene la búsqueda por EAN en las tiendas habilitadas.

El relleno conserva campos manuales, alternativas retiradas, precios y modo Al peso. No transforma un producto al peso en un envase. Si una unidad manual es compatible, se conserva y se convierte el contenido a esa unidad; si es incompatible, el contenido queda pendiente. Los campos completados guardan como procedencia el diccionario comunitario, su huella de contenido y fecha.

## Aportar datos de otras tiendas

El mantenedor puede incorporar nuevas exportaciones autorizadas con:

```sh
python scripts/build-ean-common.py --import-catalog /ruta/improved-shopping-list-catalog.json
```

El importador publica exclusivamente los campos comunes de referencias activas con EAN válido. Solo acepta contenido y pack de formatos confirmados; no deduce tamaños de nombres, cantidades compradas o precios. Los datos seleccionados quedan en [ean-common-contributions.json](../data/ean-common-contributions.json), sin el catálogo original ni sus campos privados.

El índice se genera por EAN, combinando las aportaciones de todas las tiendas. Marcas equivalentes por mayúsculas y contenidos equivalentes como 500 g y 0,5 kg coinciden. Si dos fuentes discrepan, el campo afectado se excluye y se registra el conflicto; no se escoge arbitrariamente una tienda. El proceso conserva los campos no conflictivos.

El workflow del índice público de Mercadona regenera también el diccionario general combinando las aportaciones revisadas con el snapshot actualizado. Publica el resultado en [catalogs/ean-common.json de la rama data](https://github.com/TitoTB/Improved-Shopping-List/blob/data/catalogs/ean-common.json); la copia de main sirve de respaldo inicial. No hay envíos automáticos de catálogos de los usuarios.


## Nutri-Score y NOVA por EAN

El mismo índice incluye un bloque `nutrition` por EAN con `nutriscore.grade`, la versión del cálculo cuando está disponible, `nova`, `source`, `checked_at` y `license`. Está separado del bloque de formatos dentro del JSON para que las versiones anteriores puedan seguir leyendo marca y contenido. No se publican nutrientes detallados, precios ni información de compras en este bloque.

Las clasificaciones proceden de [Open Food Facts](https://world.openfoodfacts.org/) y se publican con su atribución y licencia [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/). La fecha corresponde a la consulta de esa clasificación, no a la regeneración general del índice. Cada versión del cálculo de Nutri-Score se conserva cuando la fuente la informa; no se infiere a partir del nombre o la tienda.

Nutrición utiliza primero los datos locales vigentes y el diccionario descargado de GitHub. Solo consulta Open Food Facts si no encuentra información vigente para el EAN. La vigencia es de treinta días; no se amplía simplemente por descargar otra vez el índice. Los datos de formato confirmados manualmente se conservan.

La exportación manual del catálogo incluye las clasificaciones que ya están en la caché nutricional, junto con su fuente y fecha. El importador `build-ean-common.py --import-catalog ...` las admite sin publicar nombres internos, precios ni datos domésticos. No se envía nada automáticamente desde Home Assistant.

La carga inicial y el mantenimiento se realizan con `scripts/update-ean-nutrition.py`. Solo se consultan EAN aportados explícitamente al diccionario, no todo el catálogo de supermercados. Cada lote tiene un máximo de cien peticiones, separadas al menos 4,2 segundos; los resultados ausentes se recuerdan durante un día y un límite de peticiones o error de servicio detiene el lote. El workflow diario conserva la caché anterior, completa los EAN pendientes y publica el índice en la rama `data`. Las nuevas clasificaciones llegan a los usuarios con la descarga periódica del diccionario, sin actualizar la integración.
