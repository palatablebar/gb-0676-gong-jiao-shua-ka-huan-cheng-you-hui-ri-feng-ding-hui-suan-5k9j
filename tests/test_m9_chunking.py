import io
from decimal import Decimal
from app.modules.m5_discounts.rules import evaluate,card_days
from app.modules.m1_taps.rules import evaluate as intake
from app.modules.m3_fares.rules import evaluate as fares
from app.modules.m4_journeys.rules import evaluate as journeys
from app.config import COLUMNS

HEADER=",".join(COLUMNS)
def tap(event_id,card,route,at,reported="2.50",result="success",note="常规"):
    return f'{event_id},{card},{route},{at},{result},{reported},{note}'

def split_rows(raw,cut):
    """把 CSV 原始字节按字节切成两块，模拟超限批次拆分上传。"""
    return raw[:cut],raw[cut:]

def ride(event_id,minute,route="01",card="0001",reported="2.50",base="2.50",day="2026-11-16",part=1):
    return {"event_id":str(event_id),"card":card,"business_day":day,"route":route,"base_fare":base,
            "reported":reported,"fare_version":"F2","at":f"2026-11-16T{8+minute//60:02d}:{minute%60:02d}:00Z",
            "_sources":[int(event_id)],"_record":int(event_id),"_part":part,"_line":int(event_id)}

def test_card_day_reaggregation_beats_chunk_boundary():
    """同一卡日被拆到两块，若按块接续会漏算 08:15 的换乘；归集后必须优惠。"""
    whole=[ride(1,0),ride(2,15,"02"),ride(3,30,"03",reported="1.50")]
    split=[ride(1,0),ride(2,15,"02",part=2),ride(3,30,"03",reported="1.50",part=2)]
    expected=evaluate(whole,{})["rows"]
    shuffled=evaluate(list(reversed(split)),{})["rows"]
    assert [r["expected"] for r in expected]==["2.50","1.50","1.50"]
    assert [r["expected"] for r in shuffled]==[r["expected"] for r in expected]
    assert expected[1]["transfer_anchor"]=="1"

def test_cap_is_per_card_day_not_per_chunk():
    rows=[ride(1,0),ride(2,10,"02"),ride(3,20,"03"),ride(4,30,"01"),ride(5,90,"02")]
    # 即使每块单独看都未触顶，归集后当天合计只能是 6.00
    same=evaluate(rows,{})["rows"]
    assert sum(Decimal(r["expected"]) for r in same)==Decimal("6.00")
    for r in same:
        assert Decimal(r["base_fare"])==Decimal(r["expected"])+Decimal(r["transfer_discount"])+Decimal(r["cap_discount"])

def test_day_state_does_not_leak_across_cards_or_days():
    rows=[ride(1,0),ride(2,10,"02"),ride(3,10,"02",day="2026-11-17",reported="2.50")]
    out=evaluate(rows,{})["rows"]
    by_day={r["business_day"]:r for r in out if r["event_id"]=="3"}
    assert by_day["2026-11-17"]["transfer_discount"]=="0.00"
    assert by_day["2026-11-17"]["expected"]=="2.50"

def test_rationale_is_explicit_for_each_event():
    out=evaluate([ride(1,0),ride(2,15,"02"),ride(3,60,"03")],{})["rows"]
    assert out[0]["transfer_basis"].startswith("本卡日")
    assert "触发换乘" in out[1]["transfer_basis"]
    assert "截止点排除" in evaluate([ride(1,0),ride(2,15,"02"),ride(3,80,"03")],{})["rows"][2]["transfer_basis"]
    assert all(r["cap_basis"] and r["credential"] and r["location"] for r in out)

def test_card_days_expose_credentials_transfer_cap_and_location():
    out=evaluate([ride(1,0,part=1),ride(2,15,"02",part=2),ride(3,30,"03",part=2),ride(4,45,"01",part=2)],{})["rows"]
    day=card_days(out)[0]
    assert day["card"]=="0001" and day["business_day"]=="2026-11-16"
    assert set(day["parts"])=={"1","2"} and "2" in day["location"]
    assert "F2" in day["receipts"]
    assert day["transfer_hits"]==3 and day["capped_events"]>=1
    assert day["expected"]=="6.00"
    assert all(e["location"] and e["transfer_basis"] and e["cap_basis"] for e in day["events"])

def test_lineage_complete_requires_every_source_record():
    from app.pipeline import calculate
    r=calculate((HEADER+"\n"+tap("1","0001","01","2026-11-16T08:00:00+08:00")+"\n").encode())
    assert r["manifest"]["lineage"]["complete"] is True
    assert r["stages"][5]["metrics"]["lineage_complete"] is True

