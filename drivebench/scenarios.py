from __future__ import annotations
import time
import uuid
from .protocol import DiagnosticClient, RemoteError, TransportTimeout, ConnectionLost, utc_now

SCENARIOS = [
    {"id": "baseline", "name": "Nominal operation", "subsystem": "Vehicle state", "description": "Validate ignition, nominal telemetry, and clean diagnostics."},
    {"id": "overheat", "name": "Thermal fault lifecycle", "subsystem": "Thermal controller", "description": "Inject heat, verify hysteresis and latched faults, then recover."},
    {"id": "low_voltage", "name": "Battery undervoltage", "subsystem": "Battery controller", "description": "Verify low-voltage detection, recovery threshold, and clearing."},
    {"id": "timeout_recovery", "name": "Timeout & reconnect", "subsystem": "TCP transport", "description": "Delay a response, assert the deadline, and recover on a new session."},
    {"id": "disconnect_recovery", "name": "Connection loss", "subsystem": "TCP transport", "description": "Drop a connection and verify controlled reconnection."},
    {"id": "invalid_input", "name": "Input validation", "subsystem": "Protocol contract", "description": "Reject invalid values and commands without corrupting state."},
]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class Harness:
    def __init__(self, host, port, result):
        self.host, self.port, self.result = host, port, result
        self.client = self.make_client()

    def make_client(self, timeout=0.8):
        return DiagnosticClient(self.host, self.port, timeout, self.result["trace"].append)

    def reconnect(self, timeout=0.8):
        self.client.close()
        self.client = self.make_client(timeout)
        return self.client.request("read")

    def step(self, name, operation):
        started = time.perf_counter()
        entry = {"name": name, "status": "passed", "started_at": utc_now()}
        try:
            value = operation()
            if isinstance(value, dict):
                entry["observed"] = value
            return value
        except Exception as exc:
            entry["status"] = "failed"
            entry["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            entry["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
            self.result["steps"].append(entry)

    def expect_error(self, command, error_type, code=None, **fields):
        try:
            self.client.request(command, **fields)
        except error_type as exc:
            if code is not None:
                require(getattr(exc, "code", None) == code, f"Expected {code}, received {exc}")
            return {"expected_error": type(exc).__name__, "message": str(exc)}
        raise AssertionError(f"Expected {error_type.__name__}; command unexpectedly succeeded")

    def begin(self):
        self.step("Reset to an isolated baseline", lambda: self.client.request("reset"))
        return self.step("Enable simulated ignition", lambda: self.client.request("ignition", on=True))


class ScenarioRunner:
    def __init__(self, host="127.0.0.1", port=7071):
        self.host, self.port = host, port

    def run(self, scenario_id):
        definition = next((s for s in SCENARIOS if s["id"] == scenario_id), None)
        if definition is None:
            raise ValueError("Unknown scenario")
        result = {"id": uuid.uuid4().hex, "scenario": scenario_id, "name": definition["name"],
                  "status": "running", "started_at": utc_now(), "steps": [], "trace": []}
        harness = Harness(self.host, self.port, result)
        started = time.perf_counter()
        try:
            harness.begin()
            getattr(self, "_" + scenario_id)(harness)
            result["status"] = "passed"
        except Exception as exc:
            result["status"] = "failed"
            result["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            harness.client.close()
            result["finished_at"] = utc_now()
            result["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
            result["passed"] = sum(s["status"] == "passed" for s in result["steps"])
            result["failed"] = sum(s["status"] == "failed" for s in result["steps"])
        return result

    def _baseline(self, h):
        def verify():
            state = h.client.request("read")
            require(state["ignition"] is True, "Ignition must be on")
            require(state["sensors"] == {"temperature_c": 85.0, "battery_v": 12.6, "speed_kph": 0.0}, "Nominal readings differ")
            require(state["active_faults"] == [] and state["stored_faults"] == [], "Baseline diagnostics must be empty")
            return state
        h.step("Assert nominal telemetry and clean diagnostics", verify)
        h.step("Set simulated vehicle speed", lambda: h.client.request("set_sensor", sensor="speed_kph", value=42))
        def speed():
            state = h.client.request("read"); require(state["sensors"]["speed_kph"] == 42, "Speed did not propagate"); return state
        h.step("Verify the speed update crossed the Java/Python boundary", speed)

    def _overheat(self, h):
        h.step("Inject 110 °C temperature", lambda: h.client.request("set_sensor", sensor="temperature_c", value=110))
        def active():
            state = h.client.request("diagnostics")
            require("DB_TEMP_HIGH" in state["active_faults"], "Thermal diagnostic missing"); return state
        h.step("Verify active thermal diagnostic", active)
        h.step("Reject clearing while fault is active", lambda: h.expect_error("clear_faults", RemoteError, "ACTIVE_FAULT"))
        h.step("Lower temperature into hysteresis band", lambda: h.client.request("set_sensor", sensor="temperature_c", value=103))
        h.step("Verify fault stays active at 103 °C", active)
        h.step("Recover to 98 °C", lambda: h.client.request("set_sensor", sensor="temperature_c", value=98))
        def recovered():
            state = h.client.request("diagnostics")
            require(state["active_faults"] == [] and "DB_TEMP_HIGH" in state["stored_faults"], "Recovery must retain stored diagnostic"); return state
        h.step("Verify active fault clears but stored code remains", recovered)
        def clear():
            state = h.client.request("clear_faults"); require(state["stored_faults"] == [], "Stored code did not clear"); return state
        h.step("Clear stored thermal diagnostic after recovery", clear)

    def _low_voltage(self, h):
        h.step("Inject 10.5 V battery voltage", lambda: h.client.request("set_sensor", sensor="battery_v", value=10.5))
        def active():
            state = h.client.request("diagnostics"); require("DB_VOLT_LOW" in state["active_faults"], "Undervoltage diagnostic missing"); return state
        h.step("Verify battery undervoltage diagnostic", active)
        h.step("Set 11.8 V hysteresis band", lambda: h.client.request("set_sensor", sensor="battery_v", value=11.8))
        h.step("Verify diagnostic remains below recovery threshold", active)
        h.step("Restore 12.6 V", lambda: h.client.request("set_sensor", sensor="battery_v", value=12.6))
        def clear():
            state = h.client.request("diagnostics")
            require(state["active_faults"] == [] and "DB_VOLT_LOW" in state["stored_faults"], "Battery recovery diagnostic state incorrect")
            state = h.client.request("clear_faults"); require(not state["stored_faults"], "Battery fault did not clear"); return state
        h.step("Verify recovery and clear stored diagnostic", clear)

    def _timeout_recovery(self, h):
        h.step("Arm a one-shot 600 ms response delay", lambda: h.client.request("inject_transport", mode="delay", delay_ms=600))
        h.client.timeout = 0.15
        h.step("Assert a 150 ms response deadline", lambda: h.expect_error("read", TransportTimeout))
        def recover():
            state = h.reconnect(); require(state["ignition"] is True, "Vehicle state was lost after reconnect"); return state
        h.step("Reconnect with a fresh socket and verify a correlated response", recover)

    def _disconnect_recovery(self, h):
        h.step("Arm a one-shot connection drop", lambda: h.client.request("inject_transport", mode="disconnect"))
        h.step("Detect connection loss without a false success", lambda: h.expect_error("read", ConnectionLost))
        def recover():
            state = h.reconnect(); require(state["ignition"] is True, "Vehicle state was lost"); return state
        h.step("Reconnect and read current vehicle state", recover)

    def _invalid_input(self, h):
        h.step("Reject an out-of-range temperature", lambda: h.expect_error("set_sensor", RemoteError, "INVALID_VALUE", sensor="temperature_c", value=500))
        def unchanged():
            state = h.client.request("read"); require(state["sensors"]["temperature_c"] == 85, "Rejected input changed sensor state"); return state
        h.step("Prove invalid input did not mutate state", unchanged)
        h.step("Reject an unknown command", lambda: h.expect_error("not_a_command", RemoteError, "INVALID_COMMAND"))
        h.step("Verify the same connection is still usable", unchanged)


def run_suite(host, port, scenario="all", progress=None):
    if scenario not in {"all", *(s["id"] for s in SCENARIOS)}:
        raise ValueError("Unknown scenario")
    ids = [s["id"] for s in SCENARIOS] if scenario == "all" else [scenario]
    runner = ScenarioRunner(host, port)
    started = time.perf_counter()
    result = {"id": uuid.uuid4().hex, "scenario": scenario, "name": "Full regression suite" if scenario == "all" else next(s["name"] for s in SCENARIOS if s["id"] == scenario),
              "status": "running", "started_at": utc_now(), "results": []}
    for scenario_id in ids:
        result["current_scenario"] = next(s["name"] for s in SCENARIOS if s["id"] == scenario_id)
        if progress: progress(result)
        result["results"].append(runner.run(scenario_id))
        result["passed"] = sum(r["passed"] for r in result["results"])
        result["failed"] = sum(r["failed"] for r in result["results"])
        if progress: progress(result)
    result["status"] = "passed" if all(r["status"] == "passed" for r in result["results"]) else "failed"
    result["passed"] = sum(r["passed"] for r in result["results"])
    result["failed"] = sum(r["failed"] for r in result["results"])
    result["finished_at"] = utc_now()
    result.pop("current_scenario", None)
    result["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return result
