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
