# Dependencias

La integración requiere Home Assistant Core 2026.10 o posterior y utiliza sus entidades `todo` para gestionar las listas. No requiere tarjetas adicionales de HACS ni complementos de Home Assistant OS.

- **pypdf 6.21.2:** lectura local de tickets y facturas PDF. Home Assistant lo instala automáticamente a partir de `manifest.json`.
- **Leaflet 1.9.4:** biblioteca de mapas incluida en la integración, con licencia BSD-2-Clause. No requiere instalación adicional.
- **OpenStreetMap:** proporciona las teselas del mapa, con atribución visible. El navegador necesita acceso a Internet para mostrar ese fondo.

Las consultas opcionales a tiendas, Open Food Facts, Iconify y MyMemory requieren acceso a Internet. No son tarjetas ni componentes adicionales que el usuario deba instalar.
