import hashlib,json
from app.errors import DomainError
from app.reasons import sources

def evaluate(rows,context):
    stages=[v for v in context.values() if isinstance(v,dict) and "metrics" in v]
    balances=[s["metrics"]["balanced"] for s in stages if "balanced" in s["metrics"]]
    if balances and not all(balances): raise DomainError("UNBALANCED","来源行未对平，不能归档")
    lineage=context.get("lineage") or {}
    # 完整流水线必须带逐条去向；直接以 rows 预览的阶段没有来源行，不做封存承诺。
    if "intake" in context and not lineage.get("complete"):
        missing=len(lineage.get("missing",[]));conflicts=len(lineage.get("conflicts",[]))
        raise DomainError("LINEAGE_INCOMPLETE",f"来源行缺少逐条去向（缺 {missing} 条、冲突 {conflicts} 条），不能封存")
    ids=[str(r.get("event_id",r.get("_line",""))) for r in rows]
    if len(ids)!=len(set(ids)): raise DomainError("ARCHIVE_DUPLICATE","归档业务键重复")
    encoded=json.dumps(rows,ensure_ascii=False,sort_keys=True,default=str).encode()
    return {"rows":rows,"quarantine":[],"metrics":{"records":len(rows),
        "source_lines":len(set(x for row in rows for x in sources(row))),
        "dispositions":len(lineage.get("dispositions",[])),
        "lineage_complete":bool(lineage.get("complete",True)),
        "sha256":hashlib.sha256(encoded).hexdigest(),"ready":True,
        "differences":sum(r.get("status")=="差异" for r in rows)}}
