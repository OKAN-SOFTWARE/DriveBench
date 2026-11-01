"""Strict measurement import and source-backed, condition-aware reference comparisons."""
from __future__ import annotations

from copy import deepcopy
import csv
from datetime import datetime, timezone
from decimal import Decimal
import io
import math
import uuid

from .garage import CATALOG, PROFILE_BY_ID, text_field
from .protocol import utc_now
from . import __version__

SIGNALS = {
    "battery_v": {"name":"Battery terminal voltage", "units":["V"], "unit":"V"},
    "temperature_c": {"name":"Coolant temperature", "units":["C", "F"], "unit":"C"},
    "rpm": {"name":"Engine speed", "units":["rpm"], "unit":"rpm"},
    "speed_kph": {"name":"Vehicle speed", "units":["km/h", "mph"], "unit":"km/h"},
}
FIELDS = {"at", "signal", "value", "unit", "condition", "ambient_c", "rest_minutes", "lights_off", "measurement_source"}
CSV_COLUMNS = ["at", "signal", "value", "unit", "condition", "ambient_c", "rest_minutes", "lights_off", "measurement_source"]
MAX_READINGS = 500


def number(value, name):
    try: valid = type(value) in {int, float} and math.isfinite(value)
    except OverflowError: valid = False
    if not valid:
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def normalize_reading(body):
    if not isinstance(body, dict) or set(body) - FIELDS:
        raise ValueError("Unknown reading fields")
    signal = body.get("signal")
    if not isinstance(signal, str) or signal not in SIGNALS:
        raise ValueError("Unsupported signal")
    at = body.get("at")
    if not isinstance(at, str) or len(at) > 40:
        raise ValueError("Timestamp must be ISO 8601 with a timezone")
    try:
        moment = datetime.fromisoformat(at.replace("Z", "+00:00"))
        if moment.utcoffset() is None: raise ValueError()
    except ValueError:
        raise ValueError("Timestamp must be ISO 8601 with a timezone") from None
    unit = body.get("unit")
    if unit not in SIGNALS[signal]["units"]:
        raise ValueError(f"Expected units: {', '.join(SIGNALS[signal]['units'])}")
    value = body.get("value")
    if value is not None:
        value = number(value, "Reading")
        if unit == "F": value = (value - 32) * 5 / 9
        elif unit == "mph": value *= 1.609344
        if signal in {"battery_v", "rpm", "speed_kph"} and value < 0:
            raise ValueError("Voltage, speed, and RPM cannot be negative")
        if signal == "temperature_c" and value < -273.15:
            raise ValueError("Temperature is below absolute zero")
        if not math.isfinite(value): raise ValueError("Converted reading is not finite")
    condition = body.get("condition", "unknown")
    if not isinstance(condition, str) or condition not in {"resting", "idle", "driving", "unknown"}:
        raise ValueError("Unknown operating condition")
    source = body.get("measurement_source", "unknown")
    if not isinstance(source, str) or source not in {"battery_terminals", "obd", "unknown"}:
        raise ValueError("Unknown measurement source")
    ambient = body.get("ambient_c")
    if ambient is not None:
        ambient = number(ambient, "Ambient temperature")
        if ambient < -273.15: raise ValueError("Ambient temperature is below absolute zero")
    rest = body.get("rest_minutes")
    if rest is not None:
        rest = number(rest, "Rest duration")
        if rest < 0: raise ValueError("Rest duration cannot be negative")
    lights = body.get("lights_off")
    if lights is not None and type(lights) is not bool:
        raise ValueError("lights_off must be true, false, or null")
    return {"at":moment.astimezone(timezone.utc).isoformat().replace("+00:00","Z"), "signal":signal,
            "value":value, "unit":SIGNALS[signal]["unit"], "original_value":body.get("value"), "original_unit":unit,
            "condition":condition, "ambient_c":ambient, "rest_minutes":rest, "lights_off":lights, "measurement_source":source}


def parse_csv(text):
    if not isinstance(text, str) or len(text.encode("utf-8")) > 512 * 1024:
        raise ValueError("CSV must contain at most 512 KiB of UTF-8 text")
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff"), newline=""), strict=True)
    try: headers = reader.fieldnames
    except csv.Error as exc: raise ValueError(f"Malformed CSV: {exc}") from None
    if not headers or len(headers) != len(set(headers)):
        raise ValueError("CSV needs unique column names")
    if set(reader.fieldnames) - FIELDS or not {"at","signal","value","unit"} <= set(reader.fieldnames):
        raise ValueError("CSV requires at,signal,value,unit; use the downloadable template for optional columns")
    readings = []
    try:
        for index, row in enumerate(reader, start=2):
            if len(readings) >= MAX_READINGS: raise ValueError("Maximum 500 readings per assessment")
            if None in row or any(v is None for v in row.values()): raise ValueError(f"CSV row {index}: wrong number of columns")
            fields = {k:v.strip() for k,v in row.items()}
            for key in ["value", "ambient_c", "rest_minutes"]:
                if key in fields:
                    try: fields[key] = float(fields[key]) if fields[key] else None
                    except ValueError: raise ValueError(f"CSV row {index}: {key} must be a number") from None
            if "lights_off" in fields:
                if fields["lights_off"] not in {"true", "false", ""}: raise ValueError(f"CSV row {index}: lights_off must be true or false")
                fields["lights_off"] = {"true":True,"false":False,"":None}[fields["lights_off"]]
            for key in ["condition", "measurement_source"]:
                if key in fields and not fields[key]: fields[key] = "unknown"
            try: readings.append(normalize_reading(fields))
            except ValueError as exc: raise ValueError(f"CSV row {index}: {exc}") from None
    except csv.Error as exc:
        raise ValueError(f"Malformed CSV: {exc}") from None
    if not readings: raise ValueError("Provide at least one reading")
    return readings


