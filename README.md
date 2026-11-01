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

Este apartado permite llevar el control de los productos de tu despensa. Tú eliges cuáles quieres controlar y cómo se registra su consumo. El Stock es común para todas las listas de la compra y se organiza en las vistas **Stock**, **Rutinas** y **Lectores**.

### Añadir y configurar productos

En la vista **Stock**, pulsa **+** para añadir un producto. Después, pulsa su bloque para abrir la ficha y configurar la cantidad actual, las unidades —uds, g, kg, litros o una unidad personalizada—, el método de control y la cantidad predeterminada de reposición.

Puedes alternar entre cuadrícula y filas, y ordenar los productos alfabéticamente, por menor porcentaje de Stock o agrupados por categoría. En filas también aparecen los controles para aumentar o reducir la cantidad manualmente.

### Métodos de control

Cada producto puede utilizar uno de estos métodos:

- **Manual / lectores:** ajustas la cantidad desde la ficha, con los controles de la vista de filas o escaneando un código asociado con una acción de aumentar o reducir Stock.
- **Perecedero:** indicas cuántos días dura desde la reposición. La cantidad y el porcentaje restante disminuyen proporcionalmente con el tiempo, como estimación de disponibilidad, hasta llegar a cero al caducar. El plazo de caducidad se respeta independientemente de la cantidad repuesta.
- **Consumo registrado:** seleccionas una entidad de Home Assistant, el estado que representa un uso y la cantidad que se descuenta cada vez que la entidad entra en ese estado. Por ejemplo, puedes descontar detergente cuando la lavadora pasa al estado que hayas configurado.
- **Consumo por rutinas:** asignas una o varias rutinas y la cantidad que consume cada persona cuando está en casa durante su franja horaria. Puedes definir cantidades diferentes por persona.

Las opciones automáticas también se pueden configurar desde **Reposición** en la ficha del producto del catálogo. Ambas fichas comparten la misma configuración.

### Stock bajo y reposición

Activa **Añadir a la lista cuando el stock llegue al mínimo** e indica el umbral. En los perecederos se utiliza el porcentaje restante; los demás métodos aplican el mínimo de cantidad o porcentaje configurado. Cuando se alcanza ese mínimo, el producto se añade automáticamente a la lista elegida, sin duplicar una entrada que ya esté pendiente.

Si tienes varias listas de compra, puedes elegir la **Lista para reponer**. El selector se oculta cuando solo hay una; las listas pasarela no cuentan como listas de destino adicionales.

Para registrar lo comprado, puedes revisar un ticket desde **Analítica → Compras** o actualizar la cantidad manualmente. Al revisar el ticket, se propone la cantidad recuperada o estimada y, si no está disponible, la cantidad predeterminada de reposición. Solo se repone Stock para los productos que selecciones durante la revisión. Marcar un producto como comprado en la lista no aumenta por sí solo su Stock.

### Rutinas

Una rutina define **qué personas**, **en qué franja horaria** y **qué días de la semana** se tienen en cuenta para registrar un consumo habitual en casa.

En **Rutinas**, pulsa **+**, escribe un nombre, selecciona las personas y configura la hora de inicio, la hora de fin y los días. Después, en la ficha del producto, elige **Consumo por rutinas**, marca la rutina e indica cuánto consume cada persona.

Si una persona ha estado en casa en algún momento de esa franja, se descuenta la cantidad configurada una vez por persona y franja. Por ejemplo, una rutina de desayuno de 08:00 a 10:00 puede descontar una unidad de chocolate por cada persona seleccionada que haya estado en casa durante ese intervalo. La presencia se obtiene de sus entidades **person** de Home Assistant.

Las tarjetas se ordenan por hora de inicio. Su toggle permite activarlas o desactivarlas y, al pulsar una tarjeta, puedes editarla o eliminarla desde el popup.

### Lectores

Los lectores conectan las lecturas de **códigos de barras/QR** o **etiquetas NFC** con los productos del catálogo. En **Lectores**, pulsa **+**, asigna un nombre y selecciona el tipo y la fuente: una entidad de Home Assistant que reciba el código o, para NFC, el evento **tag_scanned** del dispositivo correspondiente.

Configura la **acción por defecto**, la lista de destino y el intervalo de **antirrepetición**, que inicialmente es de 60 segundos. Este intervalo evita procesar repetidamente una misma lectura por error.

Desde **Reposición** en la ficha de cada producto puedes escanear y asociar uno o varios códigos o etiquetas. Para cada lector se utiliza su acción predeterminada, salvo que elijas una acción específica para ese producto: añadirlo a la lista, aumentar Stock, reducir Stock o no realizar ninguna acción. Para modificar Stock, el producto debe estar incluido previamente en él.

Cada tarjeta permite activar o desactivar el lector, consultar las lecturas en directo, editarlo o quitarlo. También muestra la fecha y hora de su último uso. Los códigos desconocidos aparecen en **Catálogo → Pendiente** para vincularlos a un producto existente o crear uno nuevo. Los lectores siguen funcionando aunque cierres la interfaz.

## Analítica

Analítica reúne cuatro vistas. Los gráficos y las tablas utilizan los datos guardados en tu Home Assistant y se adaptan al periodo que selecciones.

### Compras

Es la vista inicial. Puedes consultar el gasto mensual por tienda, filtrar las compras por fechas, tienda o usuario y abrir sus tickets para revisarlos. También puedes subir un ticket o una factura. Las compras recuperadas de una cuenta pueden aparecer con fecha e importe antes de revisar su detalle.

### Gastos

Muestra el gasto total, el número de compras, el importe medio y qué parte del gasto se ha podido clasificar. Puedes explorar el gasto por tienda y categoría, los productos en los que más gastas, los que compras con más frecuencia o cantidad y la participación de cada persona. Pulsa en las barras para filtrar y en un producto para abrir su ficha.

Las categorías corresponden a las vinculaciones actuales del catálogo. Los descuentos generales se distribuyen proporcionalmente; los importes sin detalle y los gastos de envío quedan sin clasificar. Una compra compartida cuenta para cada participante, pero se suma una sola vez al gasto total. Las cantidades compradas se comparan por la misma unidad; no representan necesariamente consumo.

### Comparativa

Compara las alternativas del catálogo con precios por kg, litro o unidad equivalentes en al menos dos tiendas. Muestra las tiendas con más precios mínimos y las mayores diferencias de precio. Puedes ordenar por diferencia absoluta o porcentual. Al pulsar en una tienda se priorizan sus productos más baratos; una segunda pulsación deja solo esos productos y una tercera elimina el filtro.

### Nutrición

Incluye Nutri-Score, clasificación NOVA e información disponible sobre energía, grasas, grasas saturadas, azúcares, sal, fibra y proteínas. Permite consultar el catálogo o los productos de las compras del periodo y filtrar por características alimentarias informadas. Al desplegar una calificación o pulsar un alimento puedes consultar sus productos y fichas.

Los datos se consultan en [Open Food Facts](https://world.openfoodfacts.org/) por coincidencia exacta de EAN y se guardan en una caché persistente para evitar repetir consultas. Se muestran por 100 g o 100 ml, separando su ordenación cuando conocemos la base. Los datos ausentes se indican con «—»; las compras reflejan alimentos adquiridos, no cantidades ingeridas. No se necesitan tarjetas adicionales de HACS.

## Ajustes

## Marketing de afiliados

Algunos enlaces para consultar productos en las tiendas pueden ser enlaces de afiliado. Si accedes a través de ellos y realizas una compra, Aguacatec puede recibir una comisión.
