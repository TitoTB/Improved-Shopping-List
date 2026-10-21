# Diccionario comunitario

La integración consulta `community/products.json` de la rama `data` como máximo
una vez cada 24 horas por instalación. La consulta no requiere cuenta GitHub.
Solo se rellenan datos confirmados que falten; nunca se crea automáticamente un
producto ni se sobrescriben nombres, imágenes o vinculaciones elegidos localmente.
Las vinculaciones automáticas requieren coincidencia por EAN o referencia exacta;
el nombre por sí solo no vincula variantes de tiendas.

En **Ajustes → Comunidad → Compartir mis datos de productos**, un administrador
puede autorizar la app mediante un código de GitHub. La casilla está desactivada
inicialmente. Las aportaciones son públicas y se atribuyen a esa cuenta. Incluyen
los campos admitidos del catálogo completo: nombres, traducciones, EAN válidos,
referencias y enlaces de tiendas, Nutri-Score, iconos identificables de Iconify y
precios recientes. No incluyen categorías, notas, NFC, listas, stock, lectores,
automatizaciones, IDs locales de entidades ni ubicación del usuario.

La app pública es https://github.com/apps/improved-shopping-list-community;
su Client ID no es un secreto. Solo solicita Issues de escritura y Metadata de
lectura. No se usan tokens de HACS ni una clave del mantenedor. Los tokens de
usuario y renovación se guardan en almacenamiento privado de Home Assistant,
nunca en el frontend, logs o exportaciones. Los administradores del servidor y
quienes dispongan de sus copias de seguridad deben proteger ese almacenamiento.
Desactivar la casilla borra las credenciales locales y detiene futuros envíos;
no elimina aportaciones ya públicas. También puede revocarse la autorización
desde los ajustes de aplicaciones de GitHub.

## Intercambio y validación

Un lote diario es un Issue con manifiesto y comentarios que contienen fragmentos
comprimidos del JSON permitido. No hay archivos ejecutables ni imágenes arbitrarias
en las aportaciones. Los reintentos recuperan el mismo Issue y los fragmentos ya
aceptados. El servidor aplica el límite por ID numérico de GitHub, incluso con
varias instalaciones. Las peticiones OAuth y los fragmentos no son lotes adicionales.
La descarga pública no permite imponer un límite por cuenta en el servidor.

`community.yml` ejecuta exclusivamente código de `main`. Comprueba el autor real
y que el Issue y sus comentarios procedan de la app esperada. Valida tamaños,
huellas, EAN, dominios y rutas de tienda, importes y fechas. Publica solo datos
en `data` y cierra la aportación después de confirmar el guardado.

Cada cuenta aporta como máximo un voto por campo de cada producto. Los datos
copiados de la comunidad no generan nuevas confirmaciones. Para confirmar un
nombre, traducción, EAN, Nutri-Score o vinculación se requieren tres cuentas con
antigüedad suficiente y un candidato ganador sin empate. Hasta entonces el dato
es provisional y no rellena automáticamente las fichas. Los precios se aceptan
con una aportación válida para la referencia exacta; el primero permanece hasta
que transcurran 24 horas desde su consulta, no desde su descarga o publicación.
Son observaciones comunitarias: la autorización identifica a la cuenta, no
demuestra que una instalación modificada consultase realmente la tienda.

Si existe un precio anterior, una variación de más del 50 % en cualquier dirección
queda pendiente de tres cuentas independientes con antigüedad suficiente, dentro
de las 24 horas de validez. Se conserva el precio anterior sin renovar su fecha.
El umbral y el número de coincidencias son configurables en la política del
repositorio. No puede aplicarse un porcentaje cuando todavía no hay precio previo.
Una promoción real puede necesitar esas confirmaciones adicionales.

Los iconos requieren tres confirmaciones y metadatos contrastados contra Iconify.
Se conservan autor, licencia y procedencia. No se infiere una licencia por el
dominio o por popularidad. Las URL manuales y archivos de origen desconocido
permanecen locales. El ZIP de exportación anterior sigue disponible por separado.
Elegir explícitamente un icono de la comunidad suma una preferencia para ordenar
recomendaciones, pero no una nueva confirmación independiente de su procedencia.
Flaticon no se incluye como fuente de redistribución automática: su licencia
estándar restringe las bases de datos y servicios que distribuyen los iconos.
Las imágenes manuales que utilice cada usuario localmente no se publican.

## Administración sin revisar aportaciones

El mantenedor configura `community/policy.json` en `main`:

- `blocked_github_ids`: IDs numéricos de cuentas excluidas. Se ignoran nuevos
  envíos y sus votos/precios dejan de publicarse al regenerar el diccionario.
- `minimum_account_age_days`: antigüedad mínima para contar confirmaciones.
- `max_price_variation_percent`: variación máxima sin confirmación adicional.
- `price_outlier_confirmations`: coincidencias para aceptar cambios superiores.
- `allowed_licenses`: licencias admisibles para iconos.
- `allowed_image_hosts`: fuentes permitidas; actualmente solo `api.iconify.design`.
- `allowed_icon_prefixes`: colecciones de color admitidas por la integración.
- `excluded_icon_prefixes`: colecciones excluidas.

Cambiar la política regenera el diccionario automáticamente. No concede a los
usuarios permisos para editarla. Bloquear una cuenta no impide descargar datos
públicos; GitHub permite además bloquearla para impedir nuevos Issues.

`registry.json` de `data` es un manifiesto de 16 archivos de observaciones e
identificadores públicos para deduplicar votos y recalcular bloqueos; no contiene
credenciales. Cada selección diferente se guarda una vez y las cuentas apuntan
a esa selección. Se conservan hasta 20 precios anteriores por referencia, y los
IDs recientes de lotes se mantienen acotados. Los límites de publicación son
8 MiB por archivo de registro y 16 MiB para el diccionario descargable; superar
un límite detiene la publicación y conserva la versión anterior. No es un servicio
de almacenamiento ilimitado: habrá que vigilar el crecimiento si aumenta mucho
la comunidad. Las instalaciones reciben solo `products.json` y descargan únicamente
los iconos elegidos. El registro y la rama `data` no forman parte del ZIP de HACS.
Al empezar el
diccionario está vacío. Los datos se actualizan sin una nueva versión de HACS.

## Recuperación tras abuso

1. Añadir las cuentas identificadas a `blocked_github_ids`, si procede.
2. Abrir **Actions → Community dictionary → Run workflow** en GitHub.
3. En `restore_registry_commit`, pegar el SHA completo de un commit fiable de la
   rama `data`. Dejarlo vacío ejecuta la actualización normal.

La recuperación procesa únicamente JSON histórico usando el código actual de
`main`. Genera un nuevo commit, conserva el historial Git y no rejuvenece precios
caducados. Publica huellas de revocación de los precios sustituidos. En su siguiente
sincronización, Home Assistant retira esos precios comunitarios y recupera la
observación local anterior si existe (hasta cinco se guardan por referencia).
No se revocan precios consultados directamente por el usuario a una tienda.
Las decisiones locales de nombre, imagen y vinculaciones no se sobrescriben.

Nutri-Score obtenido de Open Food Facts se debe a esa base de datos:
https://world.openfoodfacts.org/ — licencia ODbL:
https://opendatacommons.org/licenses/odbl/1-0/.
