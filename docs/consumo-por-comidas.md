# Consumo de stock por comidas

En **Ajustes → Rutinas**, crea una rutina y selecciona una o varias personas. Cada comida tiene nombre, hora, días de la semana y una casilla para activarla. Puedes añadir comidas y crear horarios distintos para fines de semana mediante filas con días diferentes. La permanencia mínima en casa es configurable y parte de 15 minutos.

En la ficha del producto, abre **Reposición → Reposición automática → Consumo por comidas**, o selecciona ese control desde su ficha de **Stock**. Marca las comidas y la cantidad a consumir por persona, expresada en las unidades de Stock. Opcionalmente indica cantidades distintas por persona; una cantidad personal de cero excluye a esa persona de ese consumo.

A la hora indicada se comprueba la presencia de cada persona y se descuenta únicamente su cantidad si llevaba en casa el tiempo mínimo. Por ejemplo, una unidad de chocolate en desayuno, comida y cena descuenta tres unidades si la persona está en casa en las tres comidas. Dos personas pueden producir dos consumos independientes en cada comida.

Es una estimación basada en presencia, no una confirmación de haber comido el producto. Las personas ausentes, desconocidas o no disponibles no generan consumo. Los consumos aparecen en Logs → Stock. El mínimo y la lista de reposición funcionan como en el resto de controles de Stock.

El registro de cada comida, persona, producto y día se guarda junto con la cantidad de Stock. Un reinicio no repite los descuentos y no se recuperan comidas pasadas durante las que Home Assistant estuvo detenido. Guardar la configuración no añade existencias: se reponen desde tickets o manualmente.

## Requisitos

Se utilizan las entidades nativas `person.*` de Home Assistant y su estado `home`. Cada persona debe tener un seguimiento de presencia configurado en Home Assistant y la zona de casa correctamente definida. Los horarios utilizan la zona horaria de Home Assistant. No se necesitan tarjetas de HACS, servicios externos ni complementos adicionales.
