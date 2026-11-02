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

El 100 % corresponde al stock total que queda después de la última reposición. Si quedan 50 g y añades 200 g, los 250 g resultantes serán el nuevo 100 %. Se utiliza la cantidad recuperada o estimada del ticket cuando está disponible; la cantidad predeterminada solo sirve como propuesta cuando no se conoce la comprada.

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

Analítica permite consultar tus compras, entender cómo se reparte el gasto, comparar los precios guardados y conocer la información nutricional de los productos de tu catálogo. Se organiza en cuatro vistas: **Compras**, **Gastos**, **Comparativa** y **Nutrición**.

### Compras

Es la vista inicial. Muestra las compras registradas y una gráfica de gasto mensual, con un color por tienda. Puedes elegir el periodo de fechas, filtrar por tienda o persona y consultar compras anteriores con **Mostrar más**.

#### Cómo se obtienen las compras

- **Conectando una cuenta en Ajustes → Tiendas → Cuentas.** Actualmente se pueden conectar Carrefour y Lidl. Según las opciones que actives, la integración permite recuperar las compras de los últimos doce meses y descargar automáticamente nuevos tickets cuando se detecta una compra. También incorpora al histórico otras compras que encuentre durante esas consultas. El histórico puede mostrar la tienda, fecha e importe aunque todavía no hayas revisado el ticket.
- **Subiendo un ticket o una factura.** Utiliza el botón de subir ticket de esta vista. El supermercado y el formato del documento deben estar soportados: actualmente, la subida manual reconoce tickets y facturas PDF de Carrefour que contienen texto. Los documentos escaneados como imagen requieren un tratamiento distinto y no se reconocen mediante OCR.
- **Mediante la detección automática de compra, si la has configurado.** Completar más de la cantidad indicada de productos durante un día permite detectar una compra. Las personas y zonas configuradas ayudan a identificar la tienda. Si no se encuentra un ticket o no se identifica la tienda, puedes completar sus datos manualmente o adjuntar un documento compatible.

El icono del ticket de cada compra abre su revisión o recupera el detalle desde la cuenta conectada, cuando está disponible. El icono aparece en verde cuando el ticket ya se ha revisado. Recuperar una compra en el histórico no repone por sí solo el Stock ni confirma todos sus productos.

#### Para qué sirve revisar un ticket

La revisión convierte los nombres y cantidades del supermercado en información útil para tu catálogo y tu despensa. El asistente permite comprobar los datos antes de aplicarlos y se divide en cuatro pasos:

1. **Vinculación.** Relaciona cada línea del ticket con un producto de tu catálogo o crea uno nuevo. Las líneas que no vincules se ignoran para las operaciones sobre productos. Las asociaciones se guardan para reconocer futuras compras de esa tienda, aunque no incluyas el producto en Stock. Varias líneas pueden corresponder al mismo producto genérico, conservando sus alternativas comerciales y sus EAN cuando están disponibles.
2. **Stock.** Selecciona los productos que quieres reponer y confirma la cantidad y las unidades. Los que ya están en Stock aparecen seleccionados inicialmente; puedes incluir otros o desmarcarlos. Se propone la cantidad recuperada del ticket o estimada a partir de un precio por unidad de medida y, cuando no se conoce, la cantidad predeterminada de reposición. Puedes corregirla antes de guardar. Marcar un producto como comprado en la lista no aumenta por sí solo el Stock.
3. **Precios.** Selecciona los productos vinculados cuyo precio quieres guardar para esa tienda. Cuando se dispone de ellos, también se aprovechan el EAN y los datos de formato del producto, como el contenido del envase. En un producto al peso, el importe total pagado no sustituye al precio por kg: se utiliza una tarifa identificada en el ticket o el valor que confirmes manualmente.
4. **Resumen.** Comprueba las vinculaciones, las reposiciones y los precios seleccionados y confirma la compra para guardar los cambios.

También puedes guardar solo las vinculaciones y cerrar, o utilizar las opciones de guardar Stock o precios y cerrar sin completar todos los pasos. Las acciones dependen de lo que hayas seleccionado. Reprocesar los datos de un ticket ya revisado permite completar alternativas y formatos del catálogo sin volver a reponer Stock.

### Gastos

Utiliza las compras registradas en el periodo elegido para mostrar **Gasto total**, **Compras** e **Importe medio**, en euros. Los datos proceden del histórico, tanto de compras recuperadas de cuentas como de documentos revisados y compras completadas manualmente.

