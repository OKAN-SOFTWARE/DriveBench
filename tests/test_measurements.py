import json
from pathlib import Path
import pytest
from drivebench.garage import GarageStore, vehicle_from_request
from drivebench.measurements import normalize_reading, evaluate_reading, parse_csv, assess, template_csv
from drivebench.reports import assessment_text
from drivebench.store import RunStore

PROFILE = "toyota-corolla-im-2017-us"


def reading(**changes):
    return {"at":"2026-10-31T13:00:00-04:00","signal":"battery_v","value":12.7,"unit":"V",
            "condition":"resting","ambient_c":20,"rest_minutes":20,"lights_off":True,
            "measurement_source":"battery_terminals",**changes}


def vehicle():
    return vehicle_from_request({"profile_id":PROFILE,"nickname":"Test car"})


@pytest.mark.parametrize("value,label,flagged", [(12.6,"Full-charge",False),(12.8,"Full-charge",False),
    (12.2,"Half-charge",True),(12.4,"Half-charge",True),(11.8,"Discharged",True),(12.0,"Discharged",True)])
def test_documented_bands_include_boundaries(value,label,flagged):
    result=evaluate_reading(normalize_reading(reading(value=value)),vehicle())
    assert result["status"]=="reference_match"
    assert result["label"].startswith(label) and result["flagged"] is flagged
    assert result["source"]["document"]=="OM12K64U" and result["source"]["page"]==329


@pytest.mark.parametrize("value",[12.1,12.5,11.7,13])
def test_between_and_outside_bands_are_not_interpolated(value):
    result=evaluate_reading(normalize_reading(reading(value=value)),vehicle())
    assert result["status"]=="unclassified" and result["flagged"]


@pytest.mark.parametrize("changes",[{"condition":"idle"},{"ambient_c":19.9},{"ambient_c":None},
    {"rest_minutes":10},{"rest_minutes":30},{"lights_off":False},{"measurement_source":"obd"},{"measurement_source":"unknown"}])
def test_conditions_gate_even_plausible_voltage(changes):
    result=evaluate_reading(normalize_reading(reading(**changes)),vehicle())
    assert result["status"]=="conditions_not_met" and result["unmet_conditions"]
    assert not result["flagged"]  # Missing context is not a diagnosed fault.


def test_missing_and_unavailable_are_distinct_from_reference_match():
    missing=evaluate_reading(normalize_reading(reading(value=None)),vehicle())
    assert missing["status"]=="missing"
    custom={**vehicle(),"profile_id":None}
    result=evaluate_reading(normalize_reading(reading()),custom)
    assert result["status"]=="reference_unavailable" and result["reference"] is None
    coolant=evaluate_reading(normalize_reading(reading(signal="temperature_c",value=185,unit="F")),vehicle())
    assert coolant["value"]==85 and coolant["status"]=="reference_unavailable"


@pytest.mark.parametrize("changes",[{"value":True},{"value":float('nan')},{"value":float('inf')},{"value":10**500},
    {"value":-1},{"unit":"mV"},{"at":"2026-10-31T13:00:00"},{"at":"garbage"},{"condition":[]},
    {"measurement_source":[]},{"lights_off":"true"},{"signal":"arbitrary"},{"ambient_c":True},{"rest_minutes":-1}])
def test_invalid_readings_rejected(changes):
    with pytest.raises(ValueError):normalize_reading(reading(**changes))


def test_csv_normalizes_units_and_keeps_blank_missing_values():
    records=parse_csv('at,signal,value,unit\n2026-10-31T17:00:00Z,speed_kph,10,mph\n2026-10-31T17:00:01Z,battery_v,,V\n')
    assert records[0]["value"]==pytest.approx(16.09344)
    assert records[1]["value"] is None
    assert len(parse_csv(template_csv().decode()))==2


