"""Prototipo local: API REST + SQLite + interfaz sin dependencias de ejecución."""
import argparse
import csv
import hashlib
import io
import json
import math
import mimetypes
import os
import secrets
import sqlite3
import threading
import uuid
import webbrowser
import ipaddress
import importlib.util
import sys
import socket
import logging
import urllib.request
from http.cookies import SimpleCookie
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from domain import DEFAULT_SETTINGS, enrich
import workflows
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integration'))
import config as integration_config

ROOT = Path(__file__).resolve().parents[1]
DB = Path(os.environ.get('INGEFIX_DB_PATH',ROOT/'data'/'ingefix.db'))
LOCK = threading.RLock()
ACCESS_CODE = None
WAREHOUSE_CODE = None
SESSIONS = {}
RUNNING_REVISION = hashlib.sha256(b''.join((ROOT/p).read_bytes() for p in ('app/server.py','app/domain.py','app/static/app.js','app/static/operations.js','app/static/barcodes.js'))).hexdigest()[:16]
WORKSPACE_ID = hashlib.sha256(str(ROOT).lower().encode()).hexdigest()[:16]
SYNC_STATUS={'last_attempt':None,'connected':False,'message':'Sin lectura comprobada'}
FRONTEND_ORIGIN=os.environ.get('INGEFIX_FRONTEND_ORIGIN','https://ingefix-control-logistico-ui.onrender.com').rstrip('/')


class InventoryHTTPServer(ThreadingHTTPServer):
    # En Windows SO_REUSEADDR permite que varias instancias compartan el puerto.
    # El acceso exclusivo evita respuestas mezcladas entre versiones diferentes.
    allow_reuse_address = os.name != 'nt'
    def server_bind(self):
        if os.name=='nt':self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        super().server_bind()


def now(): return datetime.now(timezone.utc).isoformat()
class Connection(sqlite3.Connection):
    def __exit__(self,*args):
        try:return super().__exit__(*args)
        finally:self.close()


def connect():
    c = sqlite3.connect(DB, timeout=20, factory=Connection)
    c.row_factory = sqlite3.Row
    return c

def seed_data():
    path=ROOT/'data'/'seed.json'
    if path.exists():return json.loads(path.read_text(encoding='utf-8'))
    return dict(products=[],sources=[],metadata=dict(snapshot_at='',warehouse='08',warehouse_name='Temuco',rotation_products=0,stock_products=0,matched=0,rotation_period='Sin datos importados',pdf_range='Sin datos importados'))


