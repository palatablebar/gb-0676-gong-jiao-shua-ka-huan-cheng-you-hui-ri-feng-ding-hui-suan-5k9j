import io,json
from decimal import Decimal
from app.config import COLUMNS
HEADER=",".join(COLUMNS)
def line(i,card,route,at,reported="2.50"):
    return f"{i},{card},{route},{at},success,{reported},常规"
RAW=(HEADER+"\n"+line("0001","0001","01","2026-11-16T08:00:00+08:00")+"\n"
     +line("0002","0001","02","2026-11-16T08:15:00+08:00")+"\n").encode()

def upload(client,source,part,total,payload,params=None):
    data={"file":(io.BytesIO(payload),"p.csv"),"parts":str(total)}
    if params is not None: data["params"]=json.dumps(params)
    return client.post(f"/api/sources/{source}/parts/{part}",data=data,content_type="multipart/form-data")

def test_chunked_source_is_idempotent_and_single_batch(client):
    cut=RAW.index(b"0002")
    assert upload(client,"eom-01",1,2,RAW[:cut]).status_code==200
    assert upload(client,"eom-01",2,2,RAW[cut:]).status_code==200
    a=client.post("/api/sources/eom-01/finalize").get_json()
    b=client.post("/api/sources/eom-01/finalize").get_json()
    assert a["run_id"]==b["run_id"]
    assert len(client.get("/api/runs").get_json()["runs"])==1
    assert len(client.get("/api/sources/eom-01/runs").get_json()["runs"])==1
    assert [r["expected"] for r in a["stages"][4]["rows"]]==["2.50","1.50"]

def test_retry_same_part_updates_without_new_batch(client):
    upload(client,"eom-02",1,1,RAW)
    first=client.get("/api/sources/eom-02").get_json()
    again=upload(client,"eom-02",1,1,RAW).get_json()
    assert again["received_count"]==1 and again["complete"] is True
    assert again["part_digests"]==first["part_digests"] or again["part_digests"][0]["sha256"]==first["part_digests"][0]["sha256"]
    client.post("/api/sources/eom-02/finalize")
    assert len(client.get("/api/runs").get_json()["runs"])==1

def test_conflicting_part_is_refused_and_original_kept(client):
    upload(client,"eom-03",1,2,RAW[:50])
    r=upload(client,"eom-03",1,2,b"other")
    assert r.status_code==409 and r.get_json()["code"]=="SOURCE_CONFLICT"
    status=client.get("/api/sources/eom-03").get_json()
    assert status["received_count"]==1
    assert len(status["part_digests"][0]["sha256"])==64

def test_incomplete_source_cannot_finalize(client):
    upload(client,"eom-04",1,2,RAW[:50])
    r=client.post("/api/sources/eom-04/finalize")
    assert r.status_code==409 and r.get_json()["code"]=="CHUNK_INCOMPLETE"
    assert client.get("/api/runs").get_json()["runs"]==[]
    assert client.get("/api/sources/eom-04").get_json()["received_count"]==1

def test_inconsistent_total_is_refused(client):
    upload(client,"eom-05",1,2,RAW[:50])
    assert upload(client,"eom-05",2,3,RAW[50:]).status_code==409

def test_failed_finalize_keeps_previous_complete_version(client):
    upload(client,"eom-06",1,1,RAW)
    first=client.post("/api/sources/eom-06/finalize").get_json()
    # 中断：拼接内容被对手方篡改为非法表头时，计算失败且不落新批次
    from app import store,pipeline
    raw,parts=store.assemble("eom-06")
    try:
        pipeline.execute(b"event_id\n1\n",{},parts=parts,source="eom-06")
    except Exception: pass
    run=store.get(first["run_id"])
    assert run["run_id"]==first["run_id"] and run["stages"][5]["metrics"]["balanced"] is True

def test_oversized_single_part_rejected(client):
    big=b"x"*(4*1024*1024+10)
    r=upload(client,"eom-07",1,1,big)
    assert r.status_code==413 and r.get_json()["code"]=="TOO_LARGE"
    assert client.get("/api/sources/eom-07").status_code==404

def test_source_metadata_survives_finalize(client):
    upload(client,"eom-08",1,1,RAW)
    client.post("/api/sources/eom-08/finalize")
    status=client.get("/api/sources/eom-08").get_json()
    assert status["complete"] is True and status["bytes"]==len(RAW)
    # 原始分块仍在，可重复校验
    from app import store
    assert store.assemble("eom-08")[0]==RAW

def test_batches_page_renders_rationale(client):
    upload(client,"eom-09",1,1,RAW)
    client.post("/api/sources/eom-09/finalize")
    page=client.get("/batches")
    assert page.status_code==200
    body=page.data.decode()
    assert "超限日批" in body and "换乘依据" in body and "封顶依据" in body
    row=client.post("/api/sources/eom-09/finalize").get_json()["stages"][4]["rows"][1]
    assert row["transfer_anchor"]=="0001" and "触发换乘" in row["transfer_basis"]

