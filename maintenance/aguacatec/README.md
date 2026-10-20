# Publicación del catálogo de Carrefour

Esta carpeta prepara el enlace con el descargador de Awin de Aguacatec. No contiene
credenciales, datos de Carrefour ni una tarea activada. La publicación debe
habilitarse después de confirmar las condiciones de distribución del feed y sus
enlaces de afiliado.

## Datos públicos

Cada producto contiene exactamente `ean`, `name`, `price` (decimal como texto),
`currency` (`EUR`) y `affiliate_url` (enlace original de Awin). El identificador
`merchant_product_id` del feed 84214 contiene el EAN; se valida su dígito de control.
No se exportan imágenes, descripciones, claves ni datos del catálogo de los usuarios.
Este feed no contiene Nutri-Score. Open Food Facts lo proporciona por separado.
Los precios no corresponden a un código postal concreto ni garantizan existencias.

La rama `data` del mismo repositorio alojará:

- `carrefour/manifest.json`: versión, fecha de preparación, fecha del feed de origen,
  cantidad de registros, referencias, tamaños y hashes SHA-256.
- `carrefour/snapshots/<hash>.json`: catálogo completo validado.
- `carrefour/deltas/<hash>.json`: altas, cambios y bajas desde la versión anterior.

Home Assistant consulta el manifiesto cada 24 horas y utiliza ETag. Si tiene la base
del delta lo aplica; si no, descarga el catálogo completo. Comprueba los hashes
antes de sustituir su copia local. Los errores conservan los precios anteriores y
se registran en Logs. La versión de los datos es independiente de la integración:
instalar soporte de Carrefour requiere una actualización inicial, los precios
posteriores no requieren actualizaciones de HACS.

## Preparar y comprobar sin publicar

Desde la copia de Improved Shopping List:

```powershell
python scripts/shopping_feed.py --input RUTA_PRIVADA/feed.csv.gz --output RUTA_PRIVADA/carrefour
```

La carpeta de salida debe estar fuera del repositorio. Un feed vacío, truncado,
con códigos duplicados, precios no válidos o productos de otro anunciante se
rechaza sin cambiar el manifiesto anterior.

## Enlace con Aguacatec

1. Copiar `publish_shopping_feed.py` a
   `apps/panel/management/commands/publish_shopping_feed.py` en Aguacatec.
2. Configurar la plataforma privada `carrefour`: anunciante 25399, feed 84214 y
   clave de descarga de Awin. La clave permanece en Aguacatec.
3. Definir `SHOPPING_LIST_REPOSITORY` con la ruta de una copia de esta integración.
4. Ejecutar `python manage.py publish_shopping_feed` para preparar y validar.

El comando consulta `Last Imported` antes de descargar. Si no puede obtener esa
fecha, descarga el feed completo y compara el resultado. Genera sus propios deltas;
no presupone que Awin entregue deltas. Usa un bloqueo para evitar ejecuciones
simultáneas. Los archivos privados se guardan en `runtime/shopping_feed/carrefour`.

## Habilitar la publicación posteriormente

El publicador usa `SHOPPING_DATA_GITHUB_TOKEN`, definido solo en el entorno privado
de Aguacatec, con permiso de escritura de contenidos limitado a este repositorio.
No se incluyen claves en argumentos, archivos públicos o registros de errores.

`python manage.py publish_shopping_feed --publish` publica exclusivamente archivos
validados en una rama `data` independiente. La primera publicación crea una rama
sin historial del código; las siguientes actualizan su referencia de forma atómica,
sin sobrescritura forzada. No crean versiones, etiquetas ni releases. Los clientes
de Home Assistant no necesitan claves de GitHub ni Awin. Una edición concurrente
rechazada por GitHub deja la publicación anterior intacta.

Se incluyen plantillas de servicio y temporizador diarios para el servidor Linux.
Hay que adaptar usuario, rutas y archivo de entorno a la instalación real antes
de instalarlas. No se activan desde este repositorio. El mantenimiento deberá
vigilar el crecimiento del historial de datos y compactarlo cuando corresponda;
el catálogo completo permite recuperar clientes con versiones antiguas.
