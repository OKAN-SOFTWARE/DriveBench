from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import threading
import uuid
from .protocol import DiagnosticClient, ClientError, utc_now
from .scenarios import SCENARIOS, run_suite
from .garage import GarageStore
from . import __version__


class BusyError(Exception):
    pass


class LabService:
    def __init__(self, store, host, port, simulation_enabled=True):
        self.store, self.host, self.port = store, host, port
        self.garage = GarageStore(store)
        self.simulation_enabled = simulation_enabled
        self.lock = threading.Lock()
        self.active_id = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="drivebench-runner")
        self.closed = False

    def submit(self, scenario):
        if not self.simulation_enabled:
            raise BusyError("Simulation lab is disabled. Restart without --garage-only to enable Java scenarios.")
        if scenario not in {"all", *(s["id"] for s in SCENARIOS)}:
            raise ValueError("Unknown scenario")
        with self.lock:
            if self.closed or self.active_id:
                raise BusyError("A test run is already active")
            identifier = uuid.uuid4().hex
            definition = next((s for s in SCENARIOS if s["id"] == scenario), None)
            initial = {"id":identifier,"scenario":scenario,"name":definition["name"] if definition else "Full regression suite",
                       "status":"running","started_at":utc_now(),"results":[],"passed":0,"failed":0}
            self.store.save(initial)
            self.active_id = identifier
            self.executor.submit(self._execute, identifier, scenario, initial)
        return initial

    def _execute(self, identifier, scenario, initial):
        def save_progress(run):
            run["id"] = identifier
            self.store.save(run)
        try:
            result = run_suite(self.host, self.port, scenario, save_progress)
            result["id"] = identifier
            self.store.save(result)
        except Exception as exc:
            initial.update(status="failed",finished_at=utc_now(),error=f"{type(exc).__name__}: {exc}")
            self.store.save(initial)
        finally:
            with self.lock: self.active_id = None

    def status(self):
        with self.lock: active = self.active_id
        try:
            if not self.simulation_enabled: raise ClientError("Simulation not started in garage-only mode")
            with DiagnosticClient(self.host, self.port, timeout=0.35) as client:
                telemetry = client.request("read")
            simulator = {"connected":True,"telemetry":telemetry}
        except ClientError as exc:
            simulator = {"connected":False,"error":str(exc),"telemetry":None}
        history = self.store.history()
        return {"version":__version__,"scenarios":SCENARIOS,"active_id":active,"history":history,
                "simulator":{**simulator,"enabled":self.simulation_enabled,"endpoint":f"{self.host}:{self.port}" if self.simulation_enabled else "Garage only","protocol":"Custom TCP/IP · JSON lines"},
                "summary":{"retained_runs":len(history),"passed":sum(r["status"]=="passed" for r in history),
                           "failed":sum(r["status"] in {"failed","interrupted"} for r in history)}}

    def close(self):
        with self.lock: self.closed = True
        self.executor.shutdown(wait=True)
