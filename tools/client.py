#!/usr/bin/env python3
"""Serve repo-built browser code locally; proxy only prototype API requests over HTTPS."""
import argparse, hashlib, json, ssl, urllib.request, urllib.error
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--server',default='https://whisper.speeches.dev')
parser.add_argument('--port',type=int,default=8780)
args=parser.parse_args()
server=urlsplit(args.server)
if server.scheme!='https' or not server.hostname or server.username or server.password or server.query or server.fragment or server.path not in ('','/'):
    parser.error('--server must be a plain HTTPS origin')
build=ROOT/'attestation/build'
if not (build/'verifier.wasm').is_file() or not (build/'wasm_exec.js').is_file():
    parser.error('First build the local verifier with bash attestation/build.sh')
api={'/health','/v1/runtime','/v1/attestation','/v1/audio/transcriptions'}
class Handler(SimpleHTTPRequestHandler):
    def translate_path(self,path):
        clean=urlsplit(path).path
        if clean=='/': base=ROOT/'static';target=base/'index.html'
        elif clean.startswith('/static/attestation/'):
            base=build;target=base/clean.removeprefix('/static/attestation/')
            if target.name not in ('verifier.wasm','wasm_exec.js'): return '/not-found'
        elif clean.startswith('/static/'): base=ROOT/'static';target=base/clean.removeprefix('/static/')
        else:return '/not-found'
        target=target.resolve()
        if not target.is_relative_to(base) or not target.is_file(): return '/not-found'
        return str(target)
    def log_message(self,*args): pass
    def end_headers(self):
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        super().end_headers()
    def proxy(self):
        if self.path not in api:
            self.send_error(404);return
        try:size=int(self.headers.get('Content-Length','0'))
        except ValueError:self.send_error(400);return
        limit=65*1024*1024 if self.path.endswith('/transcriptions') else 4096
        if not 0<=size<=limit:self.send_error(413);return
        body=self.rfile.read(size) if self.command=='POST' else None
        headers={k:self.headers[k] for k in ('Content-Type','X-Session','X-IV','X-Sequence','X-Language') if k in self.headers}
        request=urllib.request.Request(args.server.rstrip('/')+self.path,data=body,headers=headers,method=self.command)
        try:response=urllib.request.urlopen(request,timeout=150,context=ssl.create_default_context())
        except urllib.error.HTTPError as error:response=error
        except (OSError,urllib.error.URLError):self.send_error(502);return
        with response:
            payload=response.read(8*1024*1024+1)
            if len(payload)>8*1024*1024:self.send_error(502);return
            self.send_response(response.status)
            self.send_header('Content-Type',response.headers.get('Content-Type','application/json'))
            self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
    def do_GET(self):
        if self.path in api:self.proxy()
        else:super().do_GET()
    def do_POST(self):self.proxy()
print(f'Local client: http://127.0.0.1:{args.port} → {args.server}',flush=True)
ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
