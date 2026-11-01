from contextlib import contextmanager
import json
import socket
import threading
import time
import pytest
from drivebench.protocol import DiagnosticClient, ProtocolError, ConnectionLost, TransportTimeout, strict_json


@contextmanager
def peer(response):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0)); listener.listen(); listener.settimeout(2)
        errors = []
        def serve():
            try:
                with listener.accept()[0] as connection:
                    connection.settimeout(2)
                    request = bytearray()
                    while b'\n' not in request: request.extend(connection.recv(4096))
                    response(connection, json.loads(request))
            except (BrokenPipeError, ConnectionResetError): pass
            except Exception as exc: errors.append(exc)
        worker = threading.Thread(target=serve); worker.start()
        try: yield listener.getsockname()[1]
        finally:
            worker.join(3)
            assert not worker.is_alive()
            assert not errors, errors


def test_fragmented_response_is_reassembled_and_correlated():
    def respond(connection, request):
        data = json.dumps({"id":request["id"],"ok":True,"data":{"temperature_c":85}}).encode()+b'\n'
        for offset in range(0, len(data), 5): connection.sendall(data[offset:offset+5])
    with peer(respond) as port, DiagnosticClient("127.0.0.1",port) as client:
        assert client.request("read") == {"temperature_c":85}


@pytest.mark.parametrize("kind", ["mismatch", "invalid_json", "duplicate", "oversized", "non_object"])
def test_bad_response_invalidates_session(kind):
    def respond(connection, request):
        data = {"mismatch":b'{"id":"wrong","ok":true,"data":{}}\n',"invalid_json":b'garbage\n',
                "duplicate":b'{"id":"x","id":"y"}\n',"oversized":b'x'*65537,"non_object":b'[]\n'}[kind]
        connection.sendall(data)
    with peer(respond) as port, DiagnosticClient("127.0.0.1",port) as client:
        with pytest.raises(ProtocolError): client.request("read")
        assert client._socket is None


@pytest.mark.parametrize("kind,error", [("timeout",TransportTimeout),("close",ConnectionLost)])
def test_transport_failure_is_explicit_and_session_closed(kind,error):
    def respond(connection, request):
        if kind == "timeout": time.sleep(.15)
    with peer(respond) as port, DiagnosticClient("127.0.0.1",port,timeout=.05) as client:
        with pytest.raises(error): client.request("read")
        assert client._socket is None


@pytest.mark.parametrize("value", ['{"x":1,"x":2}', '{"x":NaN}', '{} {}'])
def test_strict_json_rejects_ambiguous_or_nonstandard_frames(value):
    with pytest.raises(ValueError): strict_json(value)
