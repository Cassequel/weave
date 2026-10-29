import json
from pathlib import Path
import sys
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.deps'))
import app
from service import DesignService
from test_pipeline import fixture, SETTINGS

class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service=app.SERVICE;cls.port=app.PORT
        app.SERVICE=DesignService(lambda p,c:({'threads':p['palette']},b'#PES-test-exact'))
        cls.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        app.PORT=cls.server.server_port
        cls.base=f'http://127.0.0.1:{app.PORT}'
        cls.thread=Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();app.SERVICE.close();app.SERVICE=cls.service;app.PORT=cls.port

    def request(self,path,body=None,origin=None):
        headers={'Origin':origin or self.base,'Content-Type':'application/json'}
        req=Request(self.base+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
        return urlopen(req,timeout=10)

    def test_cross_site_preparation_rejected(self):
        with self.assertRaises(HTTPError) as context:self.request('/api/prepare',{},'https://example.com')
        self.assertEqual(context.exception.code,403)

    def test_prepare_then_export_exact_cached_file(self):
        with self.request('/api/prepare',{'image':fixture(),'settings':SETTINGS}) as response:p=json.load(response)
        with self.request('/api/jobs',{'preparationId':p['preparationId']}) as response:key=json.load(response)['jobId']
        # Mock conversion has no blocking work; the job future is also drained deterministically.
        app.SERVICE.pool.submit(lambda:None).result(timeout=5)
        with self.request('/api/jobs/'+key) as response:r=json.load(response)
        self.assertEqual(r['status'],'complete')
        with self.request('/api/designs/'+key+'.pes') as response:self.assertEqual(response.read(),b'#PES-test-exact')
        with self.request('/api/prepared/'+p['preparationId']+'.svg') as response:self.assertEqual(response.read().decode(),p['svg'])

    def test_invalid_and_expired_requests(self):
        for path,body in [('/api/jobs',{'preparationId':'expired'}),('/api/prepare',{'image':'bad','settings':SETTINGS})]:
            with self.subTest(path=path),self.assertRaises(HTTPError) as context:self.request(path,body)
            self.assertEqual(context.exception.code,400)

if __name__=='__main__':unittest.main()
