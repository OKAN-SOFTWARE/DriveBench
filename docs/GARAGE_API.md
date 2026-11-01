# Garage and measurement API (v0.2)

The existing loopback Host/Origin checks and `X-DriveBench: 1` mutation header also apply to these routes. Requests/responses use JSON unless stated otherwise.

| Method | Route | Result |
| --- | --- | --- |
| GET | `/api/catalog` | Reviewed vehicle profiles, reference definitions, signal/unit catalog, catalog version |
| GET | `/api/vehicles` | Saved vehicles, newest first |
| POST | `/api/vehicles` | Add a vehicle; 201 |
| GET | `/api/assessments` | Latest 100 report summaries, newest first |
| POST | `/api/assessments` | Validate, compare, and atomically save a session; 201 |
| GET | `/api/assessments/{id}` | Immutable full report |
| GET | `/api/assessments/{id}/export.json` | Download report as JSON |
| GET | `/api/assessments/{id}/report.txt` | Download a readable report with sources |
| GET | `/api/measurements/template.csv` | Download CSV header and example rows |

Create a reviewed-profile vehicle:

```json
{"profile_id":"toyota-corolla-im-2017-us","nickname":"My Corolla"}
```

Or create a custom vehicle (no bundled limits):

```json
{"nickname":"My car","make":"Kia","year":2025,"model":"Sportage","engine":"Unknown","powertrain":"gasoline","market":"US"}
```

Preset identity/source fields cannot be overridden. Custom powertrain choices: `gasoline`, `diesel`, `hybrid`, `electric`, `other`. Names are bounded printable strings; year is an integer from 1886–2100. Up to 100 vehicle records can be saved.

Submit a manual reading:

```json
{
  "vehicle_id":"<saved vehicle id>",
  "name":"Battery reference check",
  "readings":[{
    "at":"2026-10-31T13:00:00-04:00",
    "signal":"battery_v","value":12.7,"unit":"V",
    "condition":"resting","ambient_c":20,"rest_minutes":20,
    "lights_off":true,"measurement_source":"battery_terminals"
  }]
}
```

Alternatively provide `csv` containing UTF-8 CSV text in place of `readings`. Exactly one input format is allowed. Maximum assessment body: 1 MiB; CSV: 512 KiB; readings: 1–500. CSV validation is all-or-nothing. The latest 100 assessment reports are retained; exports preserve interpretation and source snapshots.

CSV columns: `at,signal,value,unit,condition,ambient_c,rest_minutes,lights_off,measurement_source`. The first four columns are required. Optional blank context values mean unknown. A blank value is missing; it is never coerced to zero. `lights_off` accepts `true`, `false`, or blank. Duplicate/unknown headers, malformed rows, invalid units, nonfinite numbers, and timezone-free timestamps are rejected with 400.

Signals/units: `battery_v`/`V`, `temperature_c`/`C` or `F`, `rpm`/`rpm`, `speed_kph`/`km/h` or `mph`. Temperatures/speeds normalize to C and km/h. Reports retain original value/unit and sort by actual timestamps in UTC. Operating conditions: `resting`, `idle`, `driving`, `unknown`. Measurement sources: `battery_terminals`, `obd`, `unknown`.

Each result has one of these statuses:

| Status | Meaning |
| --- | --- |
| `reference_match` | Falls in a published band under applicable conditions; inspect the category |
| `unclassified` | Outside the discrete published bands; no interpolation or diagnosis |
| `conditions_not_met` | Reference exists but measurement context does not match |
| `reference_unavailable` | No reviewed vehicle/signal reference is bundled |
| `missing` | No value supplied |

`flagged` is true for half-charge/discharged reference matches and values outside published bands. It is not an assertion that the car or battery is faulty. `summary` counts comparisons, flags, unavailable references, unmet conditions, and missing readings. Reports have no overall healthy/unhealthy score. Measurement reports are not exported as JUnit tests because reference observations are not regression-test results.
