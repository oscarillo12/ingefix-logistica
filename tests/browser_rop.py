"""Verificación del análisis ROP. Parámetros de prueba solo en SQLite temporal."""
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import server
from domain import DEFAULT_SETTINGS
from playwright.sync_api import sync_playwright

def main():
    root=Path(__file__).resolve().parents[1];(root/'artifacts').mkdir(exist_ok=True)
    original=server.DB
    with tempfile.TemporaryDirectory() as tmp:
        server.DB=Path(tmp)/'rop-test.db';server.initialize()
        with server.connect() as db:
            db.execute('INSERT INTO products(code,name,warehouse,unit,location,snapshot_at,snapshot_version) VALUES(?,?,?,?,?,?,?)',('QA-NODATA','Producto de prueba sin historia','08','UN','','','qa'))
        http=server.InventoryHTTPServer(('127.0.0.1',0),server.Handler)
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{http.server_port}'
        try:
            with sync_playwright() as pw:
                installed=sorted((Path(os.environ.get('LOCALAPPDATA',''))/'ms-playwright').glob('chromium-*/chrome-win64/chrome.exe'))
                browser=pw.chromium.launch(headless=True,**({'executable_path':str(installed[-1])} if installed else {}))
                page=browser.new_page(viewport={'width':1536,'height':1080});errors=[]
                page.add_init_script("localStorage.setItem('ingefix-tour-v3','done')")
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(url+'/#replenish');page.locator('.rop-formula').wait_for()
                assert page.locator('.symbolic-cycle').count()==1
                assert page.locator('.rop-cycle-chart').count()==0
                assert page.locator('.rop-formula-total').inner_text().find('ROP pendiente')!=-1
                page.screenshot(path=str(root/'artifacts'/'rop-pendiente.png'),full_page=True)
                with server.connect() as db:
                    # Datos explícitos de test; no se guardan en data/ingefix.db.
                    config=dict(DEFAULT_SETTINGS,period_days=90,period_confirmed=True,
                                lead_days=7,buffer_days=3,review_days=7,planning_confirmed=True)
                    server.mutate(db,'/api/settings',config)
                page.reload();page.locator('.rop-cycle-chart').wait_for()
                page.locator('#rop-product').select_option('2ABFESS11510M00')
                data=page.request.get(url+'/api/state').json()
                p=next(p for p in data['products'] if p['code']=='2ABFESS11510M00')
                formatted=f"{p['rop']:,}".replace(',','.')
                expected=page.evaluate('''()=>({
                  total:document.querySelector('.rop-formula-total strong').textContent,
                  bar:document.querySelector('.rop-stacked').getAttribute('aria-label'),
                  curve:document.querySelector('.rop-cycle-chart').getAttribute('aria-label'),
                  width:document.querySelector('.rop-demand-part').style.width,
                  notes:document.querySelector('.rop-model-note').textContent
                })''')
                assert formatted in expected['total']
                assert formatted in expected['bar']
                assert formatted in expected['curve']
                assert '7 días' in expected['curve']
                assert expected['width'].endswith('%')
                assert 'No representa movimientos históricos' in expected['notes']
                page.screenshot(path=str(root/'artifacts'/'rop-calculo-qa.png'),full_page=True)
                page.locator('#rop-product').select_option('TOVOPF612500000')
                assert page.locator('.rop-formula-total strong').inner_text()!=expected['total']
                # Un SKU sin salidas no recibe un ROP de otro producto.
                page.locator('#rop-product').select_option('QA-NODATA')
                assert page.locator('.rop-cycle-chart').count()==0
                page.set_viewport_size({'width':390,'height':844})
                page.locator('#rop-product').select_option('2ABFESS11510M00')
                page.screenshot(path=str(root/'artifacts'/'rop-mobile-qa.png'),full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                assert not errors,errors
                browser.close()
                print(json.dumps({'passed':True,'formula_matches_api':True,'product_switch':True,'missing_data_no_fake_curve':True,'mobile_no_page_overflow':True,'js_errors':errors}))
        finally:http.shutdown();http.server_close();thread.join();server.DB=original

if __name__=='__main__':main()
