import json
import math
import sqlite3
import sys
import tempfile
import unittest
import uuid
import urllib.request
import urllib.error
import threading
from unittest.mock import patch
from datetime import date,timedelta
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import server
from domain import classify,prediction,DEFAULT_SETTINGS,enrich
from ingest import read_rotation


class DomainTests(unittest.TestCase):
    def test_abc_uses_volume_and_includes_boundary_product(self):
        ps=[dict(code='a',outbound=81),dict(code='b',outbound=15),dict(code='c',outbound=4)]
        classify(ps)
        self.assertEqual([p['abc'] for p in ps],['A','B','C'])
        self.assertAlmostEqual(sum(p['share'] for p in ps),1)

    def test_constant_forecast_and_zero_demand(self):
        f=prediction([10]*70)
        self.assertTrue(f['validated']);self.assertEqual(f['mae'],0);self.assertEqual(f['daily'],10)
        self.assertEqual(prediction([0]*70)['daily'],0)
        self.assertFalse(prediction([10]*20)['validated'])

    def test_real_source_no_duplicate_and_no_invented_physical(self):
        root=Path(__file__).resolve().parents[1]
        if not (root/'ROT 16-11.xlsx').exists():self.skipTest('Las fuentes de empresa no se publican en GitHub')
        ps=read_rotation(root/'ROT 16-11.xlsx')
        self.assertEqual(len(ps),654)
        seed=json.loads((root/'data/seed.json').read_text(encoding='utf-8'))
        self.assertEqual(len(seed['products']),660)
        self.assertEqual(sum(p['erp_stock'] is not None for p in seed['products']),403)
        hashes=[f['sha256'] for f in seed['sources'] if f['name'].startswith('EXISTENCIAS')]
        self.assertEqual(hashes[0],hashes[1])
        self.assertTrue(all(not p['location'] for p in seed['products']))