def initialize():
    DB.parent.mkdir(exist_ok=True)
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS products(code TEXT PRIMARY KEY,name TEXT,group_name TEXT,subgroup TEXT,
          avg_stock REAL,outbound REAL,rotation REAL,erp_stock REAL,warehouse TEXT,unit TEXT,snapshot_at TEXT,
          location TEXT,reserved REAL DEFAULT 0,in_transit REAL DEFAULT 0,snapshot_version TEXT);
        CREATE TABLE IF NOT EXISTS counts(id TEXT PRIMARY KEY,code TEXT,quantity REAL,expected REAL,
          location TEXT,operator TEXT,reason TEXT,note TEXT,created_at TEXT,snapshot_version TEXT,status TEXT);
        CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,code TEXT,quantity REAL,status TEXT,created_at TEXT,
          scenario INTEGER,reason TEXT);
        CREATE TABLE IF NOT EXISTS daily(code TEXT,day TEXT,quantity REAL,PRIMARY KEY(code,day));
        CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY,body TEXT);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT,action TEXT,detail TEXT);
        CREATE TABLE IF NOT EXISTS imports(hash TEXT PRIMARY KEY,created_at TEXT,kind TEXT,rows INTEGER);
        CREATE TABLE IF NOT EXISTS metadata(id INTEGER PRIMARY KEY,body TEXT);
        ''')
        workflows.initialize(db)
        if not db.execute('SELECT 1 FROM metadata').fetchone():
            seed = seed_data()
            for p in seed['products']:
                p.update(reserved=0,in_transit=0,snapshot_version='seed-20261116')
                db.execute('INSERT INTO products VALUES ('+','.join('?' for _ in range(15))+')',
                           [p[k] for k in ('code','name','group_name','subgroup','avg_stock','outbound','rotation',
                            'erp_stock','warehouse','unit','snapshot_at','location','reserved','in_transit','snapshot_version')])
            db.execute('INSERT INTO metadata VALUES(1,?)',(json.dumps(seed),))
            log(db,'Carga inicial','Archivos originales: bodega 08. Saldos ERP, sin conteos físicos.')
        if not db.execute('SELECT 1 FROM settings').fetchone():
            db.execute('INSERT INTO settings VALUES(1,?)',(json.dumps(DEFAULT_SETTINGS),))
        else:
            previous=json.loads(db.execute('SELECT body FROM settings WHERE id=1').fetchone()[0])
            if previous.get('planning_version')!=2:
                merged=dict(DEFAULT_SETTINGS,**previous)
                for k in ('lead_days','buffer_days','review_days'):merged[k]=None
                if not previous.get('period_confirmed'):merged['period_days']=None
                merged.update(planning_version=2,planning_confirmed=False)
                db.execute('UPDATE settings SET body=? WHERE id=1',(json.dumps(merged),))
                log(db,'Retiro de supuestos','Plazos y colchón de demostración retirados. ROP requiere parámetros confirmados.')
        # El Excel no informa unidad de medida: retirar el antiguo fallback UN de
        # productos que siguen exactamente en la carga inicial sin saldo PDF.
        seed=seed_data()
        for p in seed['products']:
            if p['erp_stock'] is None:
                db.execute("UPDATE products SET unit=NULL WHERE code=? AND snapshot_version='seed-20261116'",(p['code'],))
        ledger=ROOT/'data'/'ledger.json'
        if ledger.exists() and not db.execute("SELECT 1 FROM workflow_imports WHERE hash='verified-pdf-ledger-v1'").fetchone():
            extracted=json.loads(ledger.read_text(encoding='utf-8'))
            for r in extracted['daily']:
                db.execute('INSERT OR IGNORE INTO daily VALUES(?,?,?)',(r['code'],r['day'],r['quantity']))
            for r in extracted['events']:
                db.execute('INSERT OR IGNORE INTO erp_movements VALUES(?,?,?,?,?,?,?)',(r['id'],r['code'],r['day'],r['entry'],r['exit'],r['text'][-170:],r['source']+' · página '+str(r['page'])))
            db.execute('INSERT INTO workflow_imports VALUES(?,?,?,?)',('verified-pdf-ledger-v1','ledger',len(extracted['daily']),now()))
            log(db,'Historial real validado',f"PDF: {extracted['summary']['validated_products']} bloques conciliados; {extracted['summary']['days']} días; transferencias y devoluciones excluidas de demanda bruta.")


def log(db, action, detail):
    db.execute('INSERT INTO audit(created_at,action,detail) VALUES(?,?,?)',(now(),action,detail))


def state(db):
    settings = json.loads(db.execute('SELECT body FROM settings WHERE id=1').fetchone()[0])
    counts = [dict(r) for r in db.execute('SELECT * FROM counts ORDER BY created_at DESC')]
    orders = [dict(r) for r in db.execute('SELECT * FROM orders ORDER BY created_at DESC')]
    daily=[dict(r) for r in db.execute('SELECT * FROM daily')]
    products = enrich([dict(r) for r in db.execute('SELECT * FROM products')],settings,counts,daily,orders)
    operation=workflows.read_state(db,products)
    meta = json.loads(db.execute('SELECT body FROM metadata WHERE id=1').fetchone()[0])
    meta.pop('products', None)
    imports = [dict(r) for r in db.execute('SELECT * FROM imports ORDER BY created_at DESC LIMIT 20')]
    last_sync=db.execute("SELECT created_at FROM audit WHERE action='Sincronización SQL de lectura' ORDER BY id DESC LIMIT 1").fetchone()
    integration=dict(configured=bool(integration_config.connection()),driver_available=bool(importlib.util.find_spec('pyodbc')),last_sync=last_sync[0] if last_sync else None,configuration=integration_config.load(),runtime=dict(SYNC_STATUS))
    evidence=json.loads((ROOT/'data'/'evidence.json').read_text(encoding='utf-8')) if (ROOT/'data'/'evidence.json').exists() else {}
    return dict(products=products,settings=settings,counts=counts,orders=orders,metadata=meta,imports=imports,evidence=evidence,demand_history=daily,integration=integration,workflows=operation,
                audit=[dict(r) for r in db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 150')],
                today=date.today().isoformat(),mode='local',connection='Archivos exportados · Softland no conectado')


def number(value, name, minimum=0, maximum=1e12):
    if isinstance(value, bool): raise ValueError(f'{name}: número requerido')
    try: n = float(value)
    except (ValueError,TypeError): raise ValueError(f'{name}: número requerido (decimal con punto)')
    if not math.isfinite(n) or not minimum <= n <= maximum:
        raise ValueError(f'{name}: debe estar entre {minimum} y {maximum}')
    return n


def required(value, name, limit=250):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:
        raise ValueError(f'{name}: texto requerido, máximo {limit} caracteres')
    return value.strip()


def parse_import(db, body):
    kind = body.get('kind')
    fields = dict(stock=['code','warehouse','stock','reserved','in_transit','snapshot_at'],
                  demand=['code','day','quantity'],master=['code','name','warehouse','unit'])
    if kind not in fields: raise ValueError('Tipo de importación no válido')
    content = required(body.get('csv'),'CSV',5_000_000).lstrip('\ufeff')
    reader = csv.DictReader(io.StringIO(content), delimiter=';' if ';' in content.splitlines()[0] else ',')
    if not set(fields[kind]).issubset(reader.fieldnames or []):
        raise ValueError('Columnas requeridas: '+','.join(fields[kind]))
    known = {r[0] for r in db.execute('SELECT code FROM products')}
    seen = set(); rows=[]
    for i,r in enumerate(reader,2):
        code = required(r.get('code'),f'Fila {i}: code',100)
        if code not in known and kind!='master': raise ValueError(f'Fila {i}: SKU desconocido {code}. Cargar primero el maestro de productos.')
        if kind=='master':
            if r['warehouse']!='08':raise ValueError(f'Fila {i}: solo bodega 08')
            row=dict(code=code,name=required(r.get('name'),'Descripción',250),warehouse='08',unit=required(r.get('unit'),'Unidad',30))
            key=code
        elif kind=='stock':
            if r['warehouse']!='08': raise ValueError(f'Fila {i}: solo bodega 08; no mezclar sucursales')
            stamp = date.fromisoformat(r['snapshot_at'])
            if stamp>date.today(): raise ValueError(f'Fila {i}: fecha futura')
            row = dict(code=code,warehouse='08',stock=number(r['stock'],'stock',-1e12),
                       reserved=number(r['reserved'],'reserved'),in_transit=number(r['in_transit'],'in_transit'),snapshot_at=stamp.isoformat())
            current=db.execute('SELECT snapshot_at FROM products WHERE code=?',(code,)).fetchone()[0]
            if stamp.isoformat()<current: raise ValueError(f'Fila {i}: snapshot anterior al saldo cargado')
            key=code
        else:
            stamp = date.fromisoformat(r['day'])
            if stamp>date.today(): raise ValueError(f'Fila {i}: fecha futura')
            row=dict(code=code,day=stamp.isoformat(),quantity=number(r['quantity'],'quantity'))
            key=(code,row['day'])
        if key in seen: raise ValueError(f'Fila {i}: clave repetida {key}')
        seen.add(key); rows.append(row)
        if len(rows)>30000: raise ValueError('Máximo 30.000 filas por archivo')
    if not rows: raise ValueError('CSV sin registros')
    digest=hashlib.sha256((kind+json.dumps(rows,sort_keys=True)).encode()).hexdigest()
    exists=bool(db.execute('SELECT 1 FROM imports WHERE hash=?',(digest,)).fetchone())
    return kind,rows,digest,exists


def mutate(db,path,b):
    if path in ('/api/documents/preview','/api/documents/import','/api/inbound','/api/physical-events','/api/commitments','/api/reconcile','/api/credit-classify','/api/event-document'):
        return workflows.mutate(db,path,b,(required,number,now,log))
    if path=='/api/counts':
        count_id=str(uuid.UUID(required(b.get('request_id'),'Identificador de conteo',80)))
        if db.execute('SELECT 1 FROM counts WHERE id=?',(count_id,)).fetchone():
            return dict(id=count_id,already_saved=True)
        code=required(b.get('code'),'SKU',100)
        p=db.execute('SELECT * FROM products WHERE code=?',(code,)).fetchone()
        if not p: raise ValueError('SKU no encontrado')
        loc=str(b.get('location') or p['location'] or '').strip()[:80]
        if p['location'] and loc!=p['location']: raise ValueError('Location does not match the registered shelf location.')
        if any(ord(ch)<32 for ch in loc):raise ValueError('Location has invalid control characters.')
        if b.get('snapshot_version')!=p['snapshot_version']: raise ValueError('El saldo cambió: actualice antes de contar')
        qty=number(b.get('quantity'),'Cantidad')
        op=required(b.get('operator'),'Responsable',80)
        reason=required(b.get('reason'),'Motivo',80)
        note=str(b.get('note',''))[:1000]
        if p['erp_stock'] is not None and qty!=p['erp_stock'] and reason=='Sin diferencia':
            raise ValueError('Existe diferencia: indique el motivo o seleccione Por investigar')
        if loc and not p['location']:
            db.execute('UPDATE products SET location=? WHERE code=?',(loc,code))
            log(db,'Location observed during count',f'{code}: {loc}')
        db.execute('INSERT INTO counts VALUES(?,?,?,?,?,?,?,?,?,?,?)',(count_id,code,qty,p['erp_stock'],loc,op,reason,note,now(),p['snapshot_version'],'pendiente' if qty!=p['erp_stock'] else 'coincide'))
        log(db,'Conteo fisico',f'{code}: {qty} en {loc or "location pending"}, responsable {op}; sin ajuste de Softland')
        return dict(id=count_id)
    if path=='/api/locations':
        code=required(b.get('code'),'SKU',100);loc=required(b.get('location'),'Location',80)
        if any(ord(ch)<32 for ch in loc):raise ValueError('Location has invalid control characters.')
        if not db.execute('SELECT 1 FROM products WHERE code=?',(code,)).fetchone():raise ValueError('SKU no encontrado')
        db.execute('UPDATE products SET location=? WHERE code=?',(loc,code))
        log(db,'Ubicación asignada',f'{code}: {loc} (asignación de prototipo; verificar en bodega)')
        return dict(ok=True)
    if path=='/api/settings':
        s=json.loads(db.execute('SELECT body FROM settings WHERE id=1').fetchone()[0])
        for k,lo,hi in [('period_days',1,1095),('lead_days',1,120),('buffer_days',0,120),('review_days',1,120),('growth_pct',-90,300),('count_a',1,365),('count_b',1,365),('count_c',1,365)]:
            s[k]=None if k in ('period_days','lead_days','buffer_days','review_days') and b.get(k) in (None,'') else number(b.get(k),k,lo,hi)
        if not isinstance(b.get('period_confirmed'),bool):raise ValueError('Confirmación de período inválida')
        s['period_confirmed']=b['period_confirmed']
        if not isinstance(b.get('planning_confirmed'),bool):raise ValueError('Confirme explícitamente la política de reposición')
        s['planning_confirmed']=b['planning_confirmed']
        if s['planning_confirmed'] and any(s[k] is None for k in ('lead_days','buffer_days','review_days')):raise ValueError('Complete plazo, colchón y revisión antes de confirmar')
        if s['period_confirmed'] and s['period_days'] is None:raise ValueError('Faltan los días reales del reporte de salidas')
        db.execute('UPDATE settings SET body=? WHERE id=1',(json.dumps(s),))
        log(db,'Política de inventario',json.dumps(s,ensure_ascii=False))
        return dict(ok=True)
    if path=='/api/abc-settings':
        s=json.loads(db.execute('SELECT body FROM settings WHERE id=1').fetchone()[0])
        a=number(b.get('abc_a'),'Umbral A',1,98);threshold=number(b.get('abc_b'),'Umbral B',2,99)
        if threshold<=a:raise ValueError('El umbral acumulado B debe ser mayor que A')
        s.update(abc_a=a,abc_b=threshold)
        for k in ('count_a','count_b','count_c'):s[k]=number(b.get(k),k,1,365)
        db.execute('UPDATE settings SET body=? WHERE id=1',(json.dumps(s),))
        log(db,'Clasificador ABC',f'ABC por volumen: A hasta {a}%, B hasta {threshold}%. Frecuencias actualizadas.')
        return dict(ok=True)
    if path=='/api/orders':
        code=required(b.get('code'),'SKU',100)
        p=next((p for p in state(db)['products'] if p['code']==code),None)
        if not p or not p['suggested']:raise ValueError('No existe necesidad calculada para este producto')
        if db.execute("SELECT 1 FROM orders WHERE code=? AND status IN ('borrador','aprobada')",(code,)).fetchone():
            raise ValueError('Ya existe una solicitud abierta para este SKU')
        qty=number(b.get('quantity'),'Cantidad',.001)
        ident='REP-'+uuid.uuid4().hex[:8].upper()
        reason=f"Posición {p['position']}; ROP {p['rop']}; saldo del {p['snapshot_at']}"
        db.execute('INSERT INTO orders VALUES(?,?,?,?,?,?,?)',(ident,code,qty,'borrador',now(),int(p['scenario']),reason))
        log(db,'Solicitud en borrador',f'{ident}: {code}, {qty} unidades; no enviada a Santiago')
        return dict(id=ident)
    if path=='/api/order-status':
        ident=required(b.get('id'),'Solicitud',80);target=b.get('status')
        row=db.execute('SELECT * FROM orders WHERE id=?',(ident,)).fetchone()
        allowed={'borrador':['aprobada','cancelada'],'aprobada':['cerrada','cancelada']}
        if not row or target not in allowed.get(row['status'],[]):raise ValueError('Transición de estado inválida')
        db.execute('UPDATE orders SET status=? WHERE id=?',(target,ident))
        log(db,'Estado de solicitud',f'{ident}: {target}. Sin movimiento de inventario ni envío externo.')
        return dict(ok=True)
    if path=='/api/review-count':
        ident=required(b.get('id'),'Conteo');op=required(b.get('operator'),'Revisor',80)
        note=required(b.get('note'),'Conclusión de revisión',1000)
        row=db.execute('SELECT * FROM counts WHERE id=?',(ident,)).fetchone()
        if not row or row['status']!='pendiente':raise ValueError('El conteo ya no está pendiente')
        db.execute("UPDATE counts SET status='revisado' WHERE id=?",(ident,))
        log(db,'Diferencia revisada',f'{row["code"]}: {op}: {note}. Ajuste ERP requiere procedimiento autorizado de Softland.')
        return dict(ok=True)
    if path in ('/api/import/preview','/api/import/commit'):
        kind,rows,digest,exists=parse_import(db,b)
        if path.endswith('preview'):
            return dict(hash=digest,rows=len(rows),sample=rows[:5],already_imported=exists,kind=kind)
        if b.get('hash')!=digest:raise ValueError('El archivo cambió: vuelva a previsualizar')
        if exists:return dict(ok=True,already_imported=True,rows=0)
        for r in rows:
            if kind=='master':
                db.execute('''INSERT INTO products(code,name,warehouse,unit,location,snapshot_at,snapshot_version)
                    VALUES(?,?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET name=excluded.name,unit=excluded.unit''',
                    (r['code'],r['name'],r['warehouse'],r['unit'],'','',digest))
            elif kind=='stock':
                db.execute('UPDATE products SET erp_stock=?,reserved=?,in_transit=?,snapshot_at=?,snapshot_version=? WHERE code=?',
                           (r['stock'],r['reserved'],r['in_transit'],r['snapshot_at'],digest,r['code']))
            else:
                db.execute('INSERT INTO daily VALUES(?,?,?) ON CONFLICT(code,day) DO UPDATE SET quantity=excluded.quantity',
                           (r['code'],r['day'],r['quantity']))
        db.execute('INSERT INTO imports VALUES(?,?,?,?)',(digest,now(),kind,len(rows)))
        log(db,'Importación validada',f'{kind}: {len(rows)} filas; SHA256 {digest}')
        return dict(ok=True,rows=len(rows))
    raise ValueError('Operación no soportada')


def csv_safe(value):
    return "'"+value if isinstance(value,str) and value.startswith(('=','+','-','@','\t','\r')) else value


def integration_read(apply=False):
    if not integration_config.connection():
        return dict(connected=False,message='Falta configurar INGEFIX_ODBC_CONNECTION en el servidor de la aplicación. No se ha consultado Softland. TI debe proporcionar una conexión de lectura y validar el mapeo de maestro y saldos.')
    if not importlib.util.find_spec('pyodbc'):
        return dict(connected=False,message='La conexión está indicada, pero falta instalar pyodbc y el driver ODBC de SQL Server en este equipo. No se ha establecido una conexión con Softland.')
    sys.path.insert(0,str(ROOT/'integration')) if str(ROOT/'integration') not in sys.path else None
    from sync_softland import read_sql
    try:
        kinds=integration_config.load()['modules']
        if os.environ.get('INGEFIX_SYNC_DEMAND')=='1' and 'demand' not in kinds:kinds=kinds+['demand']
        kinds=sorted(kinds,key=lambda k:0 if k=='master' else 1 if k=='stock' else 2)
        bodies=[dict(kind=kind,csv=read_sql(kind)) for kind in kinds]
        with LOCK,connect() as db:
            results=[]
            for body in bodies:
                documentary=body['kind'] in workflows.FIELDS
                preview=mutate(db,'/api/documents/preview' if documentary else '/api/import/preview',body)
                if apply:mutate(db,'/api/documents/import' if documentary else '/api/import/commit',dict(body,hash=preview['hash']))
                # La previsualización de stock requiere los SKU nuevos del maestro; sin aplicar,
                # validar el contrato completo en una transacción que se revierte al finalizar.
                elif body['kind']=='master':mutate(db,'/api/import/commit',dict(body,hash=preview['hash']))
                results.append(f"{body['kind']}: {preview['rows']} filas")
            if apply:log(db,'Sincronización SQL de lectura','; '.join(results))
            else:db.rollback()
        return dict(connected=True,applied=apply,message=('Lectura sincronizada en INGEFIX. ' if apply else 'Conexión y contratos validados, sin guardar cambios. ')+'; '.join(results)+'. Sin escritura en Softland.')
    except Exception:
        # Los errores de driver pueden contener servidor/usuario. No se reflejan al navegador.
        return dict(connected=False,message='No se pudo completar la lectura. TI debe revisar conectividad, certificados, permisos SELECT y las vistas de contrato dbo.vw_INGEFIX_Products / dbo.vw_INGEFIX_Stock. No se guardó una sincronización parcial ni se escribió en Softland.')


class Handler(BaseHTTPRequestHandler):
    server_version='INGEFIX/0.1'
    def authorized(self):
        if not ACCESS_CODE:return True
        try:
            cookie=SimpleCookie(self.headers.get('Cookie',''))
            return 'ingefix_session' in cookie and cookie['ingefix_session'].value in SESSIONS
        except Exception:return False
    def session_role(self):
        try:
            cookie=SimpleCookie(self.headers.get('Cookie',''))
            return SESSIONS.get(cookie['ingefix_session'].value,'admin') if 'ingefix_session' in cookie else 'admin'
        except Exception:return 'admin'
    def valid_host(self):
        host=self.headers.get('Host','').split(':')[0]
        if host=='localhost':return True
        if host.lower().endswith(('.trycloudflare.com','.onrender.com')):return True
        try:return ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback
        except ValueError:return False
    def expected_origin(self):
        host=self.headers.get('Host','')
        return ('https://' if host.lower().endswith(('.trycloudflare.com','.onrender.com')) else 'http://')+host
    def allowed_origin(self,origin):
        return bool(origin and origin in (self.expected_origin(),FRONTEND_ORIGIN))
    def send_cors_headers(self):
        origin=self.headers.get('Origin')
        if self.allowed_origin(origin):
            self.send_header('Access-Control-Allow-Origin',origin)
            self.send_header('Access-Control-Allow-Credentials','true')
            self.send_header('Vary','Origin')
    def send(self,status,data,kind='application/json; charset=utf-8',extra_headers=None):
        content=json.dumps(data,ensure_ascii=False,allow_nan=False).encode() if kind.startswith('application/json') else data
        self.send_response(status)
        for k,v in [('Content-Type',kind),('Content-Length',str(len(content))),('Cache-Control','no-store'),
                    ('X-Content-Type-Options','nosniff'),('Referrer-Policy','same-origin'),
                    ('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'self'")]:self.send_header(k,v)
        if urlparse(self.path).path.startswith('/api/'):self.send_cors_headers()
        for k,v in (extra_headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(content)
    def do_OPTIONS(self):
        if not self.valid_host():return self.send(403,dict(error='Host no permitido'))
        if not urlparse(self.path).path.startswith('/api/') or not self.allowed_origin(self.headers.get('Origin')):
            return self.send(403,dict(error='Origen no permitido'))
        self.send_response(204)
        self.send_cors_headers()
        self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type')
        self.send_header('Access-Control-Max-Age','600')
        self.send_header('Content-Length','0')
        self.end_headers()
    def do_GET(self):
        if not self.valid_host():return self.send(403,dict(error='Host no permitido'))
        path=urlparse(self.path).path
        if not self.authorized() and path not in ('/login.js','/style.css','/icon.svg'):
            if path.startswith('/api/'):return self.send(401,dict(error='Inicie sesión en el servidor local'))
            return self.send(200,(ROOT/'app'/'static'/'login.html').read_bytes(),'text/html; charset=utf-8')
        if self.session_role()=='warehouse' and path.startswith('/api/') and path not in ('/api/state','/api/health'):
            return self.send(403,dict(error='Acceso de bodega: escaneo y conteo únicamente'))
        if path=='/api/state':
            try:
                with LOCK,connect() as db:result=state(db)
                result['session_role']=self.session_role()
                if self.session_role()=='warehouse':
                    result['workflows']={};result['orders']=[];result['audit']=[];result['imports']=[];result['demand_history']=[];result['evidence']={};result['integration']={};result['metadata']['sources']=[]
                return self.send(200,result)
            except Exception:
                logging.exception('Error al cargar el estado de inventario')
                return self.send(500,dict(error='No se pudo cargar el inventario. Consulte data/server.log; reinicie INICIAR.bat para cargar la versión actual.'))
        if path=='/api/source':
            name=parse_qs(urlparse(self.path).query).get('name',[''])[0]
            seed=seed_data()
            allowed={f['name'] for f in seed['sources']}
            file=(ROOT/name).resolve()
            if name not in allowed or file.parent!=ROOT or not file.is_file():return self.send(404,dict(error='Fuente no disponible'))
            return self.send(200,file.read_bytes(),mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
        if path=='/api/abc-export':
            with LOCK,connect() as db:products=state(db)['products']
            out=io.StringIO();w=csv.writer(out,delimiter=';')
            w.writerow(['codigo_softland','descripcion','clase_abc','salidas','rotacion','participacion_pct','acumulado_pct','ubicacion'])
            for p in sorted(products,key=lambda p:p['volume_rank'] or 100000):
                w.writerow([csv_safe(v) for v in [p['code'],p['name'],p['abc'],p['outbound'],p['rotation'],round(p['share']*100,4),round(p['cumulative_share']*100,4),p['location']]])
            return self.send(200,('\ufeff'+out.getvalue()).encode(),'text/csv; charset=utf-8',{'Content-Disposition':'attachment; filename="clasificacion-abc.csv"'})
        if path=='/api/export':
            with LOCK,connect() as db:rows=[dict(r) for r in db.execute('SELECT * FROM orders ORDER BY created_at DESC')]
            out=io.StringIO();w=csv.writer(out,delimiter=';');w.writerow(['id','code','quantity','status','created_at','scenario','reason'])
            for r in rows:w.writerow([csv_safe(v) for v in r.values()])
            return self.send(200,('\ufeff'+out.getvalue()).encode(),'text/csv; charset=utf-8',{'Content-Disposition':'attachment; filename="solicitudes-ingefix.csv"'})
        if path=='/api/health':return self.send(200,dict(ok=True,application='ingefix',revision=RUNNING_REVISION,workspace=WORKSPACE_ID,mode='local',erp_connected=False))
        if path in ('/','/bodega'):path='/index.html'
        file=(ROOT/'app'/'static'/path.lstrip('/')).resolve()
        if not file.is_relative_to((ROOT/'app'/'static').resolve()) or not file.is_file():return self.send(404,dict(error='No encontrado'))
        kind=mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
        if kind.startswith(('text/','application/javascript','image/svg+xml')) and 'charset=' not in kind:kind+='; charset=utf-8'
        self.send(200,file.read_bytes(),kind)
    def do_POST(self):
        if not self.valid_host():return self.send(403,dict(error='Host no permitido'))
        # API local sin cookies ni CORS. JSON obligatorio bloquea POST simple desde otros sitios.
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.send(415,dict(error='Solo application/json'))
        origin=self.headers.get('Origin')
        if origin and not self.allowed_origin(origin):return self.send(403,dict(error='Origen no permitido'))
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<=0 or length>6_000_000:raise ValueError('Tamaño de petición no permitido')
            b=json.loads(self.rfile.read(length))
            if not isinstance(b,dict):raise ValueError('Objeto JSON requerido')
            if urlparse(self.path).path=='/api/login':
                supplied=str(b.get('code',''))
                role='warehouse' if WAREHOUSE_CODE and secrets.compare_digest(supplied,WAREHOUSE_CODE) else 'admin' if ACCESS_CODE and secrets.compare_digest(supplied,ACCESS_CODE) else None
                if not role:
                    return self.send(403,dict(error='Código de acceso incorrecto'))
                token=secrets.token_urlsafe(32);SESSIONS[token]=role
                content=b'{"ok":true}'
                self.send_response(200)
                self.send_header('Content-Type','application/json')
                self.send_header('Cache-Control','no-store')
                self.send_header('Set-Cookie',f'ingefix_session={token}; HttpOnly; SameSite=Strict; Path=/')
                self.send_cors_headers()
                self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
                return
            if not self.authorized():return self.send(401,dict(error='Acceso requerido'))
            if self.session_role()=='warehouse' and urlparse(self.path).path not in ('/api/counts','/api/locations'):
                return self.send(403,dict(error='Acceso de bodega: escaneo y conteo únicamente'))
            if urlparse(self.path).path=='/api/integration/config':
                if not ipaddress.ip_address(self.client_address[0]).is_loopback:return self.send(403,dict(error='Configure la conexión desde el equipo servidor, no desde el teléfono de bodega'))
                integration_config.save(b)
                with LOCK,connect() as db:log(db,'Configuración de integración','Acceso Windows y módulos configurados; no implica lectura exitosa.')
                return self.send(200,dict(ok=True))
            if urlparse(self.path).path in ('/api/integration/test','/api/integration/sync'):
                result=integration_read(urlparse(self.path).path.endswith('/sync'))
                SYNC_STATUS.update(last_attempt=now(),connected=result['connected'],message=result['message'])
                return self.send(200,result)
            with LOCK,connect() as db:result=mutate(db,urlparse(self.path).path,b)
            self.send(200,result)
        except (ValueError,KeyError,TypeError) as e:self.send(400,dict(error=str(e)))
        except sqlite3.Error:self.send(500,dict(error='No se pudo guardar. Revise la base de datos local.'))


def main():
    global ACCESS_CODE,WAREHOUSE_CODE
    parser=argparse.ArgumentParser(description='INGEFIX · Prototipo logístico local')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--host',default=os.environ.get('HOST','127.0.0.1'))
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--lan',action='store_true',help='Piloto en red local con código de acceso temporal')
    parser.add_argument('--public-demo',action='store_true',help='Demostración pública sin código de acceso')
    args=parser.parse_args()
    if args.public_demo:ACCESS_CODE=None;WAREHOUSE_CODE=None
    (ROOT/'data').mkdir(exist_ok=True)
    logging.basicConfig(filename=ROOT/'data'/'server.log',level=logging.ERROR,format='%(asctime)s %(levelname)s %(message)s',encoding='utf-8')
    initialize()
    if args.lan:ACCESS_CODE=secrets.token_urlsafe(12);WAREHOUSE_CODE=secrets.token_urlsafe(9)
    server=None
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for candidate_port in range(args.port,args.port+12):
        url=f'http://127.0.0.1:{candidate_port}'
        try:
            server=InventoryHTTPServer(('0.0.0.0' if args.lan else args.host,candidate_port),Handler)
            args.port=candidate_port
            break
        except OSError:
            try:
                with opener.open(url+'/api/health',timeout=2) as response:health=json.load(response)
                if health.get('revision')==RUNNING_REVISION and health.get('workspace')==WORKSPACE_ID:
                    with opener.open(url+'/api/state',timeout=5) as response:json.load(response)
                    print(f'INGEFIX ya está en ejecución: {url}. Se utiliza esa instancia.',flush=True)
                    if not args.no_browser:webbrowser.open(url)
                    return
            except Exception:pass
            print(f'Puerto {candidate_port} ocupado por otra instancia. Buscando un puerto libre...',flush=True)
    if server is None:
        print('No se encontró un puerto libre. Vuelva a iniciar con --port y otro número.',flush=True)
        raise SystemExit(1)
    print(f'INGEFIX listo en {url} · Ctrl+C para detener',flush=True)
    (ROOT/'ABRIR_INGEFIX.url').write_text('[InternetShortcut]\nURL='+url+'\n',encoding='utf-8')
    stop_sync=threading.Event()
    def sync_loop():
        while not stop_sync.is_set():
            try:
                c=integration_config.load()
                if c['enabled']:
                    result=integration_read(True);SYNC_STATUS.update(last_attempt=now(),connected=result['connected'],message=result['message'])
            except Exception:logging.exception('Sincronización programada no completada')
            stop_sync.wait(max(60,integration_config.load()['interval']))
    threading.Thread(target=sync_loop,daemon=True).start()
    if args.lan:
        addresses=sorted({a[4][0] for a in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET) if not a[4][0].startswith('127.')})
        (ROOT/'data'/'public-access-codes.txt').write_text('Código administrador: '+str(ACCESS_CODE)+'\nCódigo exclusivo de bodega: '+str(WAREHOUSE_CODE)+'\n',encoding='utf-8')
        print('Piloto LAN · mismo Wi-Fi/red. No exponer este puerto a Internet.',flush=True)
        for address in addresses:print(f'Telefono: http://{address}:{args.port}',flush=True)
        print(f'Codigo administrador: {ACCESS_CODE}',flush=True)
        for address in addresses:print(f'BODEGA: http://{address}:{args.port}/bodega',flush=True)
        print(f'Codigo exclusivo de bodega: {WAREHOUSE_CODE}',flush=True)
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:stop_sync.set();server.server_close()


if __name__=='__main__':main()
