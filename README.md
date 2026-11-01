# Improved Shopping List

## Índice

- [Lista de la compra](#lista-de-la-compra)
- [Catálogo](#catálogo)
- [Stock](#stock)
- [Analítica](#analítica)
- [Ajustes](#ajustes)
- [Marketing de afiliados](#marketing-de-afiliados)

## Lista de la compra

Desde este apartado puedes consultar y gestionar los productos de la lista seleccionada. En la parte superior aparecen los productos **pendientes de compra** y, debajo, el bloque desplegable **Compras recientes**, con los productos que has marcado como comprados y que todavía se conservan en la lista.

### Marcar productos como comprados o volver a añadirlos

- **Pulsa un producto pendiente** para marcarlo como comprado. Pasará al bloque de Compras recientes.
- **Pulsa un producto de Compras recientes** para devolverlo a los pendientes de compra.
- **Limpiar productos**, dentro de Compras recientes, elimina de la lista todas las entradas completadas. No elimina sus fichas del catálogo.

Los cambios se reflejan en la lista de Home Assistant y en su proveedor, como Bring.

Marcar un producto como comprado no aumenta su Stock ni reinicia su caducidad. La reposición se registra al confirmar la revisión de un ticket o al actualizar manualmente Stock. En el ticket se propone la cantidad recuperada o estimada y, si no está disponible, la cantidad predeterminada de reposición.

### Añadir productos

Utiliza el buscador de la parte superior para escribir el nombre del producto. Mientras escribes, aparecen sugerencias de los productos que ya tienes en el catálogo: pulsa una para añadirla directamente. También puedes seleccionar una sugerencia con las flechas del teclado y pulsar **Enter**.

Si el producto no está en el catálogo, escribe su nombre y pulsa **+** o **Enter** para añadirlo a la lista. Si ya está pendiente, no se crea una entrada duplicada; si estaba en Compras recientes, vuelve a quedar pendiente.

Si tienes varias listas configuradas, el botón de selección de lista permite elegir cuál quieres utilizar. Este botón se oculta cuando solo tienes una lista de la compra.

### Vistas y ordenación

Los controles situados junto al buscador permiten cambiar cómo se muestran los productos:

- **Orden alfabético:** muestra todos los productos ordenados por su nombre.
- **Agrupar por categorías:** reúne los productos según la categoría que tengan asignada en el catálogo, manteniendo el orden alfabético dentro de cada grupo. Los que no tienen categoría aparecen en Sin categoría. Vuelve a pulsar el botón para recuperar el listado sin agrupar.
- **Cuadrícula o filas:** alterna entre bloques cuadrados y una fila completa por producto. En filas se pueden mostrar la categoría, la cantidad, el último precio guardado y el Nutri-Score, cuando esos datos estén disponibles.

La vista y la agrupación se aplican tanto a los productos pendientes como a Compras recientes.

### Precio estimado y comparación entre supermercados

Junto al título Lista de la compra aparecen el **número de productos pendientes** y el **importe aproximado** de la compra. El cálculo utiliza los últimos precios guardados; abrir este apartado no actualiza los precios de las tiendas.

**Pulsa el importe estimado** para cambiar a una vista tipo ticket. En la parte superior se muestran hasta cuatro supermercados que tengan algún precio guardado para los productos pendientes, priorizando los que tienen más productos con precio disponible.

Cada supermercado muestra su logo, el importe estimado y cuántos productos tienen precio respecto al total de la lista. Por ejemplo, **2,50 € (1/17)** indica que solo hay precio para uno de los diecisiete productos pendientes.

Inicialmente se selecciona el supermercado con más productos con precio disponible; si hay empate, se prioriza el de menor importe. **Pulsa otro supermercado** para consultar su ticket, con los productos ordenados alfabéticamente y el precio a la derecha. Los productos sin precio en esa tienda se agrupan en un bloque comprimido que puedes desplegar. Al final aparece el total estimado, que suma únicamente los productos con precio conocido.

Para volver a la vista habitual de productos, **pulsa el badge del número de productos**.

## Catálogo

El catálogo reúne las fichas de tus productos para utilizarlas en la lista de la compra, Stock y la comparación de precios. Sus vistas son **Productos**, **Categorías** y **Pendiente**.

### Añadir productos y asignar imágenes

Desde **Productos**, pulsa **+** para crear una ficha. Puedes empezar con el nombre y completar el resto de la información más adelante.

En la ficha puedes asignar una imagen mediante el campo **URL Imagen/Icono**, indicando la dirección de la imagen que quieras utilizar. También se muestran propuestas de iconos, dando prioridad al catálogo comunitario, cuyas imágenes proceden principalmente de [Iconify](https://iconify.design/) y [Flaticon](https://www.flaticon.es/).

### Organizar por categorías

Puedes crear categorías y asignarles un nombre, un icono y un color. Después, selecciona la categoría correspondiente en la ficha de cada producto; también puedes crear una categoría desde esa misma ficha.

El catálogo permite buscar productos, alternar entre cuadrícula y filas y mostrarlos por orden alfabético o agrupados por categoría. Los grupos se muestran comprimidos y se despliegan al pulsarlos.

### Alternativas de compra en distintas tiendas

Un mismo producto del catálogo puede tener varias alternativas de compra, tanto de una misma tienda como de distintos supermercados. Por ejemplo, una ficha de «Café» puede reunir distintas marcas y formatos.

En la vista **Alternativas** de la ficha, introduce la **URL del producto** y pulsa **Recuperar datos**. La integración identifica la tienda a partir del enlace e intenta recuperar los datos disponibles, como el nombre comercial, el EAN, la marca, el contenido y el precio, siempre que el supermercado esté soportado y permita la consulta. Puedes revisar y completar los datos manualmente.

Las alternativas con el mismo EAN se agrupan en un bloque: comparten los datos del producto y mantienen por separado la URL y el precio de cada tienda.

### Reposición automática y lectores

La vista **Reposición** de la ficha permite configurar los criterios de reposición automática, coordinados con Stock: productos perecederos, consumo registrado mediante una entidad de Home Assistant o consumo por rutinas. Según el modo elegido, puedes indicar el plazo de caducidad, la cantidad de reposición y el mínimo a partir del cual se solicita la compra.

También puedes asociar **códigos de barras/QR** y **etiquetas NFC** al producto. Al escanearlos con un lector configurado, se ejecuta su acción predeterminada o la acción específica que hayas elegido para ese producto, como añadirlo a la lista o aumentar o reducir su Stock.

### Productos pendientes

La vista **Pendiente** avisa de los productos que requieren revisión y los separa en tres bloques desplegables:

- **Productos añadidos a la lista:** nombres presentes en la lista de la compra que todavía no están incorporados al catálogo.
- **Productos escaneados:** códigos de barras/QR o etiquetas NFC que aún no están asociados a un producto. Puedes vincularlos a una ficha existente o crear una nueva.
- **Productos pendientes de información:** fichas cuyas alternativas necesitan completar precio, contenido por envase o unidad de medida. Si al menos una alternativa está completa, el producto no aparece en este bloque.

## Stock

## Analítica

## Ajustes

## Marketing de afiliados

Algunos enlaces para consultar productos en las tiendas pueden ser enlaces de afiliado. Si accedes a través de ellos y realizas una compra, Aguacatec puede recibir una comisión.
