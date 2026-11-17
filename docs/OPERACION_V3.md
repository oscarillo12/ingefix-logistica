# Operación guiada de INGEFIX · v0.3

## Inicio y perfil de bodega

Ejecutar INICIAR.bat para administración. La guía inicial explica ocho etapas y puede repetirse desde **Guía paso a paso**. Cada pantalla ofrece ayuda contextual con el riesgo logístico, la tarea y el valor esperado. La guía no modifica inventarios ni crea transacciones.

Para teléfono, ejecutar INICIAR_MOVIL.bat y mantener abierta la consola. El servidor muestra direcciones de red y dos códigos: administrador y bodega. En el teléfono abrir la dirección terminada en `/bodega` e ingresar el código exclusivo de bodega. Este perfil ve cola de verificación, escáner y conteo, y la API bloquea configuración, documentos y exportaciones. Localhost sin autenticación permite previsualizar ambos perfiles; para una instalación sostenida todavía se necesitan usuarios individuales, HTTPS y servicio supervisado.

La cola da prioridad a productos en o bajo el ROP, compromisos de los próximos siete días y conteos ABC vencidos. El ROP usa una política explícita de colchón en días; sin plazo y política confirmados no se generan umbrales ficticios. Un conteo realizado hoy contra el mismo corte evita repetir esa verificación automáticamente. Una diferencia queda para revisión administrativa.

La vista de bodega consulta tareas cada 30 segundos mientras está abierta. Informa cambios de prioridad y usa vibración si el dispositivo lo admite. **No hay notificaciones push con el navegador cerrado** ni funcionamiento sin red. Cámara en vivo requiere contexto seguro HTTPS en teléfono; se puede leer una foto o usar un lector que actúe como teclado.

## Pronóstico usando los documentos entregados

Se extrajeron 1.807 movimientos del registro PDF de existencias. Los bloques de 401 SKU concilian apertura + entradas − salidas con el saldo final; dos se excluyen por no superar esa validación. La serie cubre 47 días, del 01/10 al 16/11/2026. Se incluyen como demanda bruta solo salidas físicas a cliente: despachos por facturar, salidas desde bodega a cliente y ventas con boleta. Transferencias, ajustes y devoluciones no se cuentan como demanda bruta.

Los días sin salida registrada se completan en cero únicamente dentro de bloques completos y conciliados. Esto modela **salidas observadas**, no pedidos no atendidos. Un producto agotado puede vender menos de lo que los clientes necesitaban.

Con al menos 35 observaciones continuas se comparan media móvil, suavizado exponencial y Croston SBA en orígenes temporales. Se reserva un mínimo de 21 observaciones iniciales y hasta 28 fechas para validación de un día. Los 47 días del PDF permiten 26 orígenes, pero siguen siendo un historial corto: no justifican una estacionalidad anual ni una garantía de nivel de servicio. La UI muestra modelo, MAE, porcentaje de días en cero, fuente y antigüedad. Para mejorar el modelo, sincronizar demanda diaria y registrar quiebres/demanda no atendida.

El libro de ventas resumido conserva los totales de la sucursal; no se reparte entre productos para fabricar ventas diarias.

## Recepciones y entregas parciales

Preparar una recepción con una solicitud real o sincronizar líneas de abastecimiento. Registrar cada entrega con total recibido, cantidad apta, documento y responsable. El sistema rechaza excedentes no documentados sobre el pendiente y cantidades aptas mayores que el total. Si falta guía, conserva la incidencia; se puede incorporar la referencia después.

Una recepción física **no aumenta el saldo ERP**. Después de registrar el ingreso por el mecanismo autorizado de Softland, sincronizar el movimiento y vincularlo con la observación. La conciliación exige mismo SKU, entrada igual a cantidad apta, salida cero y fecha no anterior a la observación. Un movimiento no se reutiliza. Una devolución parcial, daño o recepción sin guía queda visible.

## Notas de crédito

