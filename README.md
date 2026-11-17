# INGEFIX · Control y disponibilidad de inventario

Software local para complementar Softland con conteo cíclico ABC, etiquetas Code 128,
escaneo móvil, compromisos próximos, predicción de salidas, ROP explicado, recepción
parcial y conciliación logística de notas de crédito.

## Ejecutar

Python 3.12+. Abrir INICIAR.bat o ejecutar `python app/server.py`.
Para teléfono, INICIAR_MOVIL.bat; usar la dirección /bodega y su código exclusivo.
Mantener el servidor encendido. HTTPS y usuarios individuales son necesarios para
una instalación compartida sostenida; la cámara en vivo en teléfono requiere HTTPS.

Este repositorio no contiene documentos ni datos operativos de la empresa. Un clon
inicia vacío. Importar primero maestro y saldos reales mediante Integración. La guía
inicial explica orden, riesgos y valor de las acciones. No hay productos ni ventas
de demostración cargados en la base operativa.

## Softland

Conector ODBC de solo lectura con autenticación Windows o configuración administrada
por TI. Las vistas documentadas son contratos propios: versión, licencia, acceso y
mapeo deben validarse para el servidor real. No se escriben tablas ni se emiten DTE.
La lectura programada funciona mientras este servidor está encendido.

Una nota de crédito no aumenta existencias por sí sola. La devolución se cuenta y
se concilia con una entrada del ERP. El pronóstico utiliza historia por SKU/fecha y
validación temporal; no transforma totales monetarios de la sucursal en ventas ficticias.

Consultar [operación](docs/OPERACION_V3.md) y [valor para INGEFIX](docs/VALOR_PARA_INGEFIX.md).
Pruebas: `python -m unittest discover -s tests -v`; las que requieren fuentes privadas
se omiten cuando esos archivos no están disponibles.
