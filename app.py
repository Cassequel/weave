"""Local-only HTTP server for Weave."""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / '.deps'))
from engine import convert, pes_bytes

ROOT = Path(__file__).parent / 'web'
PORT = 8765


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        files = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if self.path not in files:
            self.send(404, b'Not found', 'text/plain'); return
        name, mime = files[self.path]
        self.send(200, (ROOT / name).read_bytes(), mime)

    def do_POST(self):
        if self.headers.get('Origin') not in (f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}'):
            self.send(403, b'Forbidden', 'text/plain'); return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size <= 0 or size > 18 * 1024 * 1024: raise ValueError('Request exceeds the allowed size.')
            payload = json.loads(self.rfile.read(size))
            result = convert(payload['image'], payload['settings'])
            if self.path == '/api/convert':
                self.send(200, json.dumps(result).encode(), 'application/json')
            elif self.path == '/api/export':
                self.send(200, pes_bytes(result), 'application/octet-stream')
            else:
                self.send(404, b'Not found', 'text/plain')
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            self.send(400, json.dumps({'error':str(exc)}).encode(), 'application/json')
        except Exception:
            self.send(500, json.dumps({'error':'Conversion failed. Try a simpler image.'}).encode(), 'application/json')
            import traceback; traceback.print_exc()


if __name__ == '__main__':
    server = HTTPServer(('127.0.0.1', PORT), Handler)
    print(f'Weave is running at http://127.0.0.1:{PORT}', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
