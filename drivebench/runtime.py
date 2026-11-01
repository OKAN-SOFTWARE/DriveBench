from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading

ROOT = Path(__file__).resolve().parent.parent
JAR = ROOT / "simulator" / "target" / "drivebench-simulator.jar"


def build_simulator():
    maven = shutil.which("mvn") or shutil.which("mvn.cmd")
    if not maven:
        raise RuntimeError("Maven is required for the first build. Install Maven 3.9+ and reopen the terminal.")
    subprocess.run([maven, "-B", "-f", str(ROOT / "simulator" / "pom.xml"), "verify"], check=True)


class SimulatorProcess:
    def __init__(self, jar=JAR, port=0):
        self.jar, self.port, self.process = Path(jar), port, None

    def start(self):
        java = shutil.which("java")
        if not java:
            raise RuntimeError("Java 17+ is required. Install a JDK and reopen the terminal.")
        if not self.jar.is_file():
            raise RuntimeError("Simulator JAR is missing. Run: mvn -f simulator/pom.xml verify")
        self.process = subprocess.Popen([java, "-jar", str(self.jar), "--port", str(self.port)], stdout=subprocess.PIPE, text=True)
        ready = queue.Queue()
        def read_ready():
            try: ready.put(self.process.stdout.readline())
            except Exception as exc: ready.put(exc)
        threading.Thread(target=read_ready, daemon=True).start()
        try:
            line = ready.get(timeout=15)
            if isinstance(line, Exception): raise line
            data = json.loads(line)
            if data.get("ready") is not True or not isinstance(data.get("port"), int):
                raise RuntimeError("Invalid simulator startup response")
            self.port = data["port"]
            return self
        except Exception as exc:
            self.close()
            raise RuntimeError("Java simulator failed to become ready") from exc

    def close(self):
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try: self.process.wait(timeout=5)
                except subprocess.TimeoutExpired: self.process.kill(); self.process.wait(timeout=5)
            if self.process.stdout: self.process.stdout.close()
            self.process = None

    def __enter__(self): return self.start()
    def __exit__(self, *_): self.close()
