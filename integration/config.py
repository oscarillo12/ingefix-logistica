"""Configuración local sin contraseñas: autenticación Windows o conexión de entorno."""
import json
import os
import re
from pathlib import Path

PATH=Path(__file__).resolve().parents[1]/'data'/'integration.local.json'
DEFAULT_VIEWS={'master':'dbo.vw_INGEFIX_Products','stock':'dbo.vw_INGEFIX_Stock','demand':'dbo.vw_INGEFIX_DailyDemand','credits':'dbo.vw_INGEFIX_CreditNotes','inbound':'dbo.vw_INGEFIX_Inbound','commitments':'dbo.vw_INGEFIX_Commitments','movements':'dbo.vw_INGEFIX_Movements'}
def load():
    saved=json.loads(PATH.read_text(encoding='utf-8')) if PATH.exists() else {}
    return dict(server=saved.get('server',''),database=saved.get('database',''),driver=saved.get('driver','ODBC Driver 18 for SQL Server'),
                enabled=saved.get('enabled',False),interval=saved.get('interval',300),modules=saved.get('modules',['master','stock']),views=dict(DEFAULT_VIEWS,**saved.get('views',{})))
def connection():
    if os.environ.get('INGEFIX_ODBC_CONNECTION'):return os.environ['INGEFIX_ODBC_CONNECTION']
    c=load()
    if not c['server'] or not c['database']:return None
    return f"DRIVER={{{c['driver']}}};SERVER={c['server']};DATABASE={{{c['database']}}};Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=no"
def save(b):
    for k in ('server','database'):
        if not isinstance(b.get(k),str) or not re.fullmatch(r'[A-Za-z0-9_ .\\,:\-]{1,150}',b[k]):raise ValueError(f'{k}: nombre de servidor/base requerido; sin punto y coma ni credenciales')
    if b.get('driver') not in ('ODBC Driver 18 for SQL Server','ODBC Driver 17 for SQL Server'):raise ValueError('Driver ODBC no válido')
    interval=int(b.get('interval',300))
    if not 60<=interval<=86400:raise ValueError('Intervalo permitido: 60 a 86400 segundos')
    modules=b.get('modules',[])
    if not isinstance(modules,list) or any(x not in DEFAULT_VIEWS for x in modules):raise ValueError('Módulos no válidos')
    if not {'master','stock'}.issubset(modules):raise ValueError('Seleccione maestro y saldos como base de sincronización')
    views={}
    for k,default in DEFAULT_VIEWS.items():
        value=b.get('views',{}).get(k,default)
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*',value):raise ValueError('Las vistas deben tener formato esquema.nombre; no se admite SQL libre')
        views[k]=value
    c=dict(server=b['server'],database=b['database'],driver=b['driver'],enabled=b.get('enabled') is True,interval=interval,modules=modules,views=views)
    PATH.parent.mkdir(exist_ok=True);temp=PATH.with_suffix('.tmp');temp.write_text(json.dumps(c,indent=2),encoding='utf-8');temp.replace(PATH)
    return c