def test_missing_disposition_blocks_seal():
    from app.lineage import reconcile
    intake={"input":2,"duplicate":0,"blank":0,"repeated_headers":0,
            "dispositions":[{"record":1,"kind":"accepted","start_line":1,"end_line":1}]}
    state=reconcile(intake,[],[])
    assert state["complete"] is False and state["missing"]==[2]

def test_partitioned_upload_matches_whole_file(tmp_path,monkeypatch):
    from app import store
    monkeypatch.setattr(store,"DATA_DIR",tmp_path)
    raw=(HEADER+"\n"+tap("1","0001","01","2026-11-16T08:00:00+08:00")+"\n"
         +tap("2","0001","02","2026-11-16T08:15:00+08:00")+"\n").encode()
    cut=raw.index(b"2,0001")
    left,right=split_rows(raw,cut)
    store.put_part("end-of-month",1,2,left,{})
    assert store.source_status("end-of-month")["complete"] is False
    store.put_part("end-of-month",2,2,right,{})
    from app.pipeline import finalize_source
    run=finalize_source("end-of-month")
    whole_rows=run["stages"][4]["rows"]
    assert [r["expected"] for r in whole_rows]==["2.50","1.50"]
    assert {r["_part"] for r in whole_rows}=={1,2}

def test_blank_and_duplicate_records_get_dispositions():
    from app.pipeline import calculate
    raw=(HEADER+"\n"+tap("1","0001","01","2026-11-16T08:00:00+08:00")+"\n"
         +tap("1","0001","01","2026-11-16T08:00:00+08:00")+"\n"+HEADER+"\n\n").encode()
    result=calculate(raw)
    kinds=[d["kind"] for d in result["stages"][5]["dispositions"]]
    assert kinds==["accepted","duplicate","repeated_header","blank"]
    assert result["manifest"]["lineage"]["complete"] is True

def test_lineage_detects_row_dropped_upstream():
    from app.lineage import reconcile
    intake={"input":2,"duplicate":0,"blank":0,"repeated_headers":0,
            "dispositions":[{"record":1,"kind":"accepted","start_line":1,"end_line":1},
                            {"record":2,"kind":"accepted","start_line":2,"end_line":2}]}
    state=reconcile(intake,[],[{"_record":1,"_line":1}])
    assert state["complete"] is False
    assert state["accepted"]==2 and state["missing"]==[]

def test_size_guard_for_source(tmp_path,monkeypatch):
    from app import store
    from app.errors import DomainError
    import pytest
    monkeypatch.setattr(store,"DATA_DIR",tmp_path)
    monkeypatch.setattr(store,"MAX_SOURCE_BYTES",10)
    store.put_part("big",1,2,b"012345",{})
    with pytest.raises(DomainError) as e: store.put_part("big",2,2,b"678901",{})
    assert e.value.code=="SOURCE_TOO_LARGE"

def test_card_day_cap_total_is_not_shadowed():
    out=evaluate([ride(1,0),ride(2,10,"02"),ride(3,20,"03"),ride(4,90)],{})["rows"]
    day=card_days(out)[0]
    assert day["cap_discount"]=="2.00" and day["expected"]=="6.00"
    assert "封顶减免 1 笔" in day["cap_basis"]
    assert Decimal(day["base_total"])==Decimal(day["expected"])+Decimal(day["transfer_discount"])+Decimal(day["cap_discount"])

def test_daily_cap_parameter_respected():
    out=evaluate([ride(1,0),ride(2,10,"02"),ride(3,20,"03")],{"parameters":{"daily_cap":"3.00"}})["rows"]
    assert sum(Decimal(r["expected"]) for r in out)==Decimal("3.00")
    assert card_days(out,{"daily_cap":"3.00"})[0]["expected"]=="3.00"

def test_chunked_matches_whole_for_every_sample(tmp_path,monkeypatch):
    from app import store
    from app.config import ROOT
    from app.pipeline import calculate,execute,finalize_source
    monkeypatch.setattr(store,"DATA_DIR",tmp_path)
    for name in ("dirty.csv","clean.csv","legacy.csv"):
        raw=(ROOT/"sample_data"/name).read_bytes()
        for parts in (1,2,7):
            source=f"{name}-{parts}"
            for index in range(parts):
                store.put_part(source,index+1,parts,raw[index*len(raw)//parts:(index+1)*len(raw)//parts],{})
            chunked=finalize_source(source)
            whole=calculate(raw)
            assert chunked["manifest"]["input_sha256"]==whole["manifest"]["input_sha256"]
            # 业务结果必须逐行一致；仅传输位置字段（_part/location）允许不同。
            def business(run):
                return [{k:v for k,v in row.items() if k not in {"_part","_part_end","location"}}
                        for row in run["stages"][4]["rows"]]
            assert business(chunked)==business(whole)
            assert chunked["stages"][5]["metrics"]==whole["stages"][5]["metrics"]
            assert chunked["manifest"]["lineage"]["complete"] is True
