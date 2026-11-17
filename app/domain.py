import math
import statistics
from datetime import date, timedelta


DEFAULT_SETTINGS = dict(period_days=None, period_confirmed=False, lead_days=None, buffer_days=None,
                        review_days=None, growth_pct=0, count_a=7, count_b=30, count_c=90,
                        abc_a=80, abc_b=95, planning_confirmed=False, planning_version=2)


def classify(products, a=80, b=95):
    """ABC por volumen de salidas, no por valor: no se recibieron costos."""
    ordered = sorted(products, key=lambda p: max(0, p.get('outbound') or 0), reverse=True)
    total = sum(max(0, p.get('outbound') or 0) for p in ordered)
    accum = 0
    for rank,p in enumerate(ordered,1):
        share = max(0, p.get('outbound') or 0) / total if total else 0
        p['abc'] = 'ND' if p.get('outbound') is None else (('A' if accum < a/100 else 'B' if accum < b/100 else 'C') if share else 'C')
        p['share'] = share
        accum += share
        p['cumulative_share'] = accum
        p['volume_rank'] = rank if p.get('outbound') is not None else None
    return products


def prediction(values):
    """Comparación temporal, sin utilizar observaciones futuras para entrenar."""
    def mean(a): return statistics.mean(a[-28:])
    def ses(a):
        s = a[0]
        for x in a[1:]: s = .2*x + .8*s
        return s
    def croston(a):
        nz = [(i, v) for i, v in enumerate(a) if v > 0]
        if not nz: return 0
        prev, q = nz[0]; interval = prev + 1
        for i, v in nz[1:]:
            q += .1*(v-q); interval += .1*(i-prev-interval); prev = i
        return .95*q/max(1, interval)
    methods = {'Media móvil 28 días': mean, 'Suavizado exponencial': ses, 'Croston SBA': croston}
    if len(values) < 35:
        return dict(method='Media disponible · provisional', daily=statistics.mean(values) if values else None,
                    mae=None, days=len(values), validated=False)
    validation_days=min(28,len(values)-21)
    errors = {name: statistics.mean(abs(fn(values[:i])-values[i]) for i in range(len(values)-validation_days, len(values)))
              for name, fn in methods.items()}
    name = min(errors, key=errors.get)
    return dict(method=name, daily=max(0, methods[name](values)), mae=errors[name], days=len(values),
                validated=True, scores=errors, validation=f'{validation_days} orígenes móviles, horizonte 1 día',validation_days=validation_days,short_history=len(values)<56)


def enrich(products, settings, counts, daily_rows, orders):
    classify(products,settings.get('abc_a',80),settings.get('abc_b',95))
    series = {}
    for r in daily_rows:
        series.setdefault(r['code'], []).append(r)
    pending = {}
    for o in orders:
        if o['status'] in ('borrador', 'aprobada'):
            pending[o['code']] = pending.get(o['code'], 0) + o['quantity']
    latest = {}
    for c in counts:
        latest.setdefault(c['code'], c)
    for p in products:
        c = latest.get(p['code'])
        p['last_count'] = c
        p['discrepancy'] = c['quantity'] - c['expected'] if c and c['expected'] is not None else None
        p['count_matches_snapshot'] = bool(c and c['snapshot_version'] == p['snapshot_version'] and c['location'] == p['location'])
        rows = sorted(series.get(p['code'], []), key=lambda r: r['day'])
        # Solo una serie diaria explícita y continua permite considerar los ceros conocidos.
        contiguous = bool(rows) and all((date.fromisoformat(b['day'])-date.fromisoformat(a['day'])).days == 1 for a,b in zip(rows, rows[1:]))
        if rows and contiguous:
            f = prediction([r['quantity'] for r in rows])
            f['last_day'] = rows[-1]['day']
            f['stale'] = (date.today()-date.fromisoformat(rows[-1]['day'])).days > 7
            d = f['daily']
            scenario = not f['validated'] or f['stale']
        else:
            d = max(0, p['outbound'])/settings['period_days'] if p['outbound'] is not None and settings['period_days'] and settings['period_confirmed'] else None
            f = dict(method='Promedio de salidas Excel', daily=d, days=settings['period_days'],
                     mae=None, validated=False, missing_dates=bool(rows))
            scenario = not settings['period_confirmed']
        p['forecast'] = f
        p['scenario'] = scenario
        p['daily'] = d*(1+settings['growth_pct']/100) if d is not None else None
        planning_ready = bool(settings.get('planning_confirmed')) and all(settings.get(k) is not None for k in ('lead_days','buffer_days','review_days'))
        p['planning_ready'] = planning_ready and d is not None
        p['safety'] = math.ceil(p['daily']*settings['buffer_days']) if p['planning_ready'] else None
        p['rop'] = math.ceil(p['daily']*settings['lead_days']+p['safety']) if p['planning_ready'] else None
        stock = p['erp_stock']
        p['coverage'] = max(0,stock)/p['daily'] if stock is not None and p['daily'] else None
        p['position'] = stock+p['in_transit']-p['reserved'] if stock is not None else None
        p['suggested'] = max(0, math.ceil(p['daily']*(settings['lead_days']+settings['review_days'])+p['safety']-p['position'])) if p['position'] is not None and p['planning_ready'] else None
        p['open_request'] = pending.get(p['code'], 0)
        p['risk'] = 'sin_saldo' if stock is None else 'quiebre' if p['position'] <= 0 else 'sin_politica' if p['rop'] is None else 'reponer' if p['position'] <= p['rop'] else 'estable'
        interval = settings['count_'+(p['abc'].lower() if p['abc']!='ND' else 'c')]
        p['due'] = not c or not p['count_matches_snapshot'] or (date.today()-date.fromisoformat(c['created_at'][:10])).days >= interval
        p['count_interval'] = interval
        p['priority'] = (100 if p['discrepancy'] else 0)+(50 if p['risk']=='quiebre' else 25 if p['risk']=='reponer' else 0)+({'A':20,'B':10,'C':0,'ND':0}[p['abc']])
    return sorted(products, key=lambda p:(-p['priority'], -(p['outbound'] or 0), p['code']))
