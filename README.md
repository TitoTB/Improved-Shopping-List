# Improved Shopping List

<img src="custom_components/improved_shopping_list/brand/icon.png" alt="Improved Shopping List" width="96">

Una interfaz propia para gestionar las listas de la compra que ya tienes integradas en Home Assistant.

Versión actual: **0.1.1**. Interfaz en español, pensada para móvil y ordenador. Requiere **Home Assistant Core 2026.10 o posterior**. La referencia de desarrollo es Core 2026.10.2.

## Qué puedes hacer

- Seleccionar cualquier entidad `todo.*` disponible para tu usuario, incluida Bring!, Shopping List u otros proveedores.
- Consultar productos pendientes y comprados.
- Añadir productos, marcarlos como comprados y volver a ponerlos por comprar.
- Recibir cambios del proveedor mediante la API nativa de listas de Home Assistant.
- Cambiar de lista desde el panel y cambiar la predeterminada desde la configuración de la integración.

Cada lista conserva sus datos en su integración original. Las operaciones disponibles dependen de lo que admita ese proveedor. Por ejemplo, una lista de solo lectura se puede consultar, pero sus controles de edición aparecen desactivados. La frecuencia con la que Bring! u otro proveedor recibe cambios de su nube depende de su propia integración.

El panel se comunica con Home Assistant usando la sesión del usuario y las APIs nativas. No necesita tokens adicionales, cuentas nuevas ni servicios externos. El JavaScript se sirve localmente y no utiliza un CDN.

## Instalación con HACS

Este repositorio se instala como repositorio personalizado; no está incluido en el catálogo predeterminado de HACS.

1. En HACS, abre el menú de los tres puntos → **Repositorios personalizados**.
2. Añade `https://github.com/TitoTB/Improved-Shopping-List` con tipo **Integración**.
3. Busca **Improved Shopping List**, descarga la última versión y reinicia Home Assistant.
4. Abre **Ajustes → Dispositivos y servicios → Añadir integración**.
5. Busca **Improved Shopping List** y selecciona tu lista de la compra predeterminada.
6. Abre **Improved Shopping List** desde la barra lateral.

Si no tienes ninguna entidad `todo.*`, configura antes Bring!, Shopping List u otra integración que proporcione listas. No necesitas añadir YAML ni recursos de dashboard manualmente.

Si el panel no aparece después de instalar, recarga la página o cierra y abre la aplicación de Home Assistant. Tras actualizar, una recarga completa también permite descartar una versión antigua del JavaScript.

## Actualizaciones

Las versiones se publican en GitHub. HACS permite detectar y descargar las nuevas versiones. Por defecto, decide tú cuándo instalarlas y reiniciar Home Assistant; esta integración no activa instalaciones automáticas.

Para publicar una versión, los mantenedores actualizan la versión en `manifest.json`, `const.py`, `package.json`, la referencia de módulo y el texto de versión en `frontend/panel.js`, el lockfile y `CHANGELOG.md`. Después suben una etiqueta `vX.Y.Z`. GitHub Actions ejecuta las comprobaciones y publica la release si pasan. Los cambios en la rama principal sin una nueva versión no se publican automáticamente como una actualización estable.

## Alcance de esta primera versión

El objetivo inicial es comprobar el funcionamiento del panel y su interoperabilidad con las listas existentes. Todavía no hay catálogo propio, lector de códigos, consulta de Open Food Facts, precios, scrapeo ni importación de PDF.

La configuración de la lista predeterminada se guarda en Home Assistant. El selector del panel permite abrir otra lista durante la sesión; no modifica la predeterminada. Para cambiarla de forma permanente, utiliza **Configurar** en la integración.

Eliminar la integración retira el panel; los productos siguen en sus listas originales.

## Desarrollo y comprobaciones

La integración Python registra la configuración y el panel. La interfaz utiliza un Web Component sin proceso de compilación. `todo-client.js` encapsula las llamadas nativas y la gestión de suscripciones; no duplica el almacenamiento del proveedor.

```sh
npm ci
npm run check
npm test
npx playwright install chromium
npm run test:ui
python -m compileall -q custom_components
```

Las pruebas de navegador utilizan una API de Home Assistant simulada. Comprueban la interfaz y sus llamadas, pero no sustituyen la prueba final en una instancia real con Bring! u otro proveedor. Las capturas se generan en `test-results/`.

GitHub Actions añade las validaciones de Hassfest y HACS. También ejecuta pruebas de configuración, registro del panel, cambios de opciones, recarga y entrega de archivos usando Home Assistant Core 2026.10.2 real sobre Linux. Para ejecutarlas localmente necesitas Python 3.14.2 o posterior: `pip install -r requirements_test.txt` y `pytest -q`.

La instalación real en Home Assistant debe comprobarse con el recorrido siguiente:

1. Configurar la integración con Bring! y abrir el panel.
2. Añadir un producto y comprobar que aparece en Bring!.
3. Marcarlo como comprado y devolverlo a pendientes.
4. Editar la lista desde Bring!, esperar a que su integración reciba el cambio y comprobar el panel.
5. Cambiar a otra entidad `todo.*` y comprobar que no se mezclan sus productos.
6. Cambiar la lista predeterminada desde Configurar y reiniciar Home Assistant.

## Licencia

MIT. Consulta [LICENSE](LICENSE).
