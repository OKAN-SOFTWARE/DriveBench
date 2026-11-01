import argparse
from contextlib import nullcontext
import json
from pathlib import Path
from .runtime import ROOT, JAR, SimulatorProcess, build_simulator
from .scenarios import SCENARIOS, run_suite
from .reports import write_reports
from .store import RunStore
from .service import LabService
from .web import make_server


def main(argv=None):
    parser = argparse.ArgumentParser(description="DriveBench virtual vehicle test lab")
    parser.add_argument("mode", nargs="?", choices=["serve", "run"], default="serve")
    parser.add_argument("--sim-host", default="127.0.0.1")
    parser.add_argument("--sim-port", type=int, default=0, help="0 launches a managed Java simulator")
    parser.add_argument("--no-build", action="store_true", help="require an existing simulator JAR")
    parser.add_argument("--port", type=int, default=8088, help="local dashboard port")
    parser.add_argument("--db", default=str(ROOT / "data" / "drivebench.db"))
    parser.add_argument("--scenario", default="all", choices=["all", *(s["id"] for s in SCENARIOS)])
    parser.add_argument("--report", default="reports/scenarios.json")
    parser.add_argument("--junit", default="reports/scenarios.xml")
    args = parser.parse_args(argv)
    if not 0 <= args.sim_port <= 65535 or not 0 <= args.port <= 65535: parser.error("Ports must be between 0 and 65535")
    if not args.sim_port and args.sim_host != "127.0.0.1": parser.error("A managed simulator runs on 127.0.0.1; provide --sim-port for an external simulator")
    if not args.sim_port and not args.no_build and (not JAR.is_file() or any(p.stat().st_mtime > JAR.stat().st_mtime for p in (ROOT/"simulator").rglob("*.java")) or (ROOT/"simulator/pom.xml").stat().st_mtime > JAR.stat().st_mtime):
        build_simulator()
    context = SimulatorProcess() if args.sim_port == 0 else nullcontext(None)
    with context as simulator:
        port = simulator.port if simulator else args.sim_port
        if args.mode == "run":
            result = run_suite(args.sim_host, port, args.scenario)
            write_reports(result, args.report, args.junit)
            print(json.dumps({k: result[k] for k in ["id","status","passed","failed","duration_ms"]}, indent=2))
            return 0 if result["status"] == "passed" else 1
        store = RunStore(args.db)
        service = LabService(store, args.sim_host, port)
        server = make_server(("127.0.0.1", args.port), service)
        print(f"\nDriveBench 0.1.0\nDashboard: http://127.0.0.1:{server.server_port}\nSimulator TCP: {args.sim_host}:{port}\nSimulation only · Press Ctrl+C to stop.\n", flush=True)
        try: server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt: pass
        finally: server.server_close(); service.close(); store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
