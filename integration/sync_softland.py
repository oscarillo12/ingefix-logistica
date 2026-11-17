"""Puente de lectura: CSV o vista SQL validada por TI -> API local INGEFIX.

No conoce ni modifica tablas internas de Softland. pyodbc es opcional.
"""
import argparse
import csv
import io
import json
import os
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path
import config as integration_config


def read_sql(kind):
    try: import pyodbc
    except ImportError: raise ValueError('Para ODBC instale pyodbc y el driver SQL Server; CSV no necesita dependencias')
    connection = integration_config.connection()
    if not connection: raise ValueError('Falta INGEFIX_ODBC_CONNECTION (use un usuario SQL solo lectura o autenticación Windows)')
    # Son vistas nuevas del contrato de INGEFIX. No son objetos estándar de Softland.
    query = {
        'master': 'SELECT code,name,warehouse,unit FROM dbo.vw_INGEFIX_Products WHERE warehouse = ?',
        'stock': 'SELECT code,warehouse,stock,reserved,in_transit,snapshot_at FROM dbo.vw_INGEFIX_Stock WHERE warehouse = ?',
        'demand': 'SELECT code,day,quantity FROM dbo.vw_INGEFIX_DailyDemand',
        'credits': 'SELECT id,code,quantity,day,reference,reason,inventory_effect FROM dbo.vw_INGEFIX_CreditNotes',
        'inbound': 'SELECT id,code,expected,source_doc,day,status FROM dbo.vw_INGEFIX_Inbound',
        'commitments': 'SELECT id,code,ordered,delivered,due_date,reference,status FROM dbo.vw_INGEFIX_Commitments',
        'movements': 'SELECT id,code,day,entry,exit,document FROM dbo.vw_INGEFIX_Movements',
    }[kind]
    for key,default_view in integration_config.DEFAULT_VIEWS.items():
        if key==kind:query=query.replace(default_view,integration_config.load()['views'][key])
    with pyodbc.connect(connection, timeout=15, readonly=True) as con:
        cur=con.cursor();cur.timeout=60
        cur.execute(query,'08') if kind in ('stock','master') else cur.execute(query)
        out=io.StringIO();writer=csv.writer(out);writer.writerow([c[0] for c in cur.description])
        count=0
        while True:
            batch=cur.fetchmany(1000)
            if not batch:break
            for row in batch:
                writer.writerow([v.isoformat()[:10] if hasattr(v,'isoformat') else v for v in row])
                count+=1
                if count>30000:raise ValueError('Divida la extracción: máximo 30.000 filas por carga')
        return out.getvalue()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument('--csv',type=Path,help='Exportación normalizada con columnas del contrato')
    source.add_argument('--odbc',action='store_true',help='Leer vistas creadas por TI con credenciales solo lectura')
    p.add_argument('--kind',choices=['master','stock','demand','credits','inbound','commitments','movements'],default='stock')
    p.add_argument('--url',default='http://127.0.0.1:8765')
    p.add_argument('--apply',action='store_true',help='Confirmar carga local después de la validación (por defecto solo previsualiza)')
    p.add_argument('--watch',type=int,default=0,help='Repetir cada N segundos, mínimo 60')
    args=p.parse_args()
    if args.watch and args.watch<60:p.error('--watch debe ser al menos 60 segundos')
    if args.watch and not args.apply:p.error('--watch requiere --apply')
    if not args.url.startswith(('http://127.0.0.1:','http://localhost:','https://')):
        p.error('Ejecute el puente junto al servidor local o use HTTPS')
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    def call(path,data):
        req=urllib.request.Request(args.url.rstrip('/')+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
        try:
            with opener.open(req,timeout=90) as r:return json.load(r)
        except urllib.error.HTTPError as e:
            try:message=json.load(e).get('error',str(e.code))
            except Exception:message=str(e.code)
            raise ValueError(message)
    code=os.environ.get('INGEFIX_ACCESS_CODE')
    if code:call('/api/login',{'code':code})
    while True:
        try:
            content=args.csv.read_text(encoding='utf-8-sig') if args.csv else read_sql(args.kind)
            body=dict(kind=args.kind,csv=content)
            documentary=args.kind in ('credits','inbound','commitments','movements')
            preview=call('/api/documents/preview' if documentary else '/api/import/preview',body)
            print(f"{preview['rows']} filas válidas · huella {preview['hash'][:12]} · ya cargado: {preview['already_imported']}",flush=True)
            if args.apply and not preview['already_imported']:
                result=call('/api/documents/import' if documentary else '/api/import/commit',dict(body,hash=preview['hash']))
                print(f"Carga local completada: {result['rows']} filas. Sin escritura en ERP.",flush=True)
        except (ValueError,OSError) as e:
            print(f'Sincronización no aplicada: {e}',flush=True)
            if not args.watch:raise SystemExit(1)
        if not args.watch:break
        time.sleep(args.watch)


if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:pass