def evaluate_reading(reading, vehicle):
    result = {**reading, "status":"reference_unavailable", "label":"Reference unavailable", "flagged":False,
              "explanation":"No reviewed specification for this vehicle and signal is included. This reading is not classified as healthy or faulty.",
              "reference":None, "source":None, "unmet_conditions":[]}
    # Resolve rules from the bundled catalog, never from client-submitted profile/rule fields.
    profile = PROFILE_BY_ID.get(vehicle.get("profile_id"))
    if profile and reading["signal"] == "battery_v":
        reference = deepcopy(CATALOG["references"][profile["reference_id"]])
        result.update(reference=reference, source=deepcopy(profile["source"]))
    if reading["value"] is None:
        result.update(status="missing", label="Missing reading", explanation="No measurement was supplied. A missing value cannot establish normal operation.")
        return result
    if result["reference"] is None: return result
    checks = [(reading["condition"] == "resting", "Engine off / resting"),
              (reading["ambient_c"] == 20, "Ambient temperature 20 °C (68 °F)"),
              (reading["rest_minutes"] == 20, "Measurement taken 20 minutes after switch-off"),
              (reading["lights_off"] is True, "All lights switched off"),
              (reading["measurement_source"] == "battery_terminals", "Battery-terminal voltmeter measurement")]
    unmet = [label for valid,label in checks if not valid]
    if unmet:
        result.update(status="conditions_not_met", label="Conditions not met", unmet_conditions=unmet,
                      explanation="The published resting-battery reference does not apply to these measurement conditions. No voltage classification was made.")
        return result
    value = Decimal(str(reading["value"]))
    for band in result["reference"]["bands"]:
        if Decimal(str(band["min"])) <= value <= Decimal(str(band["max"])):
            result.update(status="reference_match", label=band["label"], flagged=band["flagged"],
                          explanation=f"{reading['value']:g} V falls within the published {band['min']}–{band['max']} V band under the stated conditions. This does not determine battery health.")
            return result
    result.update(status="unclassified", label="Outside published bands", flagged=True,
                  explanation="The value is outside the manual's discrete reference bands. DriveBench does not interpolate charge percentage, diagnose a failed component, or extrapolate a threshold.")
    return result


def assess(body, garage):
    if not isinstance(body, dict) or set(body) - {"vehicle_id", "name", "readings", "csv"}:
        raise ValueError("Unknown assessment fields")
    identifier = body.get("vehicle_id")
    if not isinstance(identifier, str): raise ValueError("Choose a saved vehicle")
    vehicle = garage.vehicle(identifier)
    if not vehicle: raise ValueError("Saved vehicle not found")
    name = text_field(body.get("name"), "Assessment name", 100)
    if ("csv" in body) == ("readings" in body): raise ValueError("Provide either readings or CSV, not both")
    if "csv" in body:
        readings = parse_csv(body["csv"]); origin="csv"
    else:
        raw = body["readings"]
        if not isinstance(raw,list) or not 1 <= len(raw) <= MAX_READINGS: raise ValueError("Provide 1–500 readings")
        readings = [normalize_reading(row) for row in raw]; origin="manual"
    readings.sort(key=lambda row:datetime.fromisoformat(row["at"].replace("Z","+00:00")))
    results = [evaluate_reading(row,vehicle) for row in readings]
    summary = {"readings":len(results), "flagged":sum(row["flagged"] for row in results),
               "compared":sum(row["status"] in {"reference_match","unclassified"} for row in results),
               "unavailable":sum(row["status"] == "reference_unavailable" for row in results),
               "conditions_not_met":sum(row["status"] == "conditions_not_met" for row in results),
               "missing":sum(row["status"] == "missing" for row in results)}
    return {"id":uuid.uuid4().hex, "name":name, "created_at":utc_now(), "origin":origin, "app_version":__version__,
            "catalog_version":CATALOG["version"], "vehicle":deepcopy(vehicle), "summary":summary, "readings":results,
            "scope":"Reference comparison only. No overall vehicle-health verdict. Simulator thresholds are never used for real vehicle measurements."}


def template_csv():
    output=io.StringIO(newline=""); writer=csv.writer(output); writer.writerow(CSV_COLUMNS)
    writer.writerow(["2026-10-31T13:00:00-04:00","battery_v",12.7,"V","resting",20,20,"true","battery_terminals"])
    writer.writerow(["2026-10-31T13:01:00-04:00","temperature_c",85,"C","idle","","","","obd"])
    return output.getvalue().encode("utf-8")
