# Historial de cambios

## 0.4.0

- Nuevo apartado Lectores para configurar lectores de códigos de barras, QR y NFC mediante entidades de Home Assistant o eventos de etiquetas NFC.
- Asociación de varios códigos a cada producto y selección de una acción por producto y lector, con lista de destino configurable y la principal por defecto.
- Protección contra lecturas repetidas, sin duplicar productos pendientes y recuperando los comprados cuando el proveedor lo permite.
- Códigos desconocidos como sugerencias para crear un producto o asociarlos a uno existente, con descartes persistentes.
- Acciones de añadir o quitar stock disponibles para configurar; su ejecución queda pendiente de implementar el inventario.
- Personalización de los degradados de productos pendientes y comprados y del número de columnas en móvil y ordenador.
- Tarjetas de la lista que cambian entre pendiente y comprado al pulsarlas, sin botones interiores.
- Alta desde sugerencias mediante la ficha completa del producto y botones Añadir y Editar del catálogo con texto más pequeño y el mismo ancho.
- Filtro de categoría al pulsar su icono en las tarjetas del catálogo.
- Eliminado el texto introductorio de la vista Lista.

## 0.3.0

- Nuevo apartado Ajustes (`mdi:cog`) para añadir entidades `todo`, quitar listas de la interfaz y elegir una principal, con configuración compartida y persistente en Home Assistant.
- Barra compacta en Lista con buscador predictivo, botón de añadir (`mdi:plus-thick`) y popup de selección de listas (`mdi:format-list-checks`).
- Búsqueda predictiva en el catálogo por nombre, marca, código de barras o etiquetas, con selección mediante teclado o toque.
- Productos de Lista y Catálogo en cuadrícula, con imagen o icono y nombre centrados, icono `mdi:shopping` por defecto y distintivo de categoría con su color.
- Gestión de categorías: crear, editar y eliminar, asignando icono MDI y color. Se conservan los productos al quitar una categoría.
- Vista Sugerencias (`mdi:creation`) para incorporar rápidamente al catálogo productos de la lista seleccionada, con descartes persistentes y sin repetir nombres.
- Degradado rojo para productos pendientes en la lista seleccionada y precio oculto en las tarjetas, manteniendo los datos guardados.
- Catálogo compartido sin selector de listas, botones Añadir y Editar con sus iconos y eliminación de los textos auxiliares solicitados.
- Migración de categorías y listas de instalaciones anteriores, sincronización entre sesiones y comprobaciones de permisos en Ajustes.

## 0.2.0

- Cabecera con logo, título y versión juntos, sin un fondo diferente al del panel.
- Navegación a la derecha entre Lista y Catálogo, con el icono `mdi:view-grid`.
- Catálogo local compartido, guardado en el almacenamiento de Home Assistant.
- Alta y edición de productos con categoría, etiquetas, marca, formato, código de barras, precio orientativo, moneda, imagen mediante URL y notas.
- Búsqueda y filtros por categoría y etiqueta.
- Añadir productos del catálogo a la entidad `todo.*` seleccionada.
- Actualizaciones del catálogo entre sesiones y detección de ediciones simultáneas.

## 0.1.2

- Icono `mdi:shopping` para el acceso al panel desde el menú lateral.

## 0.1.1

- Logo propio de la integración, incluido localmente para Home Assistant.
- Logo en la cabecera del panel y en la documentación del repositorio.
- Se conserva el archivo original facilitado por TitoTB.

## 0.1.0

- Primera versión de la integración Improved Shopping List.
- Configuración visual para seleccionar una entidad `todo.*` existente.
- Panel propio en español, adaptado a móvil y accesible desde la barra lateral.
- Selección de lista, consulta de productos pendientes y comprados, alta de productos y cambio de estado.
- Actualización del panel mediante las suscripciones nativas de Home Assistant.
- Controles adaptados a las operaciones que admite cada proveedor.
- Estructura de instalación para HACS y publicación de versiones mediante etiquetas Git.

Esta versión todavía no incluye lector de códigos, catálogo propio, precios ni procesamiento de PDF.
