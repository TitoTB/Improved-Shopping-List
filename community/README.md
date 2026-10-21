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

Los iconos requieren tres confirmaciones y metadatos contrastados contra Iconify.
Se conservan autor, licencia y procedencia. No se infiere una licencia por el
dominio o por popularidad. Las URL manuales y archivos de origen desconocido
permanecen locales. El ZIP de exportación anterior sigue disponible por separado.

## Administración sin revisar aportaciones

El mantenedor configura `community/policy.json` en `main`:

- `blocked_github_ids`: IDs numéricos de cuentas excluidas. Se ignoran nuevos
  envíos y sus votos/precios dejan de publicarse al regenerar el diccionario.
- `minimum_account_age_days`: antigüedad mínima para contar confirmaciones.
- `allowed_licenses`: licencias admisibles para iconos.
- `allowed_image_hosts`: fuentes permitidas; actualmente solo `api.iconify.design`.
- `excluded_icon_prefixes`: colecciones excluidas.

Cambiar la política regenera el diccionario automáticamente. No concede a los
usuarios permisos para editarla. Bloquear una cuenta no impide descargar datos
públicos; GitHub permite además bloquearla para impedir nuevos Issues.

`registry.json` de `data` conserva observaciones e identificadores públicos para
deduplicar votos y recalcular bloqueos; no contiene credenciales. Al empezar el
diccionario está vacío. Los datos se actualizan sin una nueva versión de HACS.

Nutri-Score obtenido de Open Food Facts se debe a esa base de datos:
https://world.openfoodfacts.org/ — licencia ODbL:
https://opendatacommons.org/licenses/odbl/1-0/.
