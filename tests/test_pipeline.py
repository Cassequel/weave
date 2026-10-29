import base64
import io
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch, Mock
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.deps'))
from PIL import Image, ImageDraw
from pyembroidery import EmbPattern, STITCH, END, write_pes
from preparation import prepare, validate_settings, clean_paths, SVG, INK
from inkstitch_backend import inspect_pes, export_pes, digitize, DigitizingError
from service import DesignService


def fixture():
    im=Image.new('RGB',(160,160),'white'); d=ImageDraw.Draw(im)
    d.rectangle((20,20,140,140),fill='#002e5d'); d.rectangle((55,55,105,105),fill='white')
    buf=io.BytesIO();im.save(buf,'PNG')
    return 'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()

SETTINGS=dict(width=40,height=40,paletteMode='navy-white',colors=2)

class PreparationTests(unittest.TestCase):
    def test_tracer_rounding_preserves_large_white_region(self):
        root=ET.fromstring(f'<svg xmlns="{SVG}"><path fill="#FEFEFE" d="M0,0 L400,0 L400,400 L0,400Z"/><path fill="#FE00FE" d="M0,0 L800,0 L800,800 L0,800Z"/></svg>')
        paths=clean_paths(root,['#ffffff','#002e5d'],'#ff00ff')
        self.assertEqual(len(paths),1)
        self.assertEqual(paths[0].get('fill'),'#ffffff')

    def test_exterior_removed_enclosed_white_preserved(self):
        p=prepare(fixture(),SETTINGS)
        im=Image.open(io.BytesIO(base64.b64decode(p['image'].split(',')[1])))
        self.assertEqual(im.getpixel((0,0))[3],0)
        self.assertEqual(im.getpixel((160,160)),(255,255,255,255))
        self.assertEqual(im.getpixel((50,50)),(0,46,93,255))
        root=ET.fromstring(p['svg']); paths=root.findall(f'{{{SVG}}}path')
        self.assertEqual({n.get('fill').lower() for n in paths},{'#ffffff','#002e5d'})
        self.assertEqual(root.find(f'{{{SVG}}}metadata/{{{INK}}}inkstitch_svg_version').text,'4')
        self.assertEqual(root.get('width'),'40.0mm')
        navy=next(n for n in paths if n.get('fill').lower()=='#002e5d')
        self.assertGreaterEqual(navy.get('d').upper().count('Z'),2,'Navy must have a hole, not cover the white thread.')
        self.assertTrue(all(n.get(f'{{{INK}}}fill_method')=='tatami_fill' for n in paths))

    def test_keep_background_and_palette_override(self):
        p=prepare(fixture(),{**SETTINGS,'removeBackground':False,'threadColors':['#fffafa','#123456']})
        im=Image.open(io.BytesIO(base64.b64decode(p['image'].split(',')[1])))
        self.assertEqual(im.getpixel((0,0)),(255,250,250,255))
        self.assertEqual(im.getpixel((50,50)),(18,52,86,255))

    def test_settings_reject_nonfinite_oversize_and_invalid_color(self):
        for update in ({'width':float('nan')},{'height':180},{'spacing':0},{'colors':12},{'threadColors':['bad']}):
            with self.subTest(update=update),self.assertRaises(ValueError):validate_settings({**SETTINGS,**update})
        validate_settings({**SETTINGS,'width':170,'height':120})

    def test_empty_and_malformed_input(self):
        for image in ('broken','data:image/png;base64,YQ=='):
            with self.assertRaises(ValueError):prepare(image,SETTINGS)
        im=Image.new('RGBA',(20,20));buf=io.BytesIO();im.save(buf,'PNG')
        with self.assertRaisesRegex(ValueError,'No visible artwork'):prepare('data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode(),SETTINGS)

    def test_project_roundtrip_preserves_source_settings_and_result(self):
        project={'version':2,'source':{'data':fixture(),'name':'synthetic.png'},'settings':{**SETTINGS,'threadColors':['#fefefe','#002e5d']},'locked':True}
        reopened=json.loads(json.dumps(project))
        self.assertEqual(reopened,project)
        a=prepare(project['source']['data'],project['settings']);b=prepare(reopened['source']['data'],reopened['settings'])
        self.assertEqual(a['svg'],b['svg'])

class BackendTests(unittest.TestCase):
    def test_readback_rejects_actual_oversize(self):
        p=EmbPattern();p.add_thread('#002e5d');p.add_stitch_absolute(STITCH,0,0);p.add_stitch_absolute(STITCH,1800,1300);p.add_command(END)
        buf=io.BytesIO();write_pes(p,buf,{'version':6})
        with self.assertRaisesRegex(DigitizingError,'exceed the hoop'):inspect_pes(buf.getvalue(),{'warnings':[],'width':40,'height':40})

    @patch('inkstitch_backend.executable',return_value=Path('engine.exe'))
    @patch('inkstitch_backend.subprocess.Popen')
    def test_cancel_kills_process(self,popen,exe):
        process=popen.return_value;process.poll.return_value=None
        cancel=threading.Event();cancel.set()
        with self.assertRaisesRegex(DigitizingError,'cancelled'):export_pes('<svg/>',cancel)
        process.kill.assert_called_once();process.communicate.assert_called_once()

    @patch('inkstitch_backend.executable',return_value=Path('engine.exe'))
    @patch('inkstitch_backend.subprocess.Popen')
    def test_bad_output_is_useful_error(self,popen,exe):
        p=popen.return_value;p.communicate.return_value=(b'',b'Invalid fill geometry');p.returncode=1;p.poll.return_value=1
        with self.assertRaisesRegex(DigitizingError,'Invalid fill geometry'):export_pes('<svg/>')

class ServiceTests(unittest.TestCase):
    def test_exact_export_and_expired_preparation(self):
        service=DesignService(lambda p,c:({'threads':p['palette']},b'exact-pes-bytes'))
        try:
            with self.assertRaises(ValueError):service.start('expired')
            p=service.prepare(fixture(),SETTINGS);key=service.start(p['preparationId'])
            deadline=time.monotonic()+3
            while service.status(key)['status'] not in ('complete','failed') and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(service.status(key)['status'],'complete')
            self.assertEqual(service.pes(key),b'exact-pes-bytes')
            self.assertEqual(service.status(key)['result']['designId'],key)
            self.assertEqual(service.svg(p['preparationId']).decode(),p['svg'])
        finally:service.close()

    def test_cancel_cannot_publish_result(self):
        entered=threading.Event()
        def worker(p,c):entered.set();c.wait(3);return {},b'cancelled-bytes'
        service=DesignService(worker)
        try:
            p=service.prepare(fixture(),SETTINGS);key=service.start(p['preparationId']);self.assertTrue(entered.wait(2));service.cancel(key)
            service.pool.shutdown(wait=True)
            self.assertEqual(service.status(key)['status'],'cancelled')
            with self.assertRaises(ValueError):service.pes(key)
        finally:service.close()

@unittest.skipUnless(os.environ.get('WEAVE_INTEGRATION')=='1','Set WEAVE_INTEGRATION=1 to run the installed Ink/Stitch engine.')
class InkStitchIntegration(unittest.TestCase):
    def test_real_shape_to_pes_roundtrip(self):
        p=prepare(fixture(),SETTINGS);pes=export_pes(p['svg']);r=inspect_pes(pes,p)
        self.assertTrue(pes.startswith(b'#PES'));self.assertGreater(r['stitchCount'],100)
        self.assertLess(r['jumpCount'],100);self.assertGreater(r['width'],29);self.assertLessEqual(r['width'],31)
        self.assertEqual(r['threads'],['#ffffff','#002e5d'])
        self.assertEqual(r,inspect_pes(pes,p))

if __name__=='__main__':unittest.main()