- **Gasto por categoría:** muestra las nueve categorías con más gasto, con el color configurado para cada una. El resto y los importes sin clasificar se agrupan en **Otros**. Permite reconocer qué tipos de productos concentran el gasto.
- **Productos en los que más gastas:** muestra los diez productos vinculados con mayor importe acumulado en el periodo. Sirve para localizar los que más pesan en tu presupuesto; el importe es el gasto acumulado en ellos, no el precio de un solo envase.
- **Gasto por tienda:** muestra cuánto has gastado en cada tienda. Puedes pulsar una barra para filtrar el análisis por esa tienda.
- **Compras por persona:** muestra el número de compras y el importe asociados a cada persona registrada como compradora. Puedes pulsar su barra para filtrar. Una compra compartida cuenta para cada participante, sin repartir su importe entre ellos, pero se suma una sola vez al gasto total.

Para clasificar el gasto por categoría o producto es necesario que las líneas de los tickets estén vinculadas al catálogo. Las categorías utilizadas son las actuales del catálogo. Los descuentos generales se distribuyen proporcionalmente; los gastos de envío y los importes sin detalle quedan en **Otros**. Por eso una compra recuperada solo con fecha e importe contribuye al total, aunque todavía no pueda repartirse entre productos y categorías.

### Comparativa

Utiliza los precios y los formatos guardados en las alternativas del catálogo. Estos datos pueden proceder de la revisión de tickets y facturas, de la edición manual o de las fichas web y catálogos de supermercados compatibles que hayas habilitado. Abrir esta vista analiza los datos guardados; no actualiza los precios consultando las tiendas.

Se incluyen los productos que tienen precios comparables en al menos dos tiendas. La comparación se realiza por la misma unidad —**€/kg**, **€/l** o **€/ud**— y puede comparar alternativas de distintas marcas y EAN de un mismo producto genérico. Para ello deben estar informados el tipo de venta y los datos de formato necesarios. Las alternativas sin información suficiente para calcular un precio comparable no se incluyen.

- **Dónde están los precios más bajos:** muestra las tiendas que tienen al menos un precio mínimo. Los empates cuentan para las tiendas correspondientes.
- **Dónde puedes ahorrar más:** destaca los productos con mayores diferencias porcentuales entre tiendas e indica también la diferencia por unidad de medida.
- **La misma cesta de referencia:** compara una cantidad de referencia por producto —una unidad, un kg o un litro— utilizando solo productos comparables en todas las tiendas mostradas. Sirve para comparar la misma selección; no representa necesariamente las cantidades de tu lista de la compra.
- **Precios del catálogo:** muestra los precios comparables por producto y tienda, su fecha y la diferencia máxima. Permite ordenar alfabéticamente o por diferencia absoluta o porcentual.

Al pulsar una tienda en el gráfico o en la cabecera de la tabla se priorizan los productos más baratos en ella. Una segunda pulsación deja solo esos productos y una tercera elimina la selección. Las fechas ayudan a valorar si los precios guardados siguen siendo recientes; los importes mostrados pueden haber cambiado en la tienda.

### Nutrición

Utiliza el catálogo completo y sus EAN para mostrar dos gráficos independientes:

- **Nutri-Score:** distribuye los productos con una calificación disponible entre A y E. Los productos sin calificación no se incluyen en sus porcentajes. Cada producto genérico cuenta una vez en la distribución.
- **Grado de procesamiento:** agrupa los productos según NOVA en sin procesar o mínimamente procesados, ingredientes culinarios, procesados y ultraprocesados. Los colores van de verde a rojo según aumenta el procesamiento. Solo se clasifican los productos para los que existe ese dato; un producto con alternativas de distinto procesamiento puede aparecer en más de un grupo.

Pulsa una calificación o un grupo para desplegar sus productos y abrir sus fichas. Desplegar un grupo no filtra el otro gráfico. Esta vista ayuda a conocer la composición del catálogo; no representa las cantidades que has consumido ni una valoración de tu dieta.

La integración consulta [Open Food Facts](https://world.openfoodfacts.org/) por coincidencia exacta de EAN y conserva los resultados en una caché persistente. Al abrir la vista intenta completar la información sin caché vigente, con consultas espaciadas. Los datos encontrados se reutilizan durante treinta días para evitar repetir llamadas. Open Food Facts es una base colaborativa y puede contener información incompleta: no se deduce una clasificación a partir del nombre del producto.

Analítica no requiere tarjetas adicionales de HACS.

## Ajustes

## Marketing de afiliados

Algunos enlaces para consultar productos en las tiendas pueden ser enlaces de afiliado. Si accedes a través de ellos y realizas una compra, Aguacatec puede recibir una comisión.
