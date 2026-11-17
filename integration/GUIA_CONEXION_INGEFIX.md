# Conectar INGEFIX con Softland desde la red de la empresa

## Estado actual

El adaptador de INGEFIX puede leer CSV o vistas SQL Server autorizadas en modo solo lectura y cargar los registros validados a la aplicación. No escribe saldos, documentos ni compras en Softland.

La aplicación pública de Render es una demostración. Un servicio alojado fuera de INGEFIX no puede abrir por sí solo una conexión a la base privada de la empresa. Para sincronizar datos reales, el adaptador y el servicio de INGEFIX deben ejecutarse dentro de la red de la empresa, o TI debe aprobar y proteger expresamente un canal saliente hacia el servicio.

La conexión no está activada todavía: hacen falta versión y licencia de Softland, servidor/base, acceso de lectura y mapeo aprobado por TI. Este repositorio no contiene credenciales ni nombres de tablas internas inventados.

## Preparación de TI

1. Confirmar versión, módulos y método de integración disponible en la instalación Softland de INGEFIX (API/WMS publicada por el proveedor u ODBC de SQL Server).
2. Elegir un equipo servidor dentro de la red de la empresa. El servicio debe tener respaldos persistentes, acceso controlado y HTTPS para el uso móvil.
3. Si se usa ODBC, instalar Microsoft ODBC Driver 18 for SQL Server y `pyodbc` en ese equipo. Crear un usuario SQL con permiso `SELECT` solamente sobre vistas autorizadas; no reutilizar la cuenta administrativa del ERP.
4. TI debe crear o mapear las vistas de lectura y comprobar sus resultados con el encargado de bodega. Los nombres `vw_INGEFIX_*` del adaptador son nombres de contrato configurables, no tablas nativas garantizadas de Softland.
5. Filtrar maestro y saldos por la bodega Temuco `08`. Las vistas de movimientos, demanda, notas de crédito, recepciones y compromisos también deben filtrar explícitamente empresa, bodega, documentos anulados y unidades según la configuración real.

## Columnas del contrato

| Tipo | Columnas requeridas |
|---|---|
| Maestro | `code,name,warehouse,unit` |
| Saldo | `code,warehouse,stock,reserved,in_transit,snapshot_at` |
| Demanda diaria | `code,day,quantity` |
| Nota de crédito | `id,code,quantity,day,reference,reason,inventory_effect` |
| Recepción | `id,code,expected,source_doc,day,status` |
| Compromiso de abastecimiento | `id,code,ordered,delivered,due_date,reference,status` |
| Movimiento | `id,code,day,entry,exit,document` |

Usar un identificador documental estable que distinga empresa, tipo de documento, folio, bodega y línea. Las notas de crédito deben indicar `return`, `no_stock` o `unknown`; emitir/importar una nota no debe sumar existencias automáticamente. Una devolución física se cuenta y se concilia con la entrada registrada en el ERP.

## Activar el puente

1. En el servidor de INGEFIX, preparar el entorno Python del proyecto e instalar las dependencias de ODBC aprobadas por TI.
2. Configurar la cadena ODBC como variable de entorno `INGEFIX_ODBC_CONNECTION`. Guardarla en el almacén de secretos del servidor, nunca en Git ni en `integration/config.py`.
3. En INGEFIX, completar Integración Softland con el servidor/base, el nombre de cada vista autorizada y los módulos que TI haya validado.
4. Iniciar el servicio INGEFIX en ese servidor. En la misma máquina, ejecutar primero una vista previa sin `--apply`:

   ```powershell
   python integration/sync_softland.py --odbc --kind stock --url http://127.0.0.1:8765
   ```

5. Contrastar cantidad de filas, productos y saldos con un reporte de Softland para la bodega 08. Repetir con `master`, `demand` y los documentos que se habiliten. No avanzar si un conteo no concilia.
6. Tras aprobación de TI y de bodega, habilitar la aplicación de cargas. Ejemplo para una prueba supervisada:

   ```powershell
   python integration/sync_softland.py --odbc --kind stock --url http://127.0.0.1:8765 --apply
   ```

   Para un ciclo cada cinco minutos, añadir `--watch 300`; mantener el proceso activo con el supervisor de servicios aprobado por TI. La primera prueba no debe activar `--watch`.
7. Importar maestro y saldos, definir ubicaciones verificadas y confirmar período de ventas, plazo y colchón antes de usar alertas ROP. El panel debe mostrar el último intento real; una conexión no comprobada no debe aparecer como activa.

## Límites de seguridad y puesta en producción

- Mantener el usuario SQL en solo lectura y permitir solo las vistas aprobadas.
- No abrir el puerto SQL a Internet. No publicar la cadena de conexión ni códigos de acceso.
- El adaptador manda registros al `--url` elegido. Para producción, ese destino debe ser el servicio persistente y protegido que apruebe INGEFIX; el enlace público gratuito de demostración no es almacenamiento operativo.
- El prototipo no crea órdenes de compra, traslados ni asientos de inventario en Softland. Esa escritura requiere un contrato/API oficial, permisos y pruebas separados.
- Validar actualización, reversa, duplicados, notas de crédito y recepciones parciales antes de activar una sincronización periódica.