@pytest.mark.parametrize("text",['at,signal,value,value,unit\n', 'at,signal,value,unit,secret\n',
    'at,signal,value,unit\n2026-10-31T17:00:00Z,battery_v,NaN,V\n',
    'at,signal,value,unit\n2026-10-31T17:00:00Z,battery_v,12.7,V,extra\n',
    'at,signal,value,unit\n"unterminated', 'at,signal,value,unit\n'])
def test_csv_errors_are_atomic_and_explicit(text):
    with pytest.raises(ValueError):parse_csv(text)


def test_csv_row_and_byte_limits():
    header="at,signal,value,unit\n";row="2026-10-31T17:00:00Z,battery_v,12.7,V\n"
    with pytest.raises(ValueError,match="500"):parse_csv(header+row*501)
    with pytest.raises(ValueError,match="512"):parse_csv("x"*(512*1024+1))


def test_preset_identity_and_rules_cannot_be_overridden():
    with pytest.raises(ValueError):vehicle_from_request({"profile_id":PROFILE,"nickname":"Car","year":2025})
    with pytest.raises(ValueError):vehicle_from_request({"profile_id":"invented","nickname":"Car"})


@pytest.mark.parametrize("profile,document,page",[("toyota-corolla-2016-us","OM12J84U",555),(PROFILE,"OM12K64U",329)])
def test_each_vehicle_uses_its_own_source_document(profile,document,page):
    saved=vehicle_from_request({"profile_id":profile,"nickname":"Car"})
    result=evaluate_reading(normalize_reading(reading()),saved)
    assert result["source"]["document"]==document and result["source"]["page"]==page
    assert result["status"]=="reference_match"


def test_assessment_snapshot_survives_restart_and_exports_sources(tmp_path):
    path=tmp_path/"v01.db";store=RunStore(path)
    # Exercise adding v0.2 tables to a database that already has v0.1 runs.
    store.save({"id":"existing","status":"passed","started_at":"2026-10-31T00:00:00Z"})
    garage=GarageStore(store);saved=garage.add_vehicle({"profile_id":PROFILE,"nickname":"My Corolla"})
    result=assess({"vehicle_id":saved["id"],"name":"Battery and coolant","readings":[reading(),reading(signal="temperature_c",value=85,unit="C")]},garage)
    garage.save_assessment(result)
    assert result["summary"]=={"readings":2,"flagged":0,"compared":1,"unavailable":1,"conditions_not_met":0,"missing":0}
    exported=assessment_text(result).decode()
    assert "OM12K64U" in exported and "page 329" in exported and "No overall vehicle-health verdict" in exported
    store.close();store=RunStore(path);garage=GarageStore(store)
    try:
        assert store.get("existing")["status"]=="passed"
        assert garage.assessment(result["id"])==result
        assert garage.vehicles()[0]["id"]==saved["id"]
    finally:store.close()


def test_invalid_csv_does_not_persist_a_partial_assessment(tmp_path):
    store=RunStore(tmp_path/"garage.db");garage=GarageStore(store)
    try:
        saved=garage.add_vehicle({"profile_id":PROFILE,"nickname":"Car"})
        bad='at,signal,value,unit\n2026-10-31T17:00:00Z,battery_v,12.7,V\n2026-10-31T17:00:01Z,battery_v,wrong,V\n'
        with pytest.raises(ValueError):garage.save_assessment(assess({"vehicle_id":saved["id"],"name":"CSV","csv":bad},garage))
        assert garage.assessments()==[]
    finally:store.close()


def test_sorting_uses_instants_not_fractional_timestamp_strings(tmp_path):
    store=RunStore(tmp_path/"garage.db");garage=GarageStore(store)
    try:
        saved=garage.add_vehicle({"profile_id":PROFILE,"nickname":"Car"})
        result=assess({"vehicle_id":saved["id"],"name":"Timeline","readings":[reading(at="2026-10-31T17:00:00.1Z"),reading(at="2026-10-31T17:00:00Z")]},garage)
        assert result["readings"][0]["at"]=="2026-10-31T17:00:00Z"
    finally:store.close()
