# Consumo de stock por comidas

En **Stock → Rutinas**, crea una rutina y selecciona una o varias personas. Cada comida tiene nombre, una franja con hora de inicio y fin, días de la semana y una casilla para activarla. Puedes añadir comidas y crear horarios distintos para fines de semana mediante filas con días diferentes. Si la franja cruza medianoche, pertenece al día en que comienza.

En la ficha del producto, abre **Reposición → Reposición automática → Consumo por comidas**, o selecciona ese control desde su ficha de **Stock**. Marca las comidas y la cantidad a consumir por persona, expresada en las unidades de Stock. Opcionalmente indica cantidades distintas por persona; una cantidad personal de cero excluye a esa persona de ese consumo.

Se descuenta la cantidad una sola vez por persona y comida si se registra presencia en casa en cualquier momento de la franja. Estar en casa al comenzar la franja o llegar durante ella cuenta, sin permanencia mínima. Salir y volver no repite el consumo. Por ejemplo, una unidad de chocolate en desayuno, comida y cena descuenta tres unidades si la persona está en casa en las tres comidas. Dos personas pueden producir dos consumos independientes en cada comida.

Es una estimación basada en presencia, no una confirmación de haber comido el producto. Las personas sin presencia en casa registrada dentro de la franja no generan consumo. Un estado desconocido o no disponible no se considera presencia en casa. Los consumos aparecen en Logs → Stock. El mínimo y la lista de reposición funcionan como en el resto de controles de Stock.

El registro de cada franja, persona, producto y día de inicio se guarda junto con la cantidad de Stock. Un reinicio no repite los descuentos. Si la franja sigue abierta y se registra presencia en casa después del reinicio, puede contarse el consumo pendiente; no se recuperan franjas ya terminadas durante las que Home Assistant estuvo detenido. Guardar la configuración no añade existencias: se reponen desde tickets o manualmente.

## Requisitos

Se utilizan las entidades nativas `person.*` de Home Assistant y su estado `home`. Cada persona debe tener un seguimiento de presencia configurado en Home Assistant y la zona de casa correctamente definida. Los horarios utilizan la zona horaria de Home Assistant. No se necesitan tarjetas de HACS, servicios externos ni complementos adicionales.

Las rutinas antiguas conservan sus identificadores y productos asociados. Su hora anterior pasa a ser el inicio de una franja de una hora, que se puede editar. El ajuste anterior de permanencia mínima se retira.
