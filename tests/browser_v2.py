"""Prueba funcional de ABC, gráficos, impresión, escaneo y ROP sin datos inventados."""
import base64
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import server
from playwright.sync_api import sync_playwright

def main():
    root=Path(__file__).resolve().parents[1];(root/'artifacts').mkdir(exist_ok=True)
    original=server.DB
    with tempfile.TemporaryDirectory() as tmp:
        server.DB=Path(tmp)/'qa.db';server.initialize()
        http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{http.server_port}'
        try:
            with sync_playwright() as pw:
                existing=sorted((Path(os.environ.get('LOCALAPPDATA',''))/'ms-playwright').glob('chromium-*/chrome-win64/chrome.exe'))
                browser=pw.chromium.launch(headless=True,**({'executable_path':str(existing[-1])} if existing else {}))
                page=browser.new_page(viewport={'width':1536,'height':1080})
                page.add_init_script("localStorage.setItem('ingefix-tour-v3','done')")
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(url);page.wait_for_selector('.abc-cards')
                page.screenshot(path=str(root/'artifacts'/'dashboard-v2.png'),full_page=True)
                state=page.request.get(url+'/api/state').json()
                assert all(p['rop'] is None for p in state['products'])
                for name in ['abc','inventory','counts','labels','scan','replenish','forecast','integration','documents','research','audit']:
                    page.locator(f'#nav [data-page="{name}"]').click();page.locator('h1').wait_for()
                    assert page.locator('#load-error').is_hidden()
                page.locator('#nav [data-page="abc"]').click()
                assert page.locator('.abc-card').count()==3
                page.locator('[data-action="select-class"][data-class="B"]').click()
                assert page.locator('.ranking-chart').count()==1
                assert page.locator('tbody tr').count()==37
                page.screenshot(path=str(root/'artifacts'/'abc-v2.png'),full_page=True)
                page.locator('[data-action="select-class"][data-class="A"]').click()
                page.locator('[data-action="print-class"]').click()
                assert page.locator('.label-product input:checked').count()==19
                page.screenshot(path=str(root/'artifacts'/'labels-v2.png'),full_page=True)
                photo=page.locator('.label-barcode').first.screenshot()
                (root/'artifacts'/'barcode-test.png').write_bytes(photo)
                photo_code=page.locator('.label-sku').first.inner_text()
                page.evaluate('window.print=()=>{}')
                page.locator('[data-action="print-labels"]').click()
                assert page.locator('#print-sheet .product-label').count()==19
                page.emulate_media(media='print')
                page.pdf(path=str(root/'artifacts'/'etiquetas-clase-A.pdf'),prefer_css_page_size=True,print_background=True)
                page.emulate_media(media='screen')
                # Decodificación real de imágenes, usando los 660 códigos reales y checksum.
                decoded=page.evaluate('''async (codes)=>{
                  const result=[];
                  for(const code of codes){
                    const image=new Image();image.src='data:image/svg+xml;base64,'+btoa(String.fromCharCode(...new TextEncoder().encode(Code128.svg(code).replace('viewBox=', 'width="1000" height="180" viewBox='))));
                    await image.decode();const actual=Code128.decodeImage(image);if(actual!==code)result.push({code,actual});
                  }
                  return result;
                }''',[p['code'] for p in state['products']])
                assert not decoded,decoded[:5]
                page.locator('#nav [data-page="scan"]').click()
                page.locator('#barcode-photo').set_input_files({'name':'etiqueta-real.png','mimeType':'image/png','buffer':photo})
                page.wait_for_timeout(350)
                assert page.locator('#scan-result .sku').filter(has_text=photo_code).count(),page.locator('#scan-status').inner_text()
                page.locator('#scan-code').fill('2ABFESS11510M00');page.locator('#scan-form button').click()
                page.locator('#scan-result .scanned-product').wait_for()
                page.locator('#scan-result [data-action="count"]').click()
                page.locator('#location').fill('TCO-A01-R02-N01');page.locator('#location-form [type="submit"]').click()
                page.locator('#modal').wait_for(state='hidden')
                page.locator('#scan-code').fill('2ABFESS11510M00');page.locator('#scan-form button').click()
                page.locator('#scan-result [data-action="count"]').click()
                assert '6912' not in page.locator('#modal-body').inner_text()
                page.locator('#quantity').fill('6900');page.locator('#operator').fill('QA temporal')
                page.locator('#count-form [type="submit"]').click();page.locator('#modal').wait_for(state='hidden')
                page.locator('#nav [data-page="integration"]').click()
                page.locator('[data-action="test-connection"]').click()
                page.locator('#connection-result').filter(has_text='INGEFIX_ODBC_CONNECTION').wait_for()
                assert page.locator('#lead_days').input_value()==''
                for key,value in {'period_days':'90','lead_days':'7','buffer_days':'3','review_days':'7'}.items():page.locator('#'+key).fill(value)
                page.locator('[name="period_confirmed"]').check();page.locator('[name="planning_confirmed"]').check()
                page.locator('#settings-form [type="submit"]').click()
                page.wait_for_timeout(250)
                page.locator('#nav [data-page="replenish"]').click()
                page.locator('[data-action="request"]').first.wait_for()
                page.screenshot(path=str(root/'artifacts'/'rop-v2.png'),full_page=True)
                page.locator('[data-action="request"]').first.click();page.locator('#request-form [type="submit"]').click();page.locator('#modal').wait_for(state='hidden')
                mobile=browser.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
                mobile.add_init_script("localStorage.setItem('ingefix-tour-v3','done')")
                mobile.goto(url+'/#overview');mobile.locator('.abc-cards').wait_for()
                mobile.screenshot(path=str(root/'artifacts'/'mobile-v2.png'),full_page=True)
                assert mobile.evaluate('document.documentElement.scrollWidth<=innerWidth')
                mobile.locator('#nav [data-page="scan"]').click()
                mobile.screenshot(path=str(root/'artifacts'/'scanner-mobile-v2.png'),full_page=True)
                assert mobile.evaluate('document.documentElement.scrollWidth<=innerWidth')
                assert not errors,errors
                browser.close()
                print(json.dumps(dict(passed=True,pages=12,real_barcodes_decoded=660,labels_pdf=19,js_errors=errors)))
        finally:http.shutdown();http.server_close();thread.join();server.DB=original

if __name__=='__main__':main()
