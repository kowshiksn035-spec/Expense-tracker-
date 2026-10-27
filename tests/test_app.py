"""PennyPilot browser regression test. Run: python tests/test_app.py"""
from pathlib import Path
from threading import Thread
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
from playwright.sync_api import sync_playwright
import shutil, json, tempfile

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / 'screenshots'
SHOTS.mkdir(exist_ok=True)
class Quiet(SimpleHTTPRequestHandler):
    def log_message(self,*args): pass

def run():
    srv=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(ROOT)))
    Thread(target=srv.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            executable=shutil.which('chromium') or shutil.which('google-chrome')
            browser=p.chromium.launch(executable_path=executable,headless=True,args=['--no-sandbox'])
            context=browser.new_context(viewport={'width':1450,'height':1000},device_scale_factor=1,accept_downloads=True)
            page=context.new_page(); js_errors=[];page.on('pageerror',lambda e: js_errors.append(str(e)))
            sandbox_fallback=False
            try:
                page.goto('http://127.0.0.1:%s/'%srv.server_address[1],wait_until='domcontentloaded')
            except Exception as err:
                if 'ERR_BLOCKED_BY_ADMINISTRATOR' not in str(err): raise
                sandbox_fallback=True
                html=(ROOT/'index.html').read_text(encoding='utf-8')
                css=(ROOT/'styles.css').read_text(encoding='utf-8')
                js=(ROOT/'app.js').read_text(encoding='utf-8')
                shim="const store = new Map(); Object.defineProperty(window,'localStorage',{configurable:true,value:{getItem:k=>store.has(k)?store.get(k):null,setItem:(k,v)=>store.set(k,String(v)),removeItem:k=>store.delete(k)}});"
                html=html.replace('<link rel="stylesheet" href="styles.css">','<style>'+css+'</style>')
                html=html.replace('<script src="app.js" defer></script>','<script>'+shim+'</script><script>'+js+'</script>')
                page.set_content(html,wait_until='domcontentloaded')
                print('NOTE: Managed Chromium blocks local navigation. Testing UI with in-memory localStorage fallback; disk persistence needs manual check.')
            page.locator('.transaction').first.wait_for()
            assert page.locator('.transaction').count()==16
            assert page.locator('#balanceStat').inner_text().startswith('₹')
            page.screenshot(path=str(SHOTS/'dashboard.png'),full_page=True,animations='disabled')
            print('PASS initial dashboard and seeded demo transactions')
            page.locator('#addBtn').click();assert page.locator('#formDialog').is_visible()
            page.screenshot(path=str(SHOTS/'add-transaction.png'),full_page=False,animations='disabled')
            page.locator('#txTitle').fill('AAT test lunch')
            page.locator('#txAmount').fill('180')
            page.locator('#txDate').fill('2026-10-28')
            page.locator('#txCategory').select_option('Food & drinks')
            page.locator('#saveTransaction').click()
            assert page.locator('.transaction').count()==17
            print('PASS create expense and recalculate totals')
            page.locator('#search').fill('AAT test lunch');assert page.locator('.transaction').count()==1
            page.locator('#typeFilter').select_option('income');assert page.locator('.transaction').count()==0
            page.locator('#typeFilter').select_option('expense');assert page.locator('.transaction').count()==1
            print('PASS search and type filters')
            page.get_by_role('button',name='Edit AAT test lunch').click()
            page.locator('#txTitle').fill('Updated test lunch');page.locator('#txAmount').fill('220');page.locator('#saveTransaction').click()
            page.locator('#search').fill('Updated test lunch');assert page.locator('.transaction').count()==1
            print('PASS edit expense')
            if sandbox_fallback: page.evaluate('load();render()')
            else: page.reload(wait_until='domcontentloaded')
            page.locator('#search').fill('Updated test lunch')
            assert page.locator('.transaction').count()==1
            print('PASS data rehydration'+(' (in-memory shim; no real reload)' if sandbox_fallback else ' after actual reload'))
            page.locator('#resetFilters').click()
            page.locator('#budgetInput').fill('20000');page.locator('#budgetForm').evaluate('(x)=>x.requestSubmit()')
            assert page.locator('#budgetLimit').inner_text()=='₹20,000'
            if sandbox_fallback: page.evaluate('load();render()')
            else: page.reload(wait_until='domcontentloaded')
            assert page.locator('#budgetLimit').inner_text()=='₹20,000'
            print('PASS budget update and persistence')
            with page.expect_download() as ev: page.locator('#exportBtn').click()
            download=ev.value;assert download.suggested_filename.endswith('.csv')
            with tempfile.TemporaryDirectory() as tmp:
                filename=Path(tmp)/'export.csv';download.save_as(str(filename))
                csv=filename.read_text(encoding='utf-8-sig');assert 'Updated test lunch' in csv and '220' in csv
            print('PASS CSV download')
            page.locator('#search').fill('Updated test lunch')
            page.once('dialog',lambda dialog:dialog.accept())
            page.get_by_role('button',name='Delete Updated test lunch').click()
            assert page.locator('.transaction').count()==0
            page.locator('#resetFilters').click();assert page.locator('.transaction').count()==16
            print('PASS deletion and restored count')
            page.set_viewport_size({'width':390,'height':844})
            page.locator('#menuButton').click();assert 'open' in page.locator('#side').get_attribute('class')
            page.locator('button[data-view="transactions"]').click();assert page.locator('#breadcrumb').inner_text()=='Transactions'
            page.screenshot(path=str(SHOTS/'mobile.png'),full_page=True,animations='disabled')
            print('PASS responsive mobile navigation')
            assert not js_errors,js_errors
            print('PASS no uncaught JavaScript errors')
            context.close();browser.close()
    finally: srv.shutdown()
if __name__=='__main__':run()