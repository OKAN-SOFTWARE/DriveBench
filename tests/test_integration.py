import json
import socket
import xml.etree.ElementTree as ET
from drivebench.protocol import DiagnosticClient, RemoteError
from drivebench.reports import junit_xml, write_reports
from drivebench.scenarios import run_suite
import pytest


def test_complete_java_python_regression_and_reports(simulator, tmp_path):
    result = run_suite("127.0.0.1", simulator.port)
    assert result["status"] == "passed", json.dumps(result, indent=2)
    assert len(result["results"]) == 6
    assert result["passed"] >= 35 and result["failed"] == 0
    for case in result["results"]:
        tx = {t["request_id"] for t in case["trace"] if t["direction"] == "TX"}
        assert tx
        assert all(t["request_id"] in tx for t in case["trace"])
    timeout = next(r for r in result["results"] if r["scenario"] == "timeout_recovery")
    assert any(t["payload"].get("type") == "TransportTimeout" for t in timeout["trace"])
    write_reports(result, tmp_path/"run.json", tmp_path/"run.xml")
    assert json.loads((tmp_path/"run.json").read_text())["status"] == "passed"
    xml = ET.parse(tmp_path/"run.xml").getroot()
    assert xml.attrib["tests"] == "6" and xml.attrib["failures"] == "0"
    assert len(xml.findall("testcase/system-out")) == 6


def test_remote_rejection_preserves_connection_and_state(simulator):
    with DiagnosticClient("127.0.0.1", simulator.port) as client:
        client.request("reset")
        with pytest.raises(RemoteError, match="INVALID_VALUE"):
            client.request("set_sensor", sensor="battery_v", value=99)
        assert client.request("read")["sensors"]["battery_v"] == 12.6


def test_transport_injection_does_not_affect_other_sessions(simulator):
    with DiagnosticClient("127.0.0.1", simulator.port) as a, DiagnosticClient("127.0.0.1", simulator.port) as b:
        a.request("inject_transport", mode="disconnect")
        assert "sensors" in b.request("read")


@pytest.mark.parametrize("frame", [b'{"id":"x","id":"y","command":"read"}\n', b'{} {}\n', b'NaN\n'])
def test_java_rejects_invalid_json_and_session_remains_usable(simulator, frame):
    with socket.create_connection(("127.0.0.1", simulator.port), timeout=2) as connection:
        connection.sendall(frame + b'{"id":"after","command":"read"}\n')
        with connection.makefile("rb") as stream:
            assert json.loads(stream.readline())["error"]["code"] == "INVALID_JSON"
            assert json.loads(stream.readline())["id"] == "after"


def test_oversized_java_request_is_disconnected(simulator):
    with socket.create_connection(("127.0.0.1", simulator.port), timeout=2) as connection:
        connection.sendall(b'x'*8193+b'\n')
        try: assert connection.recv(1) == b''
        except ConnectionResetError: pass


def test_report_marks_failed_scenario():
    run = {"status":"failed","results":[{"scenario":"broken", "status":"failed", "error":"expected < actual", "steps":[], "trace":[]}], "duration_ms":100}
    root = ET.fromstring(junit_xml(run))
    assert root.attrib["failures"] == "1"
    assert root.find("testcase/failure").attrib["message"] == "expected < actual"


def test_interrupted_export_cannot_look_like_a_passing_suite():
    root = ET.fromstring(junit_xml({"status":"interrupted","results":[],"error":"Application stopped"}))
    assert root.attrib["tests"] == "1" and root.attrib["failures"] == "1"
    assert root.find("testcase/failure").attrib["message"] == "Application stopped"
