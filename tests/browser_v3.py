"""QA de tutoriales, recepción, NC, predicción y vista de bodega; datos solo temporales."""
import json
import os
import sys
import tempfile
import threading
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import server
from playwright.sync_api import sync_playwright

def main():
    root=Path(__file__).resolve().parents[1];(root/'artifacts').mkdir(exist_ok=True);previous=server.DB
    with tempfile.TemporaryDirectory() as tmp:
        server.DB=Path(tmp)/'v3.db';server.initialize()
        http=server.InventoryHTTPServer(('127.0.0.1',0),server.Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();url=f'http://127.0.0.1:{http.server_port}'
        try:
            with sync_playwright() as pw:
                installed=sorted((Path(os.environ.get('LOCALAPPDATA',''))/'ms-playwright').glob('chromium-*/chrome-win64/chrome.exe'))
                browser=pw.chromium.launch(headless=True,**({'executable_path':str(installed[-1])} if installed else {}))
                page=browser.new_page(viewport={'width':1440,'height':1000});page.add_init_script("localStorage.setItem('ingefix-tour-v3','done')")
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(url);page.locator('.abc-cards').wait_for()
                page.locator('[data-action=start-tour]').click();page.locator('.tutorial-content').wait_for()
                page.screenshot(path=str(root/'artifacts'/'tutorial-v3.png'),full_page=True)
                for _ in range(7):page.locator('[data-action=tour-next]').click()
                page.locator('[data-action=tour-finish]').click();page.locator('#modal').wait_for(state='hidden')
                page.locator('#nav [data-page=receipts]').click();page.locator('[data-action=new-inbound]').click()
                page.locator('#inbound-form [name=code]').select_option('2ABFESS11510M00')
                page.locator('#inbound-form [name=source_doc]').fill('SOL-QA');page.locator('#inbound-form [name=expected]').fill('10')
                page.locator('#inbound-form [type=submit]').click();page.locator('#modal').wait_for(state='hidden')
                page.locator('[data-action=receive]').click()
                page.locator('#physical-form [name=quantity]').fill('3');page.locator('#physical-form [name=good]').fill('2');page.locator('#physical-form [name=operator]').fill('QA temporal')
                page.locator('#physical-form [type=submit]').click();page.locator('#modal').wait_for(state='hidden')
                page.locator('.receiving-card').filter(has_text='Recepción parcial').wait_for()
                page.screenshot(path=str(root/'artifacts'/'recepciones-v3-qa.png'),full_page=True)
                page.locator('#nav [data-page=credits]').click()
                page.locator('details.document-import').first.locator('summary').click()
                csv=f'id,code,quantity,day,reference,reason,inventory_effect\nNC-QA,2ABFESS11510M00,5,{date.today()},FACT-QA,Devolucion,return'
                page.locator('#document-file').first.set_input_files({'name':'nc.csv','mimeType':'text/csv','buffer':csv.encode()})
                page.locator('[data-action=document-preview]').first.click();page.locator('#document-commit:not([disabled])').first.wait_for()
                page.locator('#document-commit').first.click();page.locator('tbody').filter(has_text='NC-QA').first.wait_for()
                page.locator('[data-kind=return]').click();page.locator('#physical-form [name=quantity]').fill('5');page.locator('#physical-form [name=good]').fill('4');page.locator('#physical-form [name=operator]').fill('QA temporal')
                page.locator('#physical-form [type=submit]').click();page.locator('#modal').wait_for(state='hidden')
                page.screenshot(path=str(root/'artifacts'/'notas-credito-v3-qa.png'),full_page=True)
                page.locator('#nav [data-page=forecast]').click();page.locator('#forecast-product').select_option('2ABFESS11510M00')
                page.locator('.model-result').first.wait_for();assert page.locator('.model-result').count()==3
                page.screenshot(path=str(root/'artifacts'/'demanda-real-v3.png'),full_page=True)
                page.locator('#nav [data-page=commitments]').click();page.locator('[data-action=new-commitment]').click()
                page.locator('#commitment-form [name=code]').select_option('2ABFESS11510M00');page.locator('#commitment-form [name=reference]').fill('NV-QA')
                page.locator('#commitment-form [name=ordered]').fill('10000');page.locator('#commitment-form [name=due_date]').fill(date.today().isoformat())
                page.locator('#commitment-form [type=submit]').click();page.locator('#modal').wait_for(state='hidden')
                mobile=browser.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True);mobile.add_init_script("localStorage.setItem('ingefix-tour-v3','done')")
                mobile.goto(url+'/bodega');mobile.locator('.warehouse-header').wait_for()
                assert mobile.locator('.sidebar').is_hidden();assert mobile.locator('.shell>header').is_hidden()
                assert mobile.locator('.warehouse-notices').inner_text().find('DISCO CORTE')!=-1
                mobile.screenshot(path=str(root/'artifacts'/'bodega-v3-qa.png'),full_page=True)
                assert mobile.evaluate('document.documentElement.scrollWidth<=innerWidth')
                # Roles autenticados de bodega: permiso de conteo, bloqueo de configuración/documentos.
                server.ACCESS_CODE='ADMIN-QA';server.WAREHOUSE_CODE='BODEGA-QA'
                guest=browser.new_context(viewport={'width':390,'height':844});wh=guest.new_page();wh.add_init_script("localStorage.setItem('ingefix-tour-v3','done')")
                wh.goto(url+'/bodega');wh.locator('#access-code').fill('BODEGA-QA');wh.locator('#login-form button').click();wh.locator('.warehouse-header').wait_for()
                assert wh.request.post(url+'/api/settings',data={}).status==403
                assert wh.request.get(url+'/api/source?name=VENTAS%20PROMEDIO.pdf').status==403
                assert wh.request.get(url+'/api/state').json()['session_role']=='warehouse'
                assert not errors,errors
                browser.close();print(json.dumps(dict(passed=True,tutorial_steps=8,partial_receipt=True,credit_import_return=True,models=3,warehouse_permissions=True,js_errors=errors)))
        finally:http.shutdown();http.server_close();thread.join();server.DB=previous;server.ACCESS_CODE=None;server.WAREHOUSE_CODE=None;server.SESSIONS.clear()
if __name__=='__main__':main()
