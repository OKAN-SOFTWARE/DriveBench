import json
import xml.etree.ElementTree as ET
from pathlib import Path


def junit_xml(run: dict) -> bytes:
    results = list(run.get("results", []))
    if run.get("status") != "passed" and not any(r["status"] != "passed" for r in results):
        results.append({"scenario":"run_completion", "status":"failed", "steps":[], "trace":[],
                        "error":run.get("error", "Run did not complete successfully")})
    suite = ET.Element("testsuite", name="DriveBench simulated integration scenarios", tests=str(len(results)),
                       failures=str(sum(r["status"] != "passed" for r in results)), errors="0",
                       time=str(run.get("duration_ms", 0) / 1000))
    props = ET.SubElement(suite, "properties")
    ET.SubElement(props, "property", name="protocol", value="DriveBench custom TCP/IP v1")
    ET.SubElement(props, "property", name="hardware", value="software simulation only")
    for result in results:
        case = ET.SubElement(suite, "testcase", classname="DriveBench.Integration", name=result["scenario"],
                             time=str(result.get("duration_ms", 0) / 1000))
        if result["status"] != "passed":
            ET.SubElement(case, "failure", message=result.get("error", "Scenario failed")).text = json.dumps(result["steps"], indent=2)
        ET.SubElement(case, "system-out").text = json.dumps({"steps": result["steps"], "trace": result["trace"]}, indent=2)
    return ET.tostring(suite, encoding="utf-8", xml_declaration=True)


def write_reports(run, json_path, xml_path):
    for target, content in [(json_path, json.dumps(run, indent=2).encode()), (xml_path, junit_xml(run))]:
        if target:
            path = Path(target); path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


def assessment_text(report):
    vehicle = report["vehicle"]
    lines = ["DriveBench measurement reference report", report["name"],
             f"Vehicle: {vehicle['year']} {vehicle['make']} {vehicle['model']} · {vehicle['engine']} · {vehicle['market']}",
             f"Created: {report['created_at']}", f"Catalog: {report['catalog_version']}", report["scope"], ""]
    for row in report["readings"]:
        lines += [f"{row['at']} · {row['signal']} · {row['value'] if row['value'] is not None else 'MISSING'} {row['unit']}",
                  row["label"], row["explanation"],
                  f"Conditions: {row['condition']}; ambient {row['ambient_c']} °C; rest {row['rest_minutes']} min; lights off {row['lights_off']}; source {row['measurement_source']}"]
        if row["unmet_conditions"]: lines.append("Unmet: "+"; ".join(row["unmet_conditions"]))
        if row["reference"]: lines += [row["reference"]["conditions"], row["reference"]["scope"]]
        if row["source"]:
            source=row["source"]
            lines += [f"Reference: {source['title']} · {source['document']} · page {source['page']}",source["url"],f"Source SHA256: {source['sha256']}"]
        lines.append("")
    return "\n".join(lines).encode("utf-8")