Sincronizar una línea por nota y producto con ID estable. Clasificar su efecto logístico como `no_stock` (corrección comercial), `return` (devolución física) o `unknown` (por investigar). La revisión local registra responsable y fundamento; **no cambia el documento tributario en Softland**.

Solo una nota clasificada como devolución permite registrar recepción física. Se cuentan unidades y se separan aptas de dañadas. El retorno queda pendiente de conciliación con una entrada del ERP. No se suman unidades por importar una nota y no se resta nuevamente demanda histórica por una mera corrección de precio. Las anulaciones/correcciones deben revisarse conservando los vínculos documentales.

## Integración directa y programada

En Integración, configurar servidor/base, driver ODBC y vistas de lectura autorizadas. La configuración local usa autenticación Windows y no guarda contraseña. También puede utilizarse una conexión de entorno administrada por TI. Seleccionar los módulos disponibles y la frecuencia; maestro y saldos son la base. Las vistas son contratos propios, no nombres garantizados de tablas de Softland.

| Módulo | Columnas requeridas |
|---|---|
| Maestro | code,name,warehouse,unit |
| Saldo | code,warehouse,stock,reserved,in_transit,snapshot_at |
| Demanda | code,day,quantity |
| Nota de crédito | id,code,quantity,day,reference,reason,inventory_effect |
| Abastecimiento | id,code,expected,source_doc,day,status |
| Compromiso | id,code,ordered,delivered,due_date,reference,status |
| Movimiento | id,code,day,entry,exit,document |

ID documental debe distinguir empresa, tipo, folio, bodega y línea. `status` es active, closed o cancelled. Las vistas deben filtrar bodega 08, convertir unidades y excluir anulaciones según el esquema real; los contratos documentales no incluyen campo warehouse y dependen de ese filtro de TI. No se debe leer otra sucursal como Temuco.

Comprobar conexión valida la lectura sin guardar documentos. Sincronizar confirma la carga atómica de los módulos seleccionados. La lectura periódica se ejecuta mientras el servidor de la aplicación está encendido y la configuración está habilitada. Al fallar una fuente no se aplica la carga parcial. La API no escribe tablas ni emite DTE en Softland.

El conector está implementado y probado con contratos controlados, pero **no se ha conectado al servidor real de INGEFIX**: falta versión, acceso autorizado, driver y mapeo de vistas por TI. El software informa ese estado; no simula una lectura exitosa.

## Uso sencillo para el operador

El inicio «Qué hago ahora» propone una tarea y permite desplegar los indicadores del encargado. «Cómo se conecta todo» muestra el recorrido: pedido por entregar → conteo físico → solicitud de reposición → recepción → comprobación con Softland. Cada pantalla incluye tres ayudas pequeñas y fijas.

«Pedidos por preparar» sirve para detectar faltantes antes de armar un pedido. Se ingresa producto, cantidad pendiente y fecha real de entrega. Los pedidos dentro de los próximos siete días priorizan el conteo en bodega; no descuentan por segunda vez el inventario reservado en Softland.

El botón «Vista del teléfono» abre la aplicación de bodega dentro de una ventana. Es una vista real: guardar un conteo allí también lo registra. En el teléfono se ve una tarea, el motivo en lenguaje cotidiano, la ubicación y el escáner con vista previa. Después de leer la etiqueta se pide cantidad observada y responsable. Las observaciones son opcionales. No se muestran saldos antes de contar.

Las tareas se actualizan cada treinta segundos mientras la pantalla está abierta. La lectura en vivo depende del permiso de cámara y de HTTPS en el teléfono; se puede usar una foto o un lector de mano. No hay notificaciones con el navegador cerrado.

## Datos privados y GitHub

El paquete de entrega local incluye las fuentes de la empresa. La carpeta preparada para GitHub excluye documentos originales, SQLite, historial extraído, exportaciones, configuración local y registros. Un clon sin datos inicia vacío y permite importar el maestro real. Se recomienda repositorio privado. No almacenar credenciales ni publicar documentos de clientes.
