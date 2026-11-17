"""Lectura de fuentes entregadas. XLSX sin dependencias; PDF solo para carga inicial."""
import hashlib
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def read_rotation(path):
    with zipfile.ZipFile(path) as z:
        strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            strings = [''.join(n.itertext()) for n in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', NS)]
        rows = ET.fromstring(z.read('xl/worksheets/sheet1.xml')).findall('.//m:sheetData/m:row', NS)
        products = []
        group = subgroup = ''
        for row in rows:
            values = {}
            for c in row.findall('m:c', NS):
                v = c.find('m:v', NS)
                value = v.text if v is not None else ''.join(c.itertext())
                if c.get('t') == 's':
                    value = strings[int(value)]
                values[re.sub(r'\d', '', c.get('r'))] = value
            code = values.get('A', '').strip()
            if code.startswith('Grupo:'):
                group = code.split(':', 1)[1].strip()
            elif code.startswith('SubGrupo:'):
                subgroup = code.split(':', 1)[1].strip()
            elif re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]+', code) and values.get('B'):
                try:
                    products.append(dict(code=code, name=values['B'].strip(), group_name=group,
                                         subgroup=subgroup, avg_stock=float(values.get('C') or 0),
                                         outbound=float(values.get('D') or 0), rotation=float(values.get('E') or 0)))
                except ValueError:
                    raise ValueError(f'Fila de rotación inválida: {code}')
        if len({p['code'] for p in products}) != len(products):
            raise ValueError('Códigos repetidos en Excel; revisar antes de cargar')
        return products


def extract_initial(root):
    from pypdf import PdfReader
    root = Path(root)
    stock_path = root / 'EXISTENCIAS PROMEDIO.pdf'
    text = '\n'.join(page.extract_text() for page in PdfReader(stock_path).pages)
    stocks = {}
    for m in re.finditer(r'([\-\d,.]+)\s*Total f[ií]sico producto\s*\[\s*([^\]]+)\s*\]', text, re.I):
        code = m[2].strip()
        if code in stocks:
            raise ValueError(f'Saldo duplicado: {code}')
        stocks[code] = float(m[1].replace(',', ''))
    # Las descripciones aparecen antes de cada bloque, aunque el resumen cruce página.
    names = {m[1].strip(): (m[2].strip(), m[3].strip()) for m in re.finditer(
        r'Item\s*:\s*\[\s*([^\]]+)\]\s*\[\s*([^\]]+)\]\s*U/medida\s*:\s*\[\s*([^\]]+)\]', text)}
    products = read_rotation(root / 'ROT 16-11.xlsx')
    by_code = {p['code']: p for p in products}
    for code, stock in stocks.items():
        if code not in by_code:
            name, unit = names.get(code, (code, 'UN'))
            by_code[code] = dict(code=code, name=name, group_name='Solo registro de existencias',
                                 subgroup='', avg_stock=None, outbound=None, rotation=None)
    for p in by_code.values():
        p.update(erp_stock=stocks.get(p['code']), warehouse='08',
                 unit=names.get(p['code'], ('', None))[1], snapshot_at='2026-11-16', location='')
    files = []
    for p in root.iterdir():
        if p.suffix.lower() in ('.pdf', '.xlsx', '.png'):
            files.append(dict(name=p.name, bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    result = dict(products=list(by_code.values()), sources=files,
                  metadata=dict(snapshot_at='2026-11-16', warehouse='08', warehouse_name='Temuco',
                                pdf_range='01/10/2026–30/11/2026 (emitido 16/11/2026)',
                                rotation_period='No informado en el Excel',
                                sales='Libro resumido julio–octubre 2026, sin detalle SKU',
                                stock_products=len(stocks), rotation_products=len(products),
                                matched=sum(p['code'] in stocks for p in products)))
    if not stocks or not products:
        raise ValueError('No se pudo reconocer la fuente; no se generará una carga vacía')
    return result


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    result = extract_initial(root)
    (root / 'data' / 'seed.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result['metadata'], ensure_ascii=False))
    print('Top por salidas:', [(p['code'], p['outbound']) for p in sorted(result['products'], key=lambda p: p['outbound'] or 0, reverse=True)[:10]])
