from decimal import Decimal
from app.reasons import sources
from app.errors import DomainError
from app.lineage import reconcile

def evaluate(rows,context):
    intake=context.get("intake")
    bad=context.get("quarantine",[])
    accepted=set(x for row in rows for x in sources(row))
    rejected=set(x for row in bad for x in sources(row))
    if accepted & rejected: raise DomainError("LINEAGE_OVERLAP","同一来源行被重复裁决")
    lineage=None
    if intake and "dispositions" in intake:
        lineage=reconcile(intake,bad,rows)
    m={"accepted_inputs":len(accepted),"quarantine_inputs":len(rejected),"output_records":len(rows),
       "records":len(rows)+len(rejected),"lineage_complete":None}
    if lineage:
        m.update(records=lineage["expected_records"],lineage_complete=lineage["complete"],
                 lineage_missing=len(lineage["missing"]),lineage_conflicts=len(lineage["conflicts"]),
                 lineage_accepted=lineage["accepted"],lineage_quarantine=lineage["quarantine"],
                 lineage_excluded=lineage["excluded"],
                 lineage_conflict_detail=[f"记录{c['record']}：{c['detail']}" for c in lineage["conflicts"]])
    if intake:
        excluded=intake["duplicate"]+intake["blank"]+intake["repeated_headers"]
        m.update(input=intake["input"],excluded=excluded,balanced=intake["input"]==len(accepted)+len(rejected)+excluded)
    else:m.update(input=len(accepted)+len(rejected),excluded=0,balanced=True)
    output=[]
    for row in rows:
        expected=Decimal(str(row.get("expected","0")));reported=Decimal(str(row.get("reported","0")))
        output.append({**row,"difference":str(expected-reported),"status":"通过" if expected==reported else "差异"})
    m.update(expected_total=str(sum((Decimal(str(r.get("expected","0"))) for r in rows),Decimal(0))),reported_total=str(sum((Decimal(str(r.get("reported","0"))) for r in rows),Decimal(0))),differences=sum(r["status"]=="差异" for r in output))
    result={"rows":output,"quarantine":[],"metrics":m}
    if lineage: result["dispositions"]=lineage["dispositions"]
    return result
