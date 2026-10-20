# Historial de cambios

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
