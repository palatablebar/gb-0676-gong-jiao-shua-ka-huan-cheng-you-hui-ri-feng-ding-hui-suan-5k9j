"""来源行逐条去向。

每个 CSV 数据记录在采信阶段获得唯一的 _record 序号。后续阶段隔离记录时
仍携带该序号；封存前必须能把 1..input 的每条记录映射到且只映射到一个去向：
accepted / quarantine / duplicate / blank / repeated_header。
"""
EXCLUDED={"duplicate","blank","repeated_header"}
def reconcile(intake, quarantine, rows):
    base={}
    conflicts=[]
    for item in (intake or {}).get("dispositions",[]) or []:
        record=item.get("record")
        if record is None:
            conflicts.append({"record":None,"detail":"去向缺少记录序号"})
            continue
        if record in base:
            conflicts.append({"record":record,"detail":"同一记录存在多条去向"})
            continue
        base[record]={**item}
    for q in quarantine or []:
        record=q.get("_record")
        if record is None:
            conflicts.append({"record":None,"detail":"隔离记录缺少序号"})
            continue
        if record not in base:
            conflicts.append({"record":record,"detail":"隔离记录不在采信去向中"})
            continue
        if base[record].get("kind") in EXCLUDED:
            conflicts.append({"record":record,"detail":"已排除记录又被隔离"})
            continue
        base[record].update(kind="quarantine",reason=q.get("reason",""),detail=q.get("detail",""),stage=q.get("_stage",""))
    final={}
    for row in rows or []:
        record=row.get("_record")
        if record is None:
            conflicts.append({"record":None,"detail":"结果记录缺少序号"})
            continue
        if record not in base:
            conflicts.append({"record":record,"detail":"结果记录不在采信去向中"})
            continue
        if base[record].get("kind") in EXCLUDED:
            conflicts.append({"record":record,"detail":"已排除记录出现在结果中"})
            continue
        final[record]=row
        base[record].update(kind="accepted",reason="",detail="",stage="clearing")
    dispositions=[base[k] for k in sorted(base)]
    total=int((intake or {}).get("input",0) or 0)
    actual=[d["record"] for d in dispositions]
    final_records=set(final)
    accepted_records={d["record"] for d in dispositions if d.get("kind")=="accepted"}
    quarantine_records={d["record"] for d in dispositions if d.get("kind")=="quarantine"}
    quarantine_seen={q.get("_record") for q in (quarantine or [])}
    missing=[r for r in range(1,total+1) if r not in base]
    complete=(total>0 and not conflicts and actual==list(range(1,total+1))
              and final_records==accepted_records
              and quarantine_seen==quarantine_records)
    return {"dispositions":dispositions,"conflicts":conflicts,"complete":complete,
            "missing":missing,"expected_records":total,
            "accepted":len(accepted_records),"quarantine":len(quarantine_records),
            "excluded":sum(d.get("kind") in EXCLUDED for d in dispositions)}
