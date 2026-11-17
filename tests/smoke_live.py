"""Comprobar una instancia local existente sin modificar datos."""
import argparse
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8766');args=parser.parse_args()
with sync_playwright() as pw:
    installed=sorted((Path(os.environ.get('LOCALAPPDATA',''))/'ms-playwright').glob('chromium-*/chrome-win64/chrome.exe'))
    browser=pw.chromium.launch(headless=True,**({'executable_path':str(installed[-1])} if installed else {}))
    page=browser.new_page();page.add_init_script("localStorage.setItem('ingefix-tour-v3','done')");errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(args.url);page.locator('.operator-next').wait_for(timeout=15000)
    assert page.locator('.operator-fixed-help>div').count()==3
    page.locator('.operator-analysis>summary').click();page.locator('.abc-cards').wait_for()
    page.locator('[data-action=phone-preview]').first.click()
    page.frame_locator('iframe').locator('.warehouse-one-task').wait_for()
    page.frame_locator('iframe').locator('video#scan-video').wait_for(state='attached')
    page.screenshot(path=str(Path(__file__).resolve().parents[1]/'artifacts'/'vista-movil-actual.png'))
    assert page.locator('#load-error').is_hidden()
    response=page.request.get(args.url+'/api/state');assert response.ok
    assert len(response.json()['products'])==660
    assert not errors,errors
    print(json.dumps({'url':args.url,'products':660,'visible_dashboard':True,'js_errors':errors}))
    browser.close()
