import json
import sys
import tempfile
import unittest
import uuid
from datetime import date,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import server

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.previous=server.DB;server.DB=Path(self.tmp.name)/'db.sqlite';server.initialize();self.db=server.connect();self.code='2ABFESS11510M00'
        if not self.db.execute('SELECT 1 FROM products WHERE code=?',(self.code,)).fetchone():
            self.db.execute('INSERT INTO products VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(self.code,'Producto de prueba','QA','',100,100,1,6912,'08','UN','2026-11-16','',0,0,'qa'))
            self.db.commit()
    def tearDown(self):self.db.close();server.DB=self.previous;self.tmp.cleanup()
    def call(self,path,b):return server.mutate(self.db,path,b)
    def receive(self,parent,kind='receipt',qty=3,good=2,request=None):return self.call('/api/physical-events',dict(parent_id=parent,kind=kind,quantity=qty,good=good,request_id=request or str(uuid.uuid4()),operator='QA',document='GUIA-QA'))
    def load(self,kind,csv):
        b=dict(kind=kind,csv=csv);preview=self.call('/api/documents/preview',b);return self.call('/api/documents/import',dict(b,hash=preview['hash']))
    def test_receipt_partial_idempotent_no_inventory_increment(self):
        before=self.db.execute('SELECT erp_stock FROM products WHERE code=?',(self.code,)).fetchone()[0]
        r=self.call('/api/inbound',dict(code=self.code,expected=10,source_doc='SOL-QA'));key=str(uuid.uuid4())
        self.receive(r['id'],request=key);self.receive(r['id'],request=key)
        state=server.state(self.db);row=state['workflows']['inbound'][0]
        self.assertEqual(row['remaining'],7);self.assertEqual(row['good'],2)
        self.assertEqual(self.db.execute('SELECT erp_stock FROM products WHERE code=?',(self.code,)).fetchone()[0],before)
        with self.assertRaises(ValueError):self.receive(r['id'],qty=8,good=8)
    def test_commercial_credit_does_not_allow_physical_return(self):
        text=f'id,code,quantity,day,reference,reason,inventory_effect\nNC-QA,{self.code},5,{date.today()},F-QA,Correccion precio,no_stock'
        self.load('credits',text)
        with self.assertRaises(ValueError):self.receive('NC-QA','return')
        text=text.replace('no_stock','return');self.load('credits',text)
        self.receive('NC-QA','return',5,4)
        self.assertEqual(server.state(self.db)['workflows']['credits'][0]['good'],4)
        with self.assertRaises(ValueError):self.call('/api/credit-classify',dict(id='NC-QA',inventory_effect='no_stock',operator='QA',explanation='No puede reclasificarse después de recibir'))
    def test_document_reference_can_resolve_missing_guide(self):
        r=self.call('/api/inbound',dict(code=self.code,expected=1,source_doc='SOL-QA'))
        e=self.call('/api/physical-events',dict(parent_id=r['id'],kind='receipt',quantity=1,good=1,request_id=str(uuid.uuid4()),operator='QA',document=''))
        self.assertEqual(server.state(self.db)['workflows']['inbound'][0]['without_document'],1)
        self.call('/api/event-document',dict(id=e['id'],document='GUIA-QA',operator='QA'))
        self.assertEqual(server.state(self.db)['workflows']['inbound'][0]['without_document'],0)
    def test_conciliation_requires_matching_real_import_and_does_not_add_stock(self):
        r=self.call('/api/inbound',dict(code=self.code,expected=3,source_doc='SOL-QA'));e=self.receive(r['id'],qty=3,good=2)
        self.load('movements',f'id,code,day,entry,exit,document\nMOV-QA,{self.code},{date.today()},2,0,GUIA-QA')
        self.call('/api/reconcile',dict(event_id=e['id'],movement_id='MOV-QA',operator='QA'))
        with self.assertRaises(ValueError):self.call('/api/reconcile',dict(event_id=e['id'],movement_id='MOV-QA',operator='QA'))
        self.assertEqual(self.db.execute('SELECT erp_movement_id FROM physical_events WHERE id=?',(e['id'],)).fetchone()[0],'MOV-QA')
    def test_upcoming_order_prioritizes_count(self):
        self.call('/api/commitments',dict(code=self.code,ordered=1000000,delivered=0,due_date=(date.today()+timedelta(days=1)).isoformat(),reference='NV-QA'))
        p=next(p for p in server.state(self.db)['products'] if p['code']==self.code)
        self.assertEqual(p['upcoming_orders'],1);self.assertGreater(p['order_shortage'],0);self.assertTrue(p['recommended_count'])
    def test_document_import_is_atomic_and_idempotent(self):
        text=f'id,code,quantity,day,reference,reason,inventory_effect\nNC-QA,{self.code},5,{date.today()},F-QA,Devolucion,return'
        self.load('credits',text);self.assertTrue(self.load('credits',text)['already_imported'])
        with self.assertRaises(ValueError):self.load('credits',text+'\nNC-ERR,UNKNOWN,2,2026-11-16,F,Error,return')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM credits').fetchone()[0],1)
    def test_forecasting_uses_verified_pdf_blocks(self):
        if not (Path(__file__).resolve().parents[1]/'data'/'ledger.json').exists():self.skipTest('Historial privado no incluido en repositorio')
        count=self.db.execute('SELECT COUNT(DISTINCT code) FROM daily').fetchone()[0]
        self.assertEqual(count,401)
        p=next(p for p in server.state(self.db)['products'] if p['code']==self.code)
        self.assertEqual(p['forecast']['days'],47);self.assertTrue(p['forecast']['validated'])
        self.assertTrue(p['forecast']['short_history']);self.assertEqual(len(p['forecast']['scores']),3)

if __name__=='__main__':unittest.main()
