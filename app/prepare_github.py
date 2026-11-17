"""Prepara código publicable sin documentos, base o configuración de la empresa."""
import json
import shutil
import zipfile
from pathlib import Path

root=Path(__file__).resolve().parents[1];target=root/'github-source';target.mkdir(exist_ok=True)
for folder in ('app','integration','tests'):
    for source in (root/folder).rglob('*'):
        if not source.is_file() or '__pycache__' in source.parts or source.name=='build_evidence.py':continue
        destination=target/source.relative_to(root);destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
for name in ('INICIAR.bat','INICIAR_MOVIL.bat','.gitignore','requirements-import.txt'):
    shutil.copy2(root/name,target/name)
for name in ('OPERACION_V3.md','VALOR_PARA_INGEFIX.md'):
    (target/'docs').mkdir(exist_ok=True);shutil.copy2(root/'docs'/name,target/'docs'/name)
(target/'README.md').write_text('''# INGEFIX · Control y disponibilidad de inventario

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
''',encoding='utf-8')
workflow=target/'.github'/'workflows';workflow.mkdir(parents=True,exist_ok=True)
(workflow/'tests.yml').write_text('''name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: python -m unittest discover -s tests -v
''',encoding='utf-8')
with zipfile.ZipFile(root/'INGEFIX-codigo-github.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for path in target.rglob('*'):
        rel=path.relative_to(target)
        approved=rel.parts[0] in ('app','integration','tests','docs','.github') or len(rel.parts)==1 and rel.name in ('README.md','.gitignore','INICIAR.bat','INICIAR_MOVIL.bat','requirements-import.txt')
        if path.is_file() and approved and '__pycache__' not in path.parts and path.suffix not in ('.db','.log','.pyc'):archive.write(path,rel)
print('Código preparado en github-source; datos privados excluidos.')