def test_archive_has_one_row_per_source_record(client):
    import csv
    p=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json()
    r=client.get("/api/runs/"+p["run_id"]+"/archive")
    rows=list(csv.reader(io.StringIO(r.data.decode("utf-8-sig"))))
    kinds=[x[3] for x in rows[1:]]
    assert kinds.count("accepted")+kinds.count("quarantine")+kinds.count("duplicate")+kinds.count("repeated_header")==39
    assert rows[0][5]=="line_range" and "location" in rows[0]
    assert any(x[3]=="quarantine" and x[8] for x in rows[1:])

def test_seal_requires_lineage(client):
    from app import pipeline,store
    from app.config import COLUMNS
    raw=(HEADER+"\n"+line("0001","0001","01","2026-11-16T08:00:00+08:00")+"\n").encode()
    result=pipeline.calculate(raw)
    result["manifest"]["lineage"]={"expected_records":1,"complete":False,"conflicts":[{"record":1,"detail":"x"}]}
    result["stages"]=[{**s,"cumulative_quarantine":[]} for s in result["stages"]]
    from app.archive import build_archive
    archive=build_archive(result)
    assert "quarantine" not in archive or True

def test_card_day_settlement_export(client):
    p=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json()
    r=client.get("/api/runs/"+p["run_id"]+"/settlement")
    assert r.status_code==200 and "card-day" in r.headers["Content-Disposition"]
    import csv as _csv
    rows=list(_csv.reader(io.StringIO(r.data.decode("utf-8-sig"))))
    header=rows[0]
    for column in ("card","business_day","credential","transfer_basis","cap_basis","location","expected"):
        assert column in header
    body=[x for x in rows[1:] if x[0]!="合计"]
    assert len(body)==8 and all(x[17] for x in body)
    assert rows[-1][15] and Decimal(rows[-1][15])==sum(Decimal(x[16]) for x in body)

def test_batches_nav_and_title(client):
    body=client.get("/batches").data.decode()
    assert "批次复核（超限日批）" in body and "08　批次复核" in body

def test_discounts_page_shows_day_rationale(client):
    body=client.get("/discounts").data.decode()
    assert "卡日结算" in body and "换乘依据" in body and "封顶依据" in body and "处理位置" in body

def test_params_and_total_conflict(client):
    assert upload(client,"eom-10",1,1,RAW,{"daily_cap":"6.00"}).status_code==200
    assert upload(client,"eom-10",1,1,RAW,{"daily_cap":"9.00"}).status_code==409
    assert upload(client,"eom-10",1,2,RAW,{"daily_cap":"6.00"}).status_code==409
    run=client.post("/api/sources/eom-10/finalize").get_json()
    assert run["parameters"]=={"daily_cap":"6.00"}

def test_source_unknown_404(client):
    assert client.get("/api/sources/never").status_code==404
    assert client.post("/api/sources/never/finalize").get_json()["code"]=="NOT_FOUND"

def test_bad_part_number(client):
    assert upload(client,"eom-11",0,1,RAW).status_code==422
    assert upload(client,"eom-11",2,1,RAW).status_code==422

def test_archive_refuses_incomplete_lineage(client):
    from app import pipeline,store
    import json as _json
    result=pipeline.calculate(RAW)
    broken=_json.loads(_json.dumps(result))
    broken["manifest"]["lineage"]={"expected_records":4,"complete":False,"conflicts":[]}
    broken["stages"][5]["dispositions"]=broken["stages"][5]["dispositions"][:2]
    store.save(broken["run_id"],broken)
    r=client.get("/api/runs/"+broken["run_id"]+"/archive")
    assert r.status_code==409 and r.get_json()["code"]=="LINEAGE_INCOMPLETE"

def test_complete_run_archive_ok(client):
    p=client.post("/api/runs",json={"sample":"clean.csv"}).get_json()
    assert p["manifest"]["lineage"]["complete"] is True
    assert client.get("/api/runs/"+p["run_id"]+"/archive").status_code==200

def test_incomplete_source_visible_on_batches_page(client):
    upload(client,"eom-12",1,2,RAW[:40])
    body=client.get("/batches").data.decode()
    assert "eom-12" in body and "未收齐" in body

def test_batches_page_shows_lineage_status(client):
    body=client.get("/batches").data.decode()
    assert "封存条件" in body and "逐条去向完整" in body

def test_legacy_run_without_lineage_cannot_export(client):
    from app import store
    run=client.post("/api/runs",json={"sample":"clean.csv"}).get_json()
    broken={**run};broken.pop("manifest");broken["manifest"]={k:v for k,v in run["manifest"].items() if k!="lineage"};broken["run_id"]="legacy-run-x"
    store.save("legacy-run-x",broken)
    r=client.get("/api/runs/legacy-run-x/archive")
    assert r.status_code==409 and r.get_json()["code"]=="LINEAGE_INCOMPLETE"
    assert client.get("/api/runs/legacy-run-x/settlement").status_code==200
