# Cantidades al revisar tickets

La revisión de Carrefour utiliza primero el peso o las unidades explícitos del ticket. En productos envasados, el contenido indicado en la descripción se multiplica por el número de envases comprados. Las líneas con peso explícito conservan una cantidad de compra separada del contenido fijo de la opción.

Después de confirmar las vinculaciones, las líneas sin cantidad utilizan el precio por unidad de medida de su opción de Carrefour, si está guardado. También se puede obtener de un último precio y un contenido de envase confirmado de esa misma opción. No se mezclan precios de otras tiendas ni formatos distintos.

Si falta ese dato y existe una única opción identificada con URL, se consulta su ficha mediante el recuperador existente. Utiliza un precio de referencia explícito cuando está disponible o lo calcula a partir del precio y contenido comercial indicados en la ficha. Guarda el precio normalizado por 1 kg, 1 l o 1 unidad dentro de la opción, con fecha y fuente. Las cantidades calculadas con ese precio se muestran como **Cantidad estimada**, incluidas las calculadas con precios previamente guardados.

El peso estimado pertenece a esa compra; no se convierte en el peso de un envase. El usuario puede corregirlo antes de confirmar. La reposición usa la cantidad revisada y las unidades del stock, cuando son compatibles. Se conserva el precio por unidad de medida para otras revisiones y se muestra en Catálogo → ficha → Opciones.

Cuando se conoce un descuento por línea, el cálculo usa su importe anterior al descuento. Los cupones generales no se reparten. Un precio web puede diferir del de la tienda física o de la fecha del ticket: por eso el resultado sigue siendo una propuesta editable. Si existen varias opciones posibles o no hay información suficiente, se mantiene la revisión manual.

La interfaz muestra un popup con barra de progreso, número de líneas procesadas y producto actual. Las consultas son secuenciales, comparten el límite de al menos cinco segundos entre peticiones y reutilizan la caché. Las respuestas 429/503 respetan una pausa de al menos quince minutos y el `Retry-After` numérico, acotado a un día; un bloqueo 403 sin datos útiles también detiene nuevas consultas durante quince minutos. Las cantidades y los precios guardados permiten continuar sin repetir consultas web. Sin nuevas dependencias.