class StartupTests(unittest.TestCase):
    def test_port_is_exclusive(self):
        http=server.InventoryHTTPServer(('127.0.0.1',0),server.Handler)
        try:
            with self.assertRaises(OSError):server.InventoryHTTPServer(('127.0.0.1',http.server_port),server.Handler)
        finally:http.server_close()
    def test_state_failure_returns_json_instead_of_dropping_connection(self):
        http=server.InventoryHTTPServer(('127.0.0.1',0),server.Handler)
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with patch.object(server,'state',side_effect=RuntimeError('Test failure')),patch.object(server.logging,'exception'):
                with self.assertRaises(urllib.error.HTTPError) as caught:opener.open(f'http://127.0.0.1:{http.server_port}/api/state')
                self.assertEqual(caught.exception.code,500)
                self.assertIn('error',json.load(caught.exception))
        finally:http.shutdown();http.server_close();thread.join()


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.original=server.DB
        server.DB=Path(self.tmp.name)/'test.db';server.initialize();self.db=server.connect()
        self.code='2ABFESS11510M00'
        if not self.db.execute('SELECT 1 FROM products WHERE code=?',(self.code,)).fetchone():
            self.db.execute('INSERT INTO products VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(self.code,'Producto de prueba','QA','',100,27593,1,6912,'08','UN','2026-11-16','',0,0,'qa'))
            self.db.commit()
    def tearDown(self):
        self.db.close();server.DB=self.original;self.tmp.cleanup()
    def stock_body(self,stock=4):
        return dict(kind='stock',csv=f'code,warehouse,stock,reserved,in_transit,snapshot_at\n{self.code},08,{stock},2,8,{date.today()}')
    def apply(self,b):
        preview=server.mutate(self.db,'/api/import/preview',b)
        return server.mutate(self.db,'/api/import/commit',dict(b,hash=preview['hash']))
    def test_stock_rop_and_duplicate_requests(self):
        self.apply(self.stock_body())
        self.db.execute('DELETE FROM daily WHERE code=?',(self.code,))
        s=dict(DEFAULT_SETTINGS,period_days=90,period_confirmed=True,lead_days=7,buffer_days=3,review_days=7,planning_confirmed=True)
        server.mutate(self.db,'/api/settings',s)
        p=next(p for p in server.state(self.db)['products'] if p['code']==self.code)
        self.assertEqual(p['position'],10)
        d=27593/90
        self.assertEqual(p['rop'],math.ceil(d*7+math.ceil(d*3)))
        self.assertFalse(p['scenario']);self.assertEqual(p['risk'],'reponer')
        order=server.mutate(self.db,'/api/orders',dict(code=self.code,quantity=p['suggested']))
        with self.assertRaises(ValueError):server.mutate(self.db,'/api/orders',dict(code=self.code,quantity=1))
        server.mutate(self.db,'/api/order-status',dict(id=order['id'],status='aprobada'))
        self.assertEqual(self.db.execute('SELECT in_transit FROM products WHERE code=?',(self.code,)).fetchone()[0],8)
    def test_import_idempotent_and_unknown_sku_rejected_without_changes(self):
        b=self.stock_body();self.apply(b)
        self.assertTrue(self.apply(b)['already_imported'])
        bad=dict(b,csv=b['csv']+f'\nUNKNOWN,08,20,0,0,{date.today()}')
        with self.assertRaises(ValueError):self.apply(bad)
        self.assertEqual(self.db.execute('SELECT erp_stock FROM products WHERE code=?',(self.code,)).fetchone()[0],4)
    def test_bad_numbers_warehouse_dates_and_hash_rejected(self):
        for b in [self.stock_body('nan'),self.stock_body('inf'),dict(self.stock_body(),csv=self.stock_body()['csv'].replace(',08,',',01,'))]:
            with self.assertRaises(ValueError):self.apply(b)
        with self.assertRaises(ValueError):server.mutate(self.db,'/api/import/commit',dict(self.stock_body(),hash='tampered'))
    def test_count_preserves_erp_is_idempotent_and_stale_snapshot_rejected(self):
        server.mutate(self.db,'/api/locations',dict(code=self.code,location='TCO-A01-R01-N01'))
        p=dict(self.db.execute('SELECT * FROM products WHERE code=?',(self.code,)).fetchone())
        b=dict(code=self.code,location=p['location'],snapshot_version=p['snapshot_version'],quantity=3,
               operator='Prueba',reason='Por investigar',request_id=str(uuid.uuid4()))
        result=server.mutate(self.db,'/api/counts',b)
        self.assertTrue(server.mutate(self.db,'/api/counts',b)['already_saved'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM counts').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT erp_stock FROM products WHERE code=?',(self.code,)).fetchone()[0],p['erp_stock'])
        self.apply(self.stock_body())
        with self.assertRaises(ValueError):server.mutate(self.db,'/api/counts',dict(b,request_id=str(uuid.uuid4())))
        c=server.state(self.db)['products'];item=next(p for p in c if p['code']==self.code)
        self.assertFalse(item['count_matches_snapshot']);self.assertTrue(item['due'])
    def test_daily_forecast_import_and_gaps(self):
        rows=[f'{self.code},{date.today()-timedelta(days=69-i)},10' for i in range(70)]
        b=dict(kind='demand',csv='code,day,quantity\n'+'\n'.join(rows));self.apply(b)
        p=next(p for p in server.state(self.db)['products'] if p['code']==self.code)
        self.assertTrue(p['forecast']['validated']);self.assertFalse(p['scenario']);self.assertEqual(p['daily'],10)
        self.db.execute('DELETE FROM daily WHERE code=? AND day=?',(self.code,(date.today()-timedelta(days=10)).isoformat()))
        p=next(p for p in server.state(self.db)['products'] if p['code']==self.code)
        self.assertTrue(p['forecast']['missing_dates']);self.assertTrue(p['scenario'])
    def test_no_invented_planning_defaults(self):
        data=server.state(self.db)
        self.assertIsNone(data['settings']['period_days'])
        self.assertIsNone(data['settings']['lead_days'])
        self.assertTrue(all(p['rop'] is None and p['suggested'] is None for p in data['products']))
        if len(data['products'])==660:
            self.assertEqual(sum(p['abc']=='ND' for p in data['products']),6)
            self.assertEqual(sum(p['abc']=='C' for p in data['products']),598)
    def test_master_import_keeps_code_and_does_not_invent_saldo(self):
        b=dict(kind='master',csv='code,name,warehouse,unit\n000-TEST.01,Prueba de maestro,08,UN')
        self.apply(b)
        p=next(p for p in server.state(self.db)['products'] if p['code']=='000-TEST.01')
        self.assertIsNone(p['erp_stock']);self.assertIsNone(p['outbound']);self.assertEqual(p['abc'],'ND')
        self.assertEqual(p['location'],'')
    def test_classifier_settings_change_real_classification(self):
        if self.db.execute('SELECT COUNT(*) FROM products').fetchone()[0]<10:self.skipTest('Prueba requiere maestro de empresa')
        before=sum(p['abc']=='A' for p in server.state(self.db)['products'])
        server.mutate(self.db,'/api/abc-settings',dict(abc_a=60,abc_b=90,count_a=3,count_b=14,count_c=60))
        after=sum(p['abc']=='A' for p in server.state(self.db)['products'])
        self.assertLess(after,before)
        with self.assertRaises(ValueError):server.mutate(self.db,'/api/abc-settings',dict(abc_a=90,abc_b=80))
    def test_direct_sync_rolls_back_master_if_stock_contract_fails(self):
        import os
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integration'))
        import sync_softland
        source={'master':'code,name,warehouse,unit\nSYNC-TEST,Producto solo de prueba,08,UN',
                'stock':f'code,warehouse,stock,reserved,in_transit,snapshot_at\nSYNC-TEST,01,4,0,0,{date.today()}'}
        with patch.dict(os.environ,{'INGEFIX_ODBC_CONNECTION':'TEST-NOT-A-REAL-CONNECTION','INGEFIX_SYNC_DEMAND':'0'}),patch.object(server.importlib.util,'find_spec',return_value=True),patch.object(sync_softland,'read_sql',side_effect=lambda kind:source[kind]):
            result=server.integration_read(True)
        self.assertFalse(result['connected'])
        self.assertIsNone(self.db.execute("SELECT code FROM products WHERE code='SYNC-TEST'").fetchone())
    def test_connection_probe_does_not_persist_master_or_stock(self):
        import os
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integration'))
        import sync_softland
        source={'master':'code,name,warehouse,unit\nSYNC-TEST,Producto solo de prueba,08,UN',
                'stock':f'code,warehouse,stock,reserved,in_transit,snapshot_at\nSYNC-TEST,08,4,0,0,{date.today()}'}
        with patch.dict(os.environ,{'INGEFIX_ODBC_CONNECTION':'TEST-NOT-A-REAL-CONNECTION','INGEFIX_SYNC_DEMAND':'0'}),patch.object(server.importlib.util,'find_spec',return_value=True),patch.object(sync_softland,'read_sql',side_effect=lambda kind:source[kind]):
            probe=server.integration_read(False)
            self.assertTrue(probe['connected'])
            self.assertIsNone(self.db.execute("SELECT code FROM products WHERE code='SYNC-TEST'").fetchone())
            applied=server.integration_read(True)
        self.assertTrue(applied['applied'])
        self.assertEqual(self.db.execute("SELECT erp_stock FROM products WHERE code='SYNC-TEST'").fetchone()[0],4)


if __name__=='__main__':unittest.main()
