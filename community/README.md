# Diccionario comunitario de iconos

La integración consulta `community/products.json` de la rama `data` como máximo una vez cada 24 horas. La consulta no requiere cuenta GitHub. El diccionario solo propone iconos a partir de nombres, traducciones y términos alternativos; no rellena otros campos del catálogo.

Con consentimiento en **Ajustes → Comunidad**, un administrador autoriza la GitHub App mediante un código. Las aportaciones son públicas y están asociadas a esa cuenta. Solo incluyen nombres, traducciones e identificadores de iconos admitidos. No incluyen EAN, referencias o enlaces de tiendas, precios, Nutri-Score, tickets, facturas, stock, listas, NFC ni automatizaciones.

La app es https://github.com/apps/improved-shopping-list-community. No se reutilizan credenciales de HACS. Los tokens se guardan en almacenamiento privado de Home Assistant y no se entregan al navegador ni a los logs. Desactivar el consentimiento elimina las credenciales locales y detiene futuros envíos.

## Intercambio y validación

Un lote diario utiliza un Issue con manifiesto y comentarios comprimidos. Se validan autor, origen de la app, tamaños y huellas. Los reintentos reanudan el mismo lote sin duplicarlo. El límite por cuenta es de un lote cada 24 horas, incluso con varias instalaciones.

Los iconos requieren tres confirmaciones de cuentas elegibles y metadatos de licencia contrastados con Iconify. Una selección explícita de una propuesta comunitaria suma una preferencia, sin crear una nueva confirmación independiente. Las URL manuales, imágenes de origen desconocido e imágenes de Flaticon permanecen locales.

Se conserva compatibilidad con el sobre JSON de versiones anteriores: los campos comerciales se descartan en la entrada y se publican vacíos. El registro actual se migra a votos de iconos agrupados por términos, retirando precios, códigos y referencias antiguas. No se reescribe el historial Git. Los lotes locales pendientes del protocolo anterior se descartan para que el siguiente envío contenga únicamente iconos.

## Administración

La política de `community/policy.json` permite bloquear cuentas mediante `blocked_github_ids`, exigir antigüedad mínima y autorizar licencias, colecciones y fuentes de iconos. Cambiar la política regenera el diccionario; no concede permisos de edición a los usuarios.

El registro se divide en 16 archivos en la rama `data`. Los clientes descargan solo `products.json` y los iconos elegidos. El registro no se incluye en HACS y sus actualizaciones no requieren publicar la integración.

Para recuperar una versión fiable, abre **Actions → Community dictionary → Run workflow** e indica el SHA de la rama `data` en `restore_registry_commit`. Se procesa únicamente JSON con el código actual, se conservan los límites de aportaciones y se genera un nuevo commit sin sobrescribir decisiones locales.
