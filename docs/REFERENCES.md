# Vehicle references — catalog 2026-10-31.1

The bundled catalog contains narrowly scoped factual reference data and links to manufacturer documents. Full manuals are not redistributed. A source review means the cited numeric table and applicability were checked against that document; it does not mean Toyota endorses DriveBench or that the software has been validated on vehicle hardware.

| Profile | Manufacturer source | Reference page | Engine applicability page |
| --- | --- | --- | --- |
| US 2016 Toyota Corolla, 1.8 L gasoline, 2ZR-FE / 2ZR-FAE | [Toyota OM12J84U](https://assets.sia.toyota.com/publications/en/om-s/OM12J84U/pdf/OM12J84U.pdf) | 555 | 552 |
| US 2017 Toyota Corolla iM, 1.8 L gasoline, 2ZR-FAE | [Toyota OM12K64U](https://assets.sia.toyota.com/publications/en/om-s/OM12K64U/pdf/OM12K64U.pdf) | 329 | 326 |

Review date: October 31, 2026. Source PDF SHA256 values:

```text
OM12J84U: c03210ea435a10f1b454f1be582bc5be0002c830ec049dd48633a4f53071027c
OM12K64U: d38feeb8cab5c3fb5506241ee0e81ec4f24b6c0645bdd0aad6afd8f9b800847d
```

Both manuals list these **open-circuit battery-voltage reference bands**, at 20 °C (68 °F), checked 20 minutes after the engine and all lights are switched off:

| Reference category | Voltage |
| --- | --- |
| Full charge | 12.6–12.8 V |
| Half charge | 12.2–12.4 V |
| Discharged | 11.8–12.0 V |

DriveBench preserves the discrete bands and inclusive endpoints. It does not interpolate values in the gaps, compensate for temperature, extrapolate to other configurations, use a charging voltage as a resting voltage, or estimate battery health. The application conservatively requires an explicit 20-minute rest value and a battery-terminal measurement origin; an ECU/OBD voltage is not treated as equivalent. These applicability gates are part of DriveBench's comparison policy, alongside the conditions published by Toyota.

Full-charge matches are displayed as a reference match. Half-charge/discharged matches and values outside published bands are flagged for review, with no component-failure claim. All other signals, custom vehicles, and measurements outside the stated conditions remain unclassified for the stated reason. Simulator fault thresholds never enter the real-vehicle comparison engine.

## Catalog maintenance

`drivebench/references/vehicles.json` is the reviewed catalog. To add coverage, record exact model year, engine/powertrain, market, signal/unit, operating conditions, manufacturer document/page, review date, and source hash. Add boundary, missing-data, condition-gating, and cross-profile-isolation tests before shipping a rule. Review document access and reuse terms; retain links instead of bundling manuals.

Reports store the catalog version and source/vehicle snapshots. Updating the catalog affects new assessments, not saved reports. The application makes no manufacturer API requests and sends no readings or vehicle details off the machine. Opening a source link uses the user's browser to visit Toyota's document host.
