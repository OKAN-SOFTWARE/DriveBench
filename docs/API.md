# Local dashboard API

For My Garage, CSV/manual measurements, and reference report routes added in v0.2, see [GARAGE_API.md](GARAGE_API.md).

Default origin: `http://127.0.0.1:8088`. All responses disable caching. The service binds only to loopback, validates the Host header, rejects cross-site writes, and requires `X-DriveBench: 1` for mutations. JSON is served with explicit content types; script/style assets are local.

| Method | Path | Result |
| --- | --- | --- |
| GET | `/api/status` | Simulator connectivity/telemetry, active run ID, scenario catalog, recent run summaries |
| GET | `/api/scenarios` | Six supported scenario definitions |
| GET | `/api/runs` | Recent run summaries, newest first |
| GET | `/api/runs/{id}` | Full report including completed scenario steps and traces |
| GET | `/api/runs/{id}/export.json` | Download completed/interrupted run as JSON |
| GET | `/api/runs/{id}/junit.xml` | Download completed/interrupted run as JUnit XML |
| POST | `/api/runs` | Start a scenario or full suite; returns 202 and initial run |

Start a run in PowerShell:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8088/api/runs `
  -Headers @{"X-DriveBench"="1"} `
  -ContentType "application/json" `
  -Body '{"scenario":"all"}'
```

Supported scenario IDs: `all`, `baseline`, `overheat`, `low_voltage`, `timeout_recovery`, `disconnect_recovery`, `invalid_input`. The request must contain exactly one `scenario` string. Maximum body size is 64 KiB.

An active run prevents another run (409). Exporting a running run returns 409. Unknown IDs return 404. Invalid input returns 400; a missing JSON content type returns 415. Untrusted Host/Origin or missing mutation header returns 403. A run starts as `running` and ends as `passed` or `failed`; abandoned persisted runs become `interrupted` on restart.

Steps and traces are saved after each complete scenario, rather than streamed for every socket operation. Poll `/api/status` and the active run about once per second. Assertion counts (`passed`, `failed`) count steps; JUnit testcase counts count scenarios. Inspect the run's top-level `status` as well as counts when determining overall success.

An interrupted run with no failed scenario receives a synthetic failing `run_completion` JUnit testcase so an incomplete export cannot appear successful in CI.

The API is a local development interface. Keep it bound to loopback. Do not expose it using a public reverse proxy.
