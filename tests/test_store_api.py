import http.client
import json
import threading
import time
import uuid
import xml.etree.ElementTree as ET
import pytest
from drivebench.store import RunStore
from drivebench.service import LabService, BusyError
from drivebench.web import make_server
from drivebench.reports import junit_xml


def test_store_restart_marks_abandoned_run_interrupted(tmp_path):
    path = tmp_path/"runs.db"; identifier = uuid.uuid4().hex
    store = RunStore(path)
    store.save({"id":identifier,"status":"running","started_at":"2026-01-01T00:00:00Z","results":[]})
    store.close(); store = RunStore(path)
    try:
        assert store.get(identifier)["status"] == "interrupted"
        assert "stopped" in store.get(identifier)["error"]
    finally: store.close()


def test_store_retains_latest_fifty_completed_runs(tmp_path):
    store = RunStore(tmp_path/"runs.db")
    try:
        for index in range(55):
            store.save({"id":str(index),"status":"passed","started_at":f"2026-01-01T00:00:{index:02d}Z"})
        assert len(store.history()) == 50
        assert store.get("0") is None and store.get("54")["status"] == "passed"
        store.save({"id":"active","status":"running","started_at":"2026-01-02T00:00:00Z"})
        assert store.get("5") is not None  # An active run does not evict a completed report.
    finally: store.close()


@pytest.fixture
def lab(simulator, tmp_path):
    store = RunStore(tmp_path/"runs.db"); service = LabService(store,"127.0.0.1",simulator.port)
    server = make_server(("127.0.0.1",0),service)
    thread = threading.Thread(target=server.serve_forever); thread.start()
    try: yield server, service
    finally:
        server.shutdown(); thread.join(3); server.server_close(); service.close(); store.close()


def request(server, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=3)
    try:
        connection.request(method,path,body=body,headers=headers or {})
        response = connection.getresponse(); data = response.read()
        return response.status, dict(response.getheaders()), data
    finally: connection.close()


def test_dashboard_executes_persists_and_exports_real_simulator_run(lab):
    server, service = lab
    status, headers, body = request(server,"GET","/")
    assert status == 200 and b"DriveBench" in body
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    for asset in ["/app.js","/style.css"]: assert request(server,"GET",asset)[0] == 200
    status, _, body = request(server,"POST","/api/runs",'{"scenario":"all"}',{"Content-Type":"application/json","X-DriveBench":"1"})
    assert status == 202; identifier = json.loads(body)["id"]
    deadline = time.monotonic()+8
    while time.monotonic()<deadline:
        status, _, body = request(server,"GET",f"/api/runs/{identifier}")
        result = json.loads(body)
        if result["status"] != "running": break
        time.sleep(.03)
    assert result["status"] == "passed", result
    history = json.loads(request(server,"GET","/api/runs")[2])
    assert history[0]["id"] == identifier
    status, headers, body = request(server,"GET",f"/api/runs/{identifier}/export.json")
    assert status == 200 and json.loads(body)["id"] == identifier
    assert "attachment" in headers["Content-Disposition"]
    status, _, body = request(server,"GET",f"/api/runs/{identifier}/junit.xml")
    assert status == 200 and ET.fromstring(body).attrib["tests"] == "6"
    assert request(server,"GET","/api/status")[0] == 200


@pytest.mark.parametrize("headers,expected", [({},403),({"X-DriveBench":"1","Origin":"https://evil.example"},403),({"X-DriveBench":"1","Origin":"http://[invalid"},403),({"X-DriveBench":"1","Sec-Fetch-Site":"cross-site"},403),({"X-DriveBench":"1","Host":"evil.example"},403)])
def test_api_rejects_untrusted_mutation(lab, headers, expected):
    assert request(lab[0],"POST","/api/runs",'{"scenario":"all"}',{"Content-Type":"application/json",**headers})[0] == expected


@pytest.mark.parametrize("body", ['{"scenario":"unknown"}','{"scenario":"all","extra":1}','{"scenario":"all","scenario":"baseline"}','null'])
def test_api_rejects_invalid_input(lab,body):
    assert request(lab[0],"POST","/api/runs",body,{"Content-Type":"application/json","X-DriveBench":"1"})[0] == 400


def test_service_serializes_runs_and_recovers_when_simulator_offline(tmp_path):
    import socket
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1",0)); port=reserved.getsockname()[1]
    store=RunStore(tmp_path/"offline.db"); service=LabService(store,"127.0.0.1",port)
    try:
        with service.lock:
            service.active_id="occupied"
        with pytest.raises(BusyError): service.submit("all")
        with service.lock: service.active_id=None
        initial=service.submit("baseline"); service.executor.shutdown(wait=True)
        result=store.get(initial["id"])
        assert result["status"] == "failed"
        assert ET.fromstring(junit_xml(result)).attrib["failures"] == "1"
        assert service.status()["simulator"]["connected"] is False
    finally: service.close(); store.close()
