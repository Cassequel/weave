"""Loopback-only HTTP service; artwork is never sent to a remote API."""
import argparse
import base64
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0,str(Path(__file__).parent / '.deps'))
from service import DesignService
from inkstitch_backend import executable, DigitizingError

ROOT = Path(__file__).parent / 'web'
PORT = 8765
SERVICE = DesignService()
STARTUP_IMAGE = None


class Handler(BaseHTTPRequestHandler):
    def reply(self,value,status=200,mime='application/json',filename=None):
        body = json.dumps(value).encode() if mime == 'application/json' else value
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        if filename: self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError): pass

    def allowed(self,mutation=False):
        hosts = (f'127.0.0.1:{PORT}',f'localhost:{PORT}')
        origin = self.headers.get('Origin')
        return self.headers.get('Host') in hosts and ((not mutation and not origin) or origin in tuple('http://'+h for h in hosts))

    def do_GET(self):
        if not self.allowed(): return self.reply({'error':'Only the local Weave page can use this service.'},403)
        path = urlsplit(self.path).path
        try:
            if path == '/api/health':
                try: executable(); available = True
                except DigitizingError: available = False
                return self.reply({'engine':'Ink/Stitch 3.3.0','available':available})
            if path == '/api/startup-image': return self.reply(STARTUP_IMAGE)
            if path.startswith('/api/jobs/'): return self.reply(SERVICE.status(path.rsplit('/',1)[1]))
            if path.startswith('/api/designs/') and path.endswith('.pes'):
                return self.reply(SERVICE.pes(path.rsplit('/',1)[1][:-4]),mime='application/octet-stream',filename='weave-design.pes')
            if path.startswith('/api/prepared/') and path.endswith('.svg'):
                return self.reply(SERVICE.svg(path.rsplit('/',1)[1][:-4]),mime='image/svg+xml',filename='weave-artwork.svg')
            files = {'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
            if path not in files: return self.reply({'error':'Not found.'},404)
            file = ROOT / files[path]
            return self.reply(file.read_bytes(),mime={'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[file.suffix[1:]])
        except ValueError as exc: self.reply({'error':str(exc)},400)

    def do_POST(self):
        if not self.allowed(True): return self.reply({'error':'Only the local Weave page can use this service.'},403)
        try:
            size = int(self.headers.get('Content-Length','0'))
            if not 0 < size <= 18*1024*1024: raise ValueError('Request is empty or exceeds 18 MB.')
            if self.headers.get('Content-Type','').split(';')[0] != 'application/json': raise ValueError('Expected a JSON request.')
            self.connection.settimeout(30)
            body = json.loads(self.rfile.read(size))
            if not isinstance(body,dict): raise ValueError('Expected a JSON object.')
            if self.path == '/api/prepare': return self.reply(SERVICE.prepare(body.get('image'),body.get('settings')))
            if self.path == '/api/jobs': return self.reply({'jobId':SERVICE.start(body.get('preparationId'))},202)
            if self.path == '/api/cancel': SERVICE.cancel(body.get('jobId')); return self.reply({'cancelled':True})
            self.reply({'error':'Not found.'},404)
        except (ValueError,TypeError) as exc: self.reply({'error':str(exc)},400)
        except Exception: self.reply({'error':'Unable to process this artwork. Try a smaller or simpler image.'},500)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run the local Weave studio.')
    parser.add_argument('--image',type=Path,help='Optional local PNG/JPEG to open on startup.')
    args = parser.parse_args()
    if args.image:
        if args.image.suffix.lower() not in ('.jpg','.jpeg','.png'): parser.error('Startup image must be PNG or JPEG.')
        if args.image.stat().st_size > 12*1024*1024: parser.error('Image exceeds 12 MB.')
        mime = mimetypes.guess_type(args.image.name)[0] or 'image/png'
        STARTUP_IMAGE = dict(name=args.image.name,data=f'data:{mime};base64,'+base64.b64encode(args.image.read_bytes()).decode())
    server = ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
    print(f'Weave is ready at http://127.0.0.1:{PORT}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close(); SERVICE.close()
