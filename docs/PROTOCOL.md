# DriveBench TCP protocol v1

This is a custom educational protocol. Each request/response is one UTF-8 JSON object followed by `\n` (the server also accepts CRLF). TCP may split or combine packets; neither side treats a socket read as a complete frame. Duplicate keys, trailing JSON, and nonstandard numbers are rejected.

## Envelope

```json
{"id":"demo-1","command":"read"}
```

```json
{"id":"demo-1","ok":true,"data":{"ignition":false,"sensors":{"temperature_c":85.0,"battery_v":12.6,"speed_kph":0.0},"active_faults":[],"stored_faults":[],"revision":0}}
```

```json
{"id":"demo-1","ok":false,"error":{"code":"INVALID_VALUE","message":"Value outside sensor bounds"}}
```

IDs must match `[A-Za-z0-9_-]{1,64}`. Invalid JSON or an invalid ID may produce `id: null`; a correlated client treats that as a protocol failure. Request fields are strict: unknown fields and incorrect JSON types are rejected. Commands do not require a particular field order.

## Commands

| Command | Additional fields | Result |
| --- | --- | --- |
| `read` | None | Full vehicle snapshot |
| `diagnostics` | None | Full vehicle snapshot, including diagnostic arrays |
| `reset` | None | Restore default sensors, ignition off, and empty faults; increment revision |
| `ignition` | `on`: boolean | Set ignition and evaluate fault rules |
| `set_sensor` | `sensor`: string, `value`: finite number | Validate bounds, set sensor, evaluate faults, return snapshot |
| `clear_faults` | None | Reject with `ACTIVE_FAULT` if active faults remain; otherwise clear stored codes |
| `inject_transport` | `mode`: `normal`, `delay`, or `disconnect`; optional `delay_ms`: integer | Acknowledge a connection-local fault plan |

For `delay`, `delay_ms` must be 50–2000. For `normal` and `disconnect`, it must be absent or zero. The plan applies once to the next non-injection request on that connection, then resets. Disconnect occurs before dispatch. A delayed request can still execute after its client times out. An injection acknowledgment is never delayed or dropped by the plan.

## Signals and fault rules

| Signal | Range | Default | Active threshold | Recovery threshold |
| --- | --- | --- | --- | --- |
| `temperature_c` | -40–160 | 85 | ≥ 105 | ≤ 100 |
| `battery_v` | 0–20 | 12.6 | < 11.5 | ≥ 12.0 |
| `speed_kph` | 0–240 | 0 | No fault rule | — |

Faults are evaluated when ignition is on. Turning ignition off clears active faults but preserves stored codes. Turning ignition on evaluates the current sensor values. Hysteresis retains the prior active state inside the gap between activation and recovery thresholds. All mutations and snapshots are synchronized; multiple clients share one vehicle state. The revision increases on successful mutation commands and reset, including setting an existing value.

`DB_TEMP_HIGH` and `DB_VOLT_LOW` are fictional codes. Stored codes latch after activation and remain until a successful `clear_faults` or `reset`.

## Limits and failures

The server permits at most 8192 bytes before the newline, 1000 requests per connection, a three-second socket read idle timeout, four active client workers, and eight queued connections. Oversized or invalid UTF-8 frames close the connection. Malformed JSON receives `INVALID_JSON` and the session can continue. Other error codes include `INVALID_REQUEST`, `INVALID_COMMAND`, `INVALID_VALUE`, `UNKNOWN_SENSOR`, and `ACTIVE_FAULT`.

The Python client accepts responses up to 64 KiB, correlates response IDs, enforces a response deadline, and closes a session on timeout, disconnect, or malformed response. A well-framed remote command rejection leaves the connection available. There is no authentication or encryption: the Java server binds only to `127.0.0.1` for local use.
