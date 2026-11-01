import json
import threading
import pytest
from drivebench.service import LabService
from drivebench.store import RunStore
from drivebench.web import make_server
from test_store_api import request


@pytest.fixture
def garage_api(tmp_path):
    store=RunStore(tmp_path/"garage.db");service=LabService(store,"127.0.0.1",0,simulation_enabled=False)
    server=make_server(("127.0.0.1",0),service);thread=threading.Thread(target=server.serve_forever);thread.start()
    try:yield server
    finally:server.shutdown();thread.join();server.server_close();service.close();store.close()


def post(server,path,body,headers=None):
    return request(server,"POST",path,json.dumps(body),headers or {"Content-Type":"application/json","X-DriveBench":"1"})


def test_garage_end_to_end_without_java(garage_api):
    server=garage_api
    assert json.loads(request(server,"GET","/api/status")[2])["simulator"]["enabled"] is False
    assert post(server,"/api/runs",{"scenario":"all"})[0]==409
    for asset in ["/garage.js","/garage.css"]:assert request(server,"GET",asset)[0]==200
    catalog=json.loads(request(server,"GET","/api/catalog")[2]);assert len(catalog["profiles"])==2
    status,_,body=post(server,"/api/vehicles",{"profile_id":"toyota-corolla-im-2017-us","nickname":"My car"})
    assert status==201;vehicle=json.loads(body)
    csv=request(server,"GET","/api/measurements/template.csv")[2].decode()
    status,_,body=post(server,"/api/assessments",{"vehicle_id":vehicle["id"],"name":"Imported session","csv":csv})
    assert status==201;report=json.loads(body)
    assert report["summary"]["compared"]==1 and report["summary"]["unavailable"]==1
    assert len(json.loads(request(server,"GET","/api/assessments")[2]))==1
    status,headers,body=request(server,"GET",f"/api/assessments/{report['id']}/export.json")
    assert status==200 and json.loads(body)==report and "attachment" in headers["Content-Disposition"]
    status,_,body=request(server,"GET",f"/api/assessments/{report['id']}/report.txt")
    assert status==200 and b"OM12K64U" in body


def test_custom_vehicle_never_receives_generic_limits(garage_api):
    body={"nickname":"Custom","make":"Kia","year":2025,"model":"Sportage","engine":"Unknown","powertrain":"gasoline","market":"US"}
    status,_,response=post(garage_api,"/api/vehicles",body);assert status==201;vehicle=json.loads(response)
    status,_,response=post(garage_api,"/api/assessments",{"vehicle_id":vehicle["id"],"name":"Check","readings":[{"at":"2026-10-31T17:00:00Z","signal":"battery_v","value":12.7,"unit":"V"}]})
    assert status==201 and json.loads(response)["readings"][0]["status"]=="reference_unavailable"


@pytest.mark.parametrize("path",["/api/vehicles","/api/assessments"])
def test_new_mutations_keep_same_origin_boundary(garage_api,path):
    assert post(garage_api,path,{},headers={"Content-Type":"application/json"})[0]==403
    assert post(garage_api,path,{},headers={"Content-Type":"application/json","X-DriveBench":"1","Origin":"https://evil.example"})[0]==403
    assert post(garage_api,path,{},headers={"Content-Type":"application/json","X-DriveBench":"1"})[0]==400
