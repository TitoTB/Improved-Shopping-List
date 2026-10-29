# Lidl: enlaces y formatos de los tickets

Durante la revisión y el reprocesamiento de un ticket, la integración intenta completar las alternativas de Lidl vinculadas con productos del catálogo. No conecta cuentas nuevas ni consulta productos ajenos al ticket.

El orden es caché local por IAN, diccionario público por EAN exacto cuando esa alternativa tiene EAN y consulta pública de Lidl. El diccionario se conserva en Home Assistant y se comprueban sus cambios como máximo una vez al día. Una URL manual se conserva y se comprueba antes de usar sus datos.

Los tickets contienen un IAN, distinto del identificador de la URL web. Los listados de ofertas y alimentación incluyen ambos. Se aceptan coincidencias exactas y únicas; los ceros iniciales no distinguen un IAN de otro. Un nombre parecido no es suficiente. No se inventa un EAN a partir del IAN ni se utiliza el EAN de otro formato del mismo producto genérico.

Se leen como máximo cuatro páginas conocidas por cada consulta diaria de listados, con veinte segundos entre peticiones, límite de tamaño y pausa ante HTTP 403/429/503. Las respuestas se guardan localmente y los productos de un mismo ticket comparten esa caché. La cobertura depende de los productos publicados en esos listados. Un código sin coincidencia o con varias fichas queda disponible para completar manualmente.

Un popup muestra el progreso de los productos. Cuando falta el contenido por envase, se propone el recuperado de la web. Los packs como 8 × 125 g corresponden a 1000 g por envase vendido; comprar dos packs no cambia ese formato unitario. Los formatos procedentes únicamente de una oferta futura se señalan para confirmar que corresponden al envase comprado. Se conservan las cantidades explícitas del ticket, los formatos ya informados y las correcciones manuales realizadas mientras se consulta.

La consulta no sustituye el precio pagado por el precio anunciado en la web. La URL, la marca y los datos confirmados se incorporan al guardar la revisión o al pulsar Guardar datos en el reprocesamiento. Descartar la ficha no modifica el catálogo. Reprocesar no crea otra compra ni repone Stock o cambia los importes históricos.

La alternativa conserva `ticket_reference_id` con el IAN y `reference_id` con la referencia web. Esto permite reconocer siguientes tickets sin duplicar la alternativa y abrir correctamente la ficha de Lidl. No requiere dependencias nuevas.
