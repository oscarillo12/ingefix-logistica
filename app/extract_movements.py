"""Extrae movimientos físicos del PDF y valida cada producto por su saldo.

No usa el libro de ventas resumido como historial por SKU. Una serie diaria se
genera solo para un bloque completo cuya identidad contable coincide.
"""
import json
import re
from datetime import date,timedelta
from pathlib import Path
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
def extract():
    products={};current=None;events=[];issues=[]
    def value(s):return float(s.replace(',',''))
    for page_no,page in enumerate(PdfReader(ROOT/'EXISTENCIAS PROMEDIO.pdf').pages,1):
        for line in page.extract_text().splitlines():
            m=re.search(r'Item\s*:\s*\[\s*([^\]]+)\]',line)
            if m:
                current=m[1].strip();opening=re.search(r'([\-\d,.]+)Saldo Anterior',line)
                products[current]=dict(opening=value(opening[1]) if opening else None,closing=None,entries=0.,exits=0.,valid=True)
            if not current:continue
            summary=re.search(r'([\-\d,.]+)Total f[ií]sico producto\s*\[\s*([^\]]+)',line,re.I)
            if summary:
                code=summary[2].strip()
                if code in products:products[code]['closing']=value(summary[1])
            day=re.match(r'(\d{2})/(\d{2})/(\d{4})',line)
            if not day or not re.search(r'Guía\[|Factura\[|Boleta\[|Crédito\[',line):continue
            qty=re.search(r'(-?\d[\d,]*\.\d{2})\s+(-?\d[\d,]*\.\d{2})\s+(-?\d[\d,]*\.\d{2})',line)
            if not qty:
                products[current]['valid']=False;issues.append(dict(code=current,page=page_no,reason='Movimiento sin tres cantidades inequívocas'));continue
            entry,out,balance=map(value,qty.groups());p=products[current]
            previous=p['opening']+p['entries']-p['exits'] if p['opening'] is not None else None
            if previous is None or abs(previous+entry-out-balance)>.02:p['valid']=False
            p['entries']+=entry;p['exits']+=out
            customer=bool(re.search(r'01-Despacho por Facturar|01-Desde Bodega Base a Cliente|01-Venta con Boleta',line))
            events.append(dict(id=f'pdf-{page_no}-{len(events)+1}',code=current,day=date(int(day[3]),int(day[2]),int(day[1])).isoformat(),entry=entry,exit=out,balance=balance,customer_out=out if customer else 0.,page=page_no,source='EXISTENCIAS PROMEDIO.pdf',text=line))
    valid=[]
    for code,p in products.items():
        p['valid']=p['valid'] and p['opening'] is not None and p['closing'] is not None and abs(p['opening']+p['entries']-p['exits']-p['closing'])<.02
        if p['valid']:valid.append(code)
    start=date(2026,10,1);end=date(2026,11,16);totals={}
    for e in events:
        if e['code'] in valid and start.isoformat()<=e['day']<=end.isoformat():totals[e['code'],e['day']]=totals.get((e['code'],e['day']),0)+e['customer_out']
    daily=[dict(code=code,day=(start+timedelta(days=i)).isoformat(),quantity=totals.get((code,(start+timedelta(days=i)).isoformat()),0)) for code in valid for i in range((end-start).days+1)]
    result=dict(start=start.isoformat(),end=end.isoformat(),source='EXISTENCIAS PROMEDIO.pdf',basis='Salidas físicas a cliente; transferencias, ajustes y devoluciones excluidos de demanda bruta',products=products,events=events,daily=daily,issues=issues,
                summary=dict(products=len(products),validated_products=len(valid),excluded_products=len(products)-len(valid),movements=len(events),days=(end-start).days+1))
    (ROOT/'data'/'ledger.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps(result['summary']))
if __name__=='__main__':extract()
