# Tiendas archivadas

Alcampo y DIA están archivados. Las demás tiendas siguen disponibles como antes.

Alcampo y DIA mantienen su implementación y sus datos locales. No se borran las vinculaciones del catálogo, códigos EAN, compras, precios, opciones de actualización ni fechas de revisión guardadas. Tampoco se eliminan los normalizadores de URL/ID: son necesarios para leer las asociaciones existentes.

`custom_components/improved_shopping_list/store_availability.py` define `AVAILABLE_STORES`. Los ajustes recibidos por la interfaz indican qué tiendas mostrar. Las activaciones archivadas se enmascaran solo en la vista de configuración que consume la integración; las opciones originales permanecen guardadas. No cuentan como tiendas activas ni pueden convertirse en favorita o activarse desde un cliente antiguo. El favorito efectivo pasa a una tienda disponible y activa, si existe.

Los planificadores de precios públicos comprueban esta capacidad antes de arrancar, por lo que una instalación con revisiones antiguas activadas no continúa consultando las webs. Se conserva la caché para consultar el histórico. La restricción afecta a Alcampo y DIA.

## Código que se conserva

- Alcampo: `alcampo.py`, `price_sources.py`, `frontend/alcampo-settings.js` y sus comandos WebSocket.
- DIA público: `dia.py`, `dia_prices.py`, `frontend/dia-prices-settings.js` y sus comandos WebSocket.
- Investigación de cuenta DIA: `dia_account.py`, `dia_receipts.py`, `dia_websocket.py` y `frontend/dia-account.js`. El acceso real a la cuenta sigue sin estar resuelto; no se utiliza en la recuperación automática de tickets.
- Ubicaciones de referencia: `store_location.py`.
- Referencias y precios históricos: `store_links.py`, `price_manager.py` y `price_history.py`.

## Recuperación futura

Para volver a ofrecer un conector, hay que validar primero el comportamiento deseado y añadir su identificador a `AVAILABLE_STORES`. Los paneles de configuración existentes y los planificadores públicos volverán a estar disponibles sin reconstruir sus datos. Para incorporar una nueva fuente de tickets hay que registrar, además, su conector de cuenta en `TicketAccounts`; cambiar la lista de capacidades por sí solo no añade esa función.

Los tests de la política actual verifican la conservación de datos, la imposibilidad de activar tiendas archivadas y la ausencia de consultas. Los escenarios históricos que prueban conectores conservados usan explícitamente la fixture `archived_store_capabilities`; esa fixture amplía las capacidades solo durante esas pruebas.
