"""Informe reproducible de las fuentes, sin modificar SQLite."""
import csv
import json
from pathlib import Path
from domain import classify

ROOT=Path(__file__).resolve().parents[1]


def main():
    seed=json.loads((ROOT/'data'/'seed.json').read_text(encoding='utf-8'))
    ps=classify(seed['products'])
    ordered=sorted([p for p in ps if p['outbound'] is not None],key=lambda p:p['outbound'],reverse=True)
    with (ROOT/'data'/'clasificacion_productos.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f,delimiter=';')
        w.writerow(['codigo','descripcion','abc_unidades','salidas_periodo_no_confirmado','rotacion','existencia_promedio','saldo_erp_2026_11_16','participacion_salidas'])
        for p in sorted(ps,key=lambda p:p['outbound'] or 0,reverse=True):
            w.writerow([p['code'],p['name'],p['abc'],p['outbound'],p['rotation'],p['avg_stock'],p['erp_stock'],round(p['share'],8)])
    lines=['# Análisis de los archivos de INGEFIX','',
           'Resultado reproducible con `python app/analyze.py`. No equivale a una auditoría física.','',
           '## Cobertura','',
           '- 654 códigos de producto en `ROT 16-11.xlsx`; se excluyen encabezados, grupos y totales.',
           '- 403 productos con resumen de saldo en el registro PDF de bodega 08 de Temuco. Se reconocieron los 403 bloques de producto.',
           '- 397 códigos coinciden entre las dos fuentes; hay 257 solo en rotación y 6 solo en existencias. Maestro combinado: 660 SKU.',
           '- Ambos PDF de existencias tienen SHA256 idéntico; solo se procesó uno.',
           '- Saldo del ERP emitido 16/11/2026, rango solicitado 01/10/2026–30/11/2026. La fecha final futura del filtro no demuestra movimientos futuros.',
           '- El PDF usa la palabra “físico” para su saldo registrado. No se recibieron conteos independientes en terreno ni ubicaciones.',
           '- Los 403 resúmenes del PDF indican reserva cero. No hay evidencia de tránsito de entrada confirmado; se inicializa en cero.',
           '- El Excel no especifica período ni sucursal en su hoja. No usar sus salidas como tasa diaria definitiva antes de confirmarlos.',
           '- `VENTAS PROMEDIO.pdf` es un libro resumido de julio–octubre 2026: no contiene ventas por SKU/día. No sirve para entrenar demanda individual.',
           '- Las imágenes son referencias visuales de pedidos pendientes y abastecimiento con recepciones parciales; no se transcribieron como transacciones verificadas.','',
           '## ABC por volumen de salida','',
           'Se ordena por salidas positivas. A cubre al menos el primer 80% del volumen y B el siguiente tramo hasta 95%, incluyendo el producto que cruza cada umbral. No es ABC por valor: faltan costos unitarios. Las cantidades no se convierten entre unidades o embalajes; validar su comparabilidad.','']
    for c in ('A','B','C','ND'):
        group=[p for p in ps if p['abc']==c]
        lines.append(f'- Clase {c}: {len(group)} SKU, {sum(p["share"] for p in group):.2%} de las unidades de salida.')
    lines+=['','## Mayor volumen de salidas (primera selección para revisar)','',
            '| Código | Producto | Salidas del período | Rotación reportada | Saldo ERP | ABC |',
            '|---|---|---:|---:|---:|---|']
    for p in ordered[:15]:
        lines.append(f'| {p["code"]} | {p["name"]} | {p["outbound"]:,.0f} | {p["rotation"]:.4f} | {p["erp_stock"] if p["erp_stock"] is not None else "Sin dato"} | {p["abc"]} |')
    lines+=['','## Mayor ratio de rotación','',
            'Un ratio alto puede venir de existencias promedio muy pequeñas. Revisar junto con volumen y quiebres; no equivale automáticamente a mayor importancia.','',
            '| Código | Producto | Rotación | Salidas |','|---|---|---:|---:|']
    for p in sorted(ordered,key=lambda p:p['rotation'],reverse=True)[:10]:
        lines.append(f'| {p["code"]} | {p["name"]} | {p["rotation"]:.4f} | {p["outbound"]:,.0f} |')
    lines+=['','## Límites para decidir reposición','',
            'No se puede afirmar una discrepancia física ni un quiebre real solo con estos documentos. El software no precarga días de demanda, plazo ni colchón de demostración. El ROP queda vacío hasta contar con datos confirmados. Confirmar demanda, saldos actuales, reservas, disponibilidad de Santiago, embalajes y plazo real antes de emitir solicitudes operativas.','',
            'La clasificación completa está en `data/clasificacion_productos.csv`. Los archivos originales y sus hashes se conservan en `data/seed.json`.','']
    (ROOT/'docs'/'ANALISIS_DATOS.md').write_text('\n'.join(lines),encoding='utf-8')
    print('Análisis y clasificación de 660 productos generados.')


if __name__=='__main__':main()
