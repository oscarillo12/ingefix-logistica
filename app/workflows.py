"""Operación de recepciones, devoluciones, compromisos y conciliación ERP."""
import csv
import hashlib
import io
import json
import math
import uuid
from datetime import date,timedelta

def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS inbound(id TEXT PRIMARY KEY,code TEXT,expected REAL,source_doc TEXT,day TEXT,status TEXT);
    CREATE TABLE IF NOT EXISTS credits(id TEXT PRIMARY KEY,code TEXT,quantity REAL,day TEXT,reference TEXT,reason TEXT,inventory_effect TEXT);
    CREATE TABLE IF NOT EXISTS commitments(id TEXT PRIMARY KEY,code TEXT,ordered REAL,delivered REAL,due_date TEXT,reference TEXT,status TEXT);
    CREATE TABLE IF NOT EXISTS physical_events(id TEXT PRIMARY KEY,request_id TEXT UNIQUE,kind TEXT,parent_id TEXT,code TEXT,quantity REAL,good REAL,document TEXT,operator TEXT,note TEXT,created_at TEXT,erp_movement_id TEXT UNIQUE);
    CREATE TABLE IF NOT EXISTS erp_movements(id TEXT PRIMARY KEY,code TEXT,day TEXT,entry REAL,exit REAL,document TEXT,source TEXT);
    CREATE TABLE IF NOT EXISTS workflow_imports(hash TEXT PRIMARY KEY,kind TEXT,rows INTEGER,created_at TEXT);
    ''')

FIELDS={
 'inbound':['id','code','expected','source_doc','day','status'],
 'credits':['id','code','quantity','day','reference','reason','inventory_effect'],
 'commitments':['id','code','ordered','delivered','due_date','reference','status'],
 'movements':['id','code','day','entry','exit','document'],
}

def read_state(db,products):
    inbound=[dict(r) for r in db.execute('SELECT * FROM inbound ORDER BY day DESC,id')]
    credits=[dict(r) for r in db.execute('SELECT * FROM credits ORDER BY day DESC,id')]
    physical=[dict(r) for r in db.execute('SELECT * FROM physical_events ORDER BY created_at DESC')]
    commitments=[dict(r) for r in db.execute('SELECT * FROM commitments ORDER BY due_date,id')]
    for row in inbound+credits:
        kind='receipt' if 'expected' in row else 'return'
        linked=[e for e in physical if e['kind']==kind and e['parent_id']==row['id']]
        row['received']=sum(e['quantity'] for e in linked)
        row['good']=sum(e['good'] for e in linked)
        row['remaining']=max(0,row.get('expected',row.get('quantity',0))-row['received'])
        row['without_document']=sum(not e['document'] for e in linked)
    today=date.today();horizon=today+timedelta(days=7)
    for p in products:
        rows=[c for c in commitments if c['code']==p['code'] and c['status']=='active' and c['due_date']<=horizon.isoformat() and c['ordered']>c['delivered']]
        required=sum(c['ordered']-c['delivered'] for c in rows)
        p['upcoming_orders']=len(rows);p['upcoming_quantity']=required
        p['order_shortage']=max(0,required-p['erp_stock']) if required and p['erp_stock'] is not None else None
        reasons=[]
        if p['rop'] is not None and p['position'] is not None and p['position']<=p['rop']:
            reasons.append('Llegó al punto de pedido: contar físicamente antes de preparar la reposición')
        elif p.get('count_alert'):
            reasons.append(f"Se acerca al ROP: contar ahora ({p['position']:g} disponibles; conteo desde {p['count_trigger']:g})")
        if required:reasons.append(f"{len(rows)} pedido(s) próximos requieren {required:g} unidades")
        if p['order_shortage']:reasons.append('El saldo registrado no cubre esos compromisos: confirmar físicamente')
        if p['discrepancy']:reasons.append('Último conteo con diferencia')
        if p.get('count_alert') and p['abc'] in ('A','B'):
            reasons.append(f"Clase {p['abc']}: prioridad alta por movimiento y cercanía al ROP")
        elif p.get('count_alert'):
            reasons.append(f"Clase {p['abc']}: conteo preventivo por cercanía al ROP")
        elif p['abc']=='A':reasons.append('Clase A: concentra movimiento y conviene verificarla con mayor frecuencia')
        p['task_reasons']=reasons
        p['wms_alert']=bool(p['rop'] is not None and p['position'] is not None and p['position']<=p['rop'])
        p['priority']+=(200 if p['risk']=='quiebre' else 150 if p['wms_alert'] else 0)
        p['priority']+=100 if p['order_shortage'] else 60 if rows else 0
        recent=bool(p['count_matches_snapshot'] and p['last_count'] and p['last_count']['created_at'][:10]==today.isoformat())
        p['recommended_count']=bool(p['due'] or ((p['wms_alert'] or p.get('count_alert') or rows) and not recent))
    products.sort(key=lambda p:(-p['priority'],-(p['outbound'] or 0),p['code']))
    return dict(inbound=inbound,credits=credits,physical_events=physical,commitments=commitments,
                movements=[dict(r) for r in db.execute('SELECT * FROM erp_movements ORDER BY day DESC LIMIT 3000')],
                pending_reconciliation=sum(not e['erp_movement_id'] for e in physical),
                upcoming_window_days=7)

def import_records(db,b,helpers,commit):
    required,number,now,log=helpers
    kind=b.get('kind')
    if kind not in FIELDS:raise ValueError('Tipo documental no soportado')
    content=required(b.get('csv'),'CSV',5_000_000).lstrip('\ufeff')
    reader=csv.DictReader(io.StringIO(content),delimiter=';' if ';' in content.splitlines()[0] else ',')
    if not set(FIELDS[kind]).issubset(reader.fieldnames or []):raise ValueError('Columnas requeridas: '+','.join(FIELDS[kind]))
    known={r[0] for r in db.execute('SELECT code FROM products')};rows=[];seen=set()
    for line,r in enumerate(reader,2):
        row={k:required(r.get(k),f'Fila {line}: {k}',300) for k in FIELDS[kind] if k not in ('reference','reason','source_doc')}
        for k in ('reference','reason','source_doc'):
            if k in FIELDS[kind]:row[k]=str(r.get(k,'')).strip()[:300]
        if row['code'] not in known:raise ValueError(f'Fila {line}: código desconocido, cargue primero el maestro')
        if row['id'] in seen:raise ValueError('Identificador documental repetido en el archivo')
        seen.add(row['id'])
        for k in ('quantity','expected','ordered','delivered','entry','exit'):
            if k in row:row[k]=number(row[k],k)
        for k in ('day','due_date'):
            if k in row:row[k]=date.fromisoformat(row[k]).isoformat()
        if 'day' in row and row['day']>date.today().isoformat():raise ValueError('Un movimiento o documento emitido no puede tener fecha futura')
        if kind=='credits' and row['inventory_effect'] not in ('no_stock','return','unknown'):raise ValueError('inventory_effect: no_stock, return o unknown')
        if 'status' in row and row['status'] not in ('active','closed','cancelled'):raise ValueError('status: active, closed o cancelled')
        if kind=='commitments' and row['delivered']>row['ordered']:raise ValueError('Lo entregado no puede superar lo solicitado')
        if kind in ('inbound','credits'):
            table='inbound' if kind=='inbound' else 'credits';eventkind='receipt' if kind=='inbound' else 'return'
            old=db.execute(f'SELECT code FROM {table} WHERE id=?',(row['id'],)).fetchone()
            received=db.execute('SELECT COALESCE(SUM(quantity),0) FROM physical_events WHERE kind=? AND parent_id=?',(eventkind,row['id'])).fetchone()[0]
            if old and old[0]!=row['code']:raise ValueError('No se puede reasignar un documento existente a otro SKU')
            if row.get('expected',row.get('quantity',0))<received:raise ValueError('El documento corregido queda por debajo de lo ya recibido físicamente')
            if kind=='inbound' and received and abs(received-row['expected'])<.00001 and row['status']=='active':row['status']='closed'
            if kind=='credits' and received and row['inventory_effect']!='return':raise ValueError('La nota tiene devolución física: revise la corrección antes de cambiar su efecto')
        if kind=='movements':
            old=db.execute('SELECT * FROM erp_movements WHERE id=?',(row['id'],)).fetchone()
            if old and any(old[k]!=row[k] for k in FIELDS[kind]):raise ValueError('Un movimiento ERP ya cargado cambió: requiere conciliación de corrección, no sobrescritura')
        rows.append(row)
        if len(rows)>30000:raise ValueError('Máximo 30.000 filas')
    if not rows:raise ValueError('Archivo sin registros')
    digest=hashlib.sha256((kind+json.dumps(rows,sort_keys=True)).encode()).hexdigest()
    exists=bool(db.execute('SELECT 1 FROM workflow_imports WHERE hash=?',(digest,)).fetchone())
    if not commit:return dict(hash=digest,rows=len(rows),sample=rows[:4],already_imported=exists)
    if digest!=b.get('hash'):raise ValueError('Valide otra vez: el archivo cambió')
    if exists:return dict(ok=True,rows=0,already_imported=True)
    table={'inbound':'inbound','credits':'credits','commitments':'commitments','movements':'erp_movements'}[kind]
    for row in rows:
        fields=FIELDS[kind]+(['source'] if kind=='movements' else [])
        if kind=='movements':row['source']='Softland / archivo normalizado'
        updates=','.join(f'{k}=excluded.{k}' for k in fields if k!='id')
        db.execute(f'INSERT INTO {table}({",".join(fields)}) VALUES({",".join("?" for _ in fields)}) ON CONFLICT(id) DO UPDATE SET {updates}',[row[k] for k in fields])
    db.execute('INSERT INTO workflow_imports VALUES(?,?,?,?)',(digest,kind,len(rows),now()))
    log(db,'Sincronización documental',f'{kind}: {len(rows)} líneas; {digest}')
    return dict(ok=True,rows=len(rows))

def mutate(db,path,b,helpers):
    required,number,now,log=helpers
    if path=='/api/credit-classify':
        row=db.execute('SELECT * FROM credits WHERE id=?',(b.get('id'),)).fetchone();effect=b.get('inventory_effect')
        if not row or effect not in ('no_stock','return','unknown'):raise ValueError('Nota o clasificación no válida')
        if effect!='return' and db.execute("SELECT 1 FROM physical_events WHERE kind='return' AND parent_id=?",(row['id'],)).fetchone():raise ValueError('Ya existe devolución física registrada; requiere revisión documental antes de cambiar su efecto')
        op=required(b.get('operator'),'Responsable',80);reason=required(b.get('explanation'),'Motivo de clasificación',500)
        db.execute('UPDATE credits SET inventory_effect=? WHERE id=?',(effect,row['id']))
        log(db,'Clasificación logística de NC',f'{row["id"]}: {effect}; {op}: {reason}. No modifica el DTE en Softland.')
        return dict(ok=True)
    if path=='/api/event-document':
        document=required(b.get('document'),'Guía/documento',150);op=required(b.get('operator'),'Responsable',80)
        if not db.execute('SELECT 1 FROM physical_events WHERE id=?',(b.get('id'),)).fetchone():raise ValueError('Evento no encontrado')
        db.execute('UPDATE physical_events SET document=? WHERE id=?',(document,b['id']))
        log(db,'Documento de recepción incorporado',f'{b["id"]}: {document}; responsable {op}')
        return dict(ok=True)
    if path in ('/api/documents/preview','/api/documents/import'):return import_records(db,b,helpers,path.endswith('/import'))
    if path=='/api/inbound':
        code=required(b.get('code'),'Producto',100)
        if not db.execute('SELECT 1 FROM products WHERE code=?',(code,)).fetchone():raise ValueError('Producto desconocido')
        ident='REC-'+uuid.uuid4().hex[:10].upper();expected=number(b.get('expected'),'Cantidad esperada',.001)
        doc=required(b.get('source_doc'),'Solicitud o documento',100)
        db.execute('INSERT INTO inbound VALUES(?,?,?,?,?,?)',(ident,code,expected,doc,date.today().isoformat(),'active'))
        log(db,'Recepción preparada',f'{ident} · {code} · {expected:g} esperadas · documento {doc}')
        return dict(id=ident)
    if path=='/api/commitments':
        code=required(b.get('code'),'Producto',100)
        if not db.execute('SELECT 1 FROM products WHERE code=?',(code,)).fetchone():raise ValueError('Producto desconocido')
        ordered=number(b.get('ordered'),'Cantidad',.001);delivered=number(b.get('delivered',0),'Entregado')
        if delivered>ordered:raise ValueError('La entrega supera el pedido')
        due=date.fromisoformat(b.get('due_date')).isoformat();ref=required(b.get('reference'),'Nota de venta o pedido',100)
        ident=required(b.get('id') or 'PED-'+uuid.uuid4().hex[:10].upper(),'ID',100)
        old=db.execute('SELECT code FROM commitments WHERE id=?',(ident,)).fetchone()
        if old and old[0]!=code:raise ValueError('No se puede reasignar un pedido existente a otro producto')
        db.execute('INSERT INTO commitments VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET ordered=excluded.ordered,delivered=excluded.delivered,due_date=excluded.due_date,reference=excluded.reference,status=excluded.status',
                   (ident,code,ordered,delivered,due,ref,'active' if delivered<ordered else 'closed'))
        log(db,'Compromiso de pedido',f'{ident} · {code} · {ordered-delivered:g} pendientes para {due}')
        return dict(id=ident)
    if path=='/api/physical-events':
        request=required(b.get('request_id'),'ID de operación',100)
        previous=db.execute('SELECT id FROM physical_events WHERE request_id=?',(request,)).fetchone()
        if previous:return dict(id=previous[0],already_saved=True)
        kind=b.get('kind');table={'receipt':'inbound','return':'credits'}.get(kind)
        if not table:raise ValueError('Tipo físico no válido')
        parent=db.execute(f'SELECT * FROM {table} WHERE id=?',(b.get('parent_id'),)).fetchone()
        if not parent:raise ValueError('Documento de origen no encontrado')
        if kind=='receipt' and parent['status']!='active':raise ValueError('Recepción cerrada o cancelada')
        if kind=='return' and parent['inventory_effect']!='return':raise ValueError('La nota no está identificada como devolución física; no se recibe mercadería automáticamente')
        qty=number(b.get('quantity'),'Cantidad recibida',.001);good=number(b.get('good'),'Cantidad apta')
        if good>qty:raise ValueError('La cantidad apta supera el total recibido')
        total=db.execute('SELECT COALESCE(SUM(quantity),0) FROM physical_events WHERE kind=? AND parent_id=?',(kind,parent['id'])).fetchone()[0]
        expected=parent['expected'] if kind=='receipt' else parent['quantity']
        if total+qty>expected+.00001:raise ValueError('La recepción supera el pendiente; documente y corrija el origen antes de aceptar el excedente')
        op=required(b.get('operator'),'Responsable',80);document=str(b.get('document','')).strip()[:150];note=str(b.get('note',''))[:1000]
        ident=str(uuid.uuid4())
        db.execute('INSERT INTO physical_events VALUES(?,?,?,?,?,?,?,?,?,?,?,NULL)',(ident,request,kind,parent['id'],parent['code'],qty,good,document,op,note,now()))
        if kind=='receipt' and abs(total+qty-expected)<.00001:db.execute("UPDATE inbound SET status='closed' WHERE id=?",(parent['id'],))
        log(db,'Recepción física' if kind=='receipt' else 'Devolución física',f'{parent["code"]}: {qty:g} recibidas, {good:g} aptas. '+('Documento '+document if document else 'Sin guía: incidencia pendiente')+'. Saldo ERP sin modificar.')
        return dict(id=ident)
    if path=='/api/reconcile':
        event=db.execute('SELECT * FROM physical_events WHERE id=?',(b.get('event_id'),)).fetchone()
        movement=db.execute('SELECT * FROM erp_movements WHERE id=?',(b.get('movement_id'),)).fetchone()
        if not event or not movement:raise ValueError('Seleccione una observación y un movimiento ERP importado')
        if event['erp_movement_id']:raise ValueError('La observación ya está conciliada')
        if movement['code']!=event['code'] or abs(movement['entry']-event['good'])>.00001 or movement['exit']!=0:raise ValueError('No coincide producto, entrada apta o dirección del movimiento')
        if movement['day']<event['created_at'][:10]:raise ValueError('El movimiento antecede a la recepción física registrada')
        if db.execute('SELECT 1 FROM physical_events WHERE erp_movement_id=?',(movement['id'],)).fetchone():raise ValueError('Ese movimiento ERP ya fue conciliado')
        op=required(b.get('operator'),'Responsable',80)
        db.execute('UPDATE physical_events SET erp_movement_id=? WHERE id=?',(movement['id'],event['id']))
        log(db,'Conciliación con Softland',f'{event["id"]} ↔ {movement["id"]}; {op}. Sin sumar nuevamente al stock.')
        return dict(ok=True)
    raise ValueError('Operación documental no soportada')
