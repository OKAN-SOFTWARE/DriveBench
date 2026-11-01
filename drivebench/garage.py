"""Vehicle identities and immutable measurement reports, separate from simulator runs."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import uuid

from .protocol import utc_now

CATALOG = json.loads((Path(__file__).parent / "references" / "vehicles.json").read_text(encoding="utf-8"))
PROFILE_BY_ID = {profile["id"]: profile for profile in CATALOG["profiles"]}


def text_field(value, name, limit=80):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError(f"{name} must contain 1–{limit} printable characters")
    return value.strip()


def vehicle_from_request(body):
    if not isinstance(body, dict):
        raise ValueError("Vehicle must be a JSON object")
    profile_id = body.get("profile_id")
    if profile_id is not None and not isinstance(profile_id, str):
        raise ValueError("profile_id must be a string or null")
    if profile_id:
        if set(body) - {"profile_id", "nickname"} or not isinstance(profile_id, str) or profile_id not in PROFILE_BY_ID:
            raise ValueError("Choose a supported reference profile")
        vehicle = deepcopy(PROFILE_BY_ID[profile_id])
        vehicle.pop("id")
        vehicle["profile_id"] = profile_id
    else:
        allowed = {"profile_id", "nickname", "make", "year", "model", "engine", "powertrain", "market"}
        if set(body) - allowed:
            raise ValueError("Unknown vehicle field")
        year = body.get("year")
        if type(year) is not int or not 1886 <= year <= 2100:
            raise ValueError("Model year must be an integer between 1886 and 2100")
        powertrain = body.get("powertrain")
        if not isinstance(powertrain, str) or powertrain not in {"gasoline", "diesel", "hybrid", "electric", "other"}:
            raise ValueError("Choose a valid powertrain")
        vehicle = {key: text_field(body.get(key), key) for key in ["make", "model", "engine", "market"]}
        vehicle.update(year=year, powertrain=powertrain, profile_id=None, reference_id=None, source=None)
    vehicle["nickname"] = text_field(body.get("nickname"), "Nickname")
    vehicle.update(id=uuid.uuid4().hex, created_at=utc_now())
    return vehicle


class GarageStore:
    def __init__(self, run_store):
        self.connection, self.lock = run_store.connection, run_store.lock
        with self.lock, self.connection:
            self.connection.execute("CREATE TABLE IF NOT EXISTS vehicles (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL)")
            self.connection.execute("CREATE TABLE IF NOT EXISTS assessments (id TEXT PRIMARY KEY, vehicle_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)")

    def add_vehicle(self, body):
        vehicle = vehicle_from_request(body)
        with self.lock, self.connection:
            if self.connection.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] >= 100:
                raise ValueError("Garage limit is 100 saved vehicles")
            self.connection.execute("INSERT INTO vehicles VALUES(?,?,?)", (vehicle["id"], vehicle["created_at"], json.dumps(vehicle)))
        return vehicle

    def vehicles(self):
        with self.lock:
            rows = self.connection.execute("SELECT payload FROM vehicles ORDER BY created_at DESC").fetchall()
        return [json.loads(row[0]) for row in rows]

    def vehicle(self, identifier):
        with self.lock:
            row = self.connection.execute("SELECT payload FROM vehicles WHERE id=?", (identifier,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_assessment(self, report):
        payload = json.dumps(report, allow_nan=False)
        if len(payload.encode()) > 2 * 1024 * 1024:
            raise ValueError("Assessment exceeds the 2 MiB report limit")
        with self.lock, self.connection:
            self.connection.execute("INSERT INTO assessments VALUES(?,?,?,?)", (report["id"],report["vehicle"]["id"],report["created_at"],payload))
            self.connection.execute("DELETE FROM assessments WHERE id NOT IN (SELECT id FROM assessments ORDER BY created_at DESC LIMIT 100)")
        return report

    def assessments(self, vehicle_id=None):
        query, params = "SELECT payload FROM assessments", ()
        if vehicle_id:
            query += " WHERE vehicle_id=?"; params = (vehicle_id,)
        with self.lock:
            rows = self.connection.execute(query+" ORDER BY created_at DESC LIMIT 100", params).fetchall()
        return [{key: report[key] for key in ["id", "name", "created_at", "vehicle", "summary"]}
                for (payload,) in rows for report in [json.loads(payload)]]

    def assessment(self, identifier):
        with self.lock:
            row = self.connection.execute("SELECT payload FROM assessments WHERE id=?", (identifier,)).fetchone()
        return json.loads(row[0]) if row else None
