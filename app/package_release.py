"""Empaqueta el prototipo sin bases operativas, cachés ni archivos de origen."""
import sqlite3
import zipfile
from pathlib import Path

root=Path(__file__).resolve().parents[1]
paths=[]
for directory in ('app','docs','integration','tests'):
    paths.extend(p for p in (root/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
paths.extend(root/p for p in ('README.md','INICIAR.bat','INICIAR_MOVIL.bat','requirements-import.txt','data/seed.json','data/evidence.json','data/ledger.json','data/clasificacion_productos.csv'))
sources=__import__('json').loads((root/'data'/'seed.json').read_text(encoding='utf-8'))['sources']
paths.extend(root/f['name'] for f in sources)
if (root/'artifacts'/'etiquetas-clase-A.pdf').is_file():paths.append(root/'artifacts'/'etiquetas-clase-A.pdf')
with zipfile.ZipFile(root/'INGEFIX-prototipo.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for path in paths:
        archive.write(path,'INGEFIX/'+path.relative_to(root).as_posix())
with zipfile.ZipFile(root/'INGEFIX-prototipo.zip','r') as archive:
    invalid=archive.testzip()
    if invalid:raise ValueError('Archivo corrupto en paquete: '+invalid)
    print(f'Entrega verificada: {len(archive.namelist())} archivos.',flush=True)
con=sqlite3.connect(root/'data'/'ingefix.db',timeout=5)
try:
    print({table:con.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('products','counts','orders','imports')},flush=True)
finally:con.close()
