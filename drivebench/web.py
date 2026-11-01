from __future__ import annotations
import ipaddress
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from urllib.parse import urlsplit
from .protocol import strict_json
from .reports import junit_xml
from .service import BusyError
from .garage import CATALOG
from .measurements import SIGNALS, assess, template_csv

WEB = Path(__file__).resolve().parent / "web"
RUN_PATH = re.compile(r"^/api/runs/([a-f0-9]{32})(?:/(export\.json|junit\.xml))?$")
ASSESSMENT_PATH = re.compile(r"^/api/assessments/([a-f0-9]{32})(?:/(export\.json|report\.txt))?$")


def local_host(host):
    if host == "localhost": return True
    try: return ipaddress.ip_address(host).is_loopback
    except ValueError: return False


def make_server(address, service):
    if not local_host(address[0]): raise ValueError("Dashboard must bind to a loopback address")
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup(); self.connection.settimeout(5)

        def log_message(self, *_): pass

        def send(self, status, value, mime="application/json; charset=utf-8", filename=None):
            data = value if isinstance(value, bytes) else json.dumps(value, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type",mime); self.send_header("Content-Length",str(len(data)))
            self.send_header("Cache-Control","no-store"); self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.send_header("Referrer-Policy","no-referrer"); self.send_header("X-Frame-Options","DENY")
            if filename: self.send_header("Content-Disposition",f'attachment; filename="{filename}"')
            self.end_headers()
            try: self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError): pass

        def boundary(self, mutation=False):
            try: host = urlsplit("http://"+self.headers.get("Host", "")).hostname
            except ValueError: host = None
            if not host or not local_host(host): self.send(403,{"error":"Local Host header required"}); return False
            if mutation:
                origin = self.headers.get("Origin")
                if self.headers.get("X-DriveBench") != "1" or self.headers.get("Sec-Fetch-Site") == "cross-site":
                    self.send(403,{"error":"X-DriveBench: 1 and a same-origin request are required"}); return False
                if origin:
                    try: parsed = urlsplit(origin)
                    except ValueError:
                        self.send(403,{"error":"Invalid Origin"}); return False
                    if parsed.scheme != "http" or parsed.netloc != self.headers.get("Host"):
                        self.send(403,{"error":"Same-origin request required"}); return False
            return True

        def do_GET(self):
            if not self.boundary(): return
            path = urlsplit(self.path).path
            try:
                if path in {"/", "/app.js", "/style.css", "/garage.js", "/garage.css"}:
                    name, mime = {"/":("index.html","text/html; charset=utf-8"),"/app.js":("app.js","text/javascript; charset=utf-8"),"/garage.js":("garage.js","text/javascript; charset=utf-8"),"/garage.css":("garage.css","text/css; charset=utf-8"),"/style.css":("style.css","text/css; charset=utf-8")}[path]
                    self.send(200,(WEB/name).read_bytes(),mime); return
                if path == "/api/catalog": self.send(200,{**CATALOG,"signals":SIGNALS}); return
                if path == "/api/vehicles": self.send(200,service.garage.vehicles()); return
                if path == "/api/assessments": self.send(200,service.garage.assessments()); return
                if path == "/api/measurements/template.csv": self.send(200,template_csv(),"text/csv; charset=utf-8","drivebench-readings-template.csv"); return
                assessment_match = ASSESSMENT_PATH.match(path)
                if assessment_match:
                    identifier, export = assessment_match.groups()
                    report = service.garage.assessment(identifier)
                    if report is None: self.send(404,{"error":"Assessment not found"}); return
                    if export == "report.txt":
                        from .reports import assessment_text
                        self.send(200,assessment_text(report),"text/plain; charset=utf-8",f"drivebench-assessment-{identifier}.txt"); return
                    self.send(200,report,filename=f"drivebench-assessment-{identifier}.json" if export else None); return
                if path == "/api/status": self.send(200,service.status()); return
                if path == "/api/scenarios": self.send(200,service.status()["scenarios"]); return
                if path == "/api/runs": self.send(200,service.store.history()); return
                match = RUN_PATH.match(path)
                if match:
                    identifier, export = match.groups(); run = service.store.get(identifier)
                    if run is None: self.send(404,{"error":"Run not found"}); return
                    if export and run["status"] == "running": self.send(409,{"error":"Wait for the run to finish before exporting"}); return
                    if export == "junit.xml": self.send(200,junit_xml(run),"application/xml",f"drivebench-{identifier}.xml"); return
                    self.send(200,run,filename=f"drivebench-{identifier}.json" if export else None); return
                self.send(404,{"error":"Route not found"})
            except Exception:
                logging.exception("Dashboard request failed"); self.send(500,{"error":"Internal error; check the server terminal"})

        def do_POST(self):
            if not self.boundary(mutation=True): return
            path = urlsplit(self.path).path
            if path not in {"/api/runs","/api/vehicles","/api/assessments"}: self.send(404,{"error":"Route not found"}); return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json": self.send(415,{"error":"Content-Type must be application/json"}); return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                limit = 1024 * 1024 if path == "/api/assessments" else 65536
                if size < 1 or size > limit: self.send(413,{"error":f"Body must be between 1 and {limit} bytes"}); return
                body = strict_json(self.rfile.read(size).decode("utf-8"))
                if path == "/api/vehicles": self.send(201,service.garage.add_vehicle(body)); return
                if path == "/api/assessments": self.send(201,service.garage.save_assessment(assess(body,service.garage))); return
                if not isinstance(body, dict) or set(body) != {"scenario"} or not isinstance(body["scenario"], str):
                    raise ValueError("Provide one scenario field")
                self.send(202,service.submit(body["scenario"]))
            except (ValueError, UnicodeError) as exc: self.send(400,{"error":str(exc) or "Invalid JSON or scenario"})
            except BusyError as exc: self.send(409,{"error":str(exc)})
            except Exception:
                logging.exception("Cannot start run"); self.send(500,{"error":"Cannot start run; check server terminal"})

    server = ThreadingHTTPServer(address, Handler)
    server.daemon_threads = False
    return server
