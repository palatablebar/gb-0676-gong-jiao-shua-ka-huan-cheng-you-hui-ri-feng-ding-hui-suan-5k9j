import time
from app.config import ROOT,MODULES
from app.errors import DomainError
from app.values import scalar
from app.manifest import digest,manifest
from app import store
from app.lineage import reconcile
from app.modules.m1_taps.rules import evaluate as stage1
from app.modules.m2_routes.rules import evaluate as stage2
from app.modules.m3_fares.rules import evaluate as stage3
from app.modules.m4_journeys.rules import evaluate as stage4
from app.modules.m5_discounts.rules import evaluate as stage5
from app.modules.m6_clearing.rules import evaluate as stage6
from app.modules.m7_settlement.rules import evaluate as stage7
STAGES=[stage1,stage2,stage3,stage4,stage5,stage6,stage7]

def load_sample(name):
    if name not in {"dirty.csv","clean.csv","legacy.csv"}: raise DomainError("BAD_SAMPLE","样例不存在",404)
    return (ROOT/"sample_data"/name).read_bytes()

def calculate(raw,params=None,stop=6,parts=None,source=None):
    params=params or {}
    started=time.monotonic()
    context={"parameters":params,"raw":raw,"quarantine":[],"parts":parts or []}
    if source is not None: context["source"]=source
    stages=[];rows=[];lineage=None
    for index,stage in enumerate(STAGES[:stop+1]):
        if index==6:
            # 封存前必须具备每条来源记录的逐条去向；缺席即拒绝，不生成新版本。
            lineage=context["lineage"]=reconcile(context.get("intake"),context["quarantine"],rows)
        result=stage(raw if index==0 else rows,context)
        result=scalar(result);rows=result["rows"]
        for item in result.get("quarantine",[]): item.setdefault("_stage",MODULES[index][0])
        context["quarantine"].extend(result.get("quarantine",[]))
        if index==0:
            context["intake"]={**result["metrics"],"dispositions":result.get("dispositions",[])}
            # 去向明细只在采信上下文与清分结果中各保留一份，避免重复放大批次载荷。
            result.pop("dispositions",None)
        result["cumulative_quarantine"]=list(context["quarantine"])
        context[MODULES[index][0]]=result
        stages.append(result)
    if stop>=5 and lineage is None:
        lineage=reconcile(context.get("intake"),context["quarantine"],stages[5]["rows"])
    meta=manifest(raw,params,started)
    if parts: meta["parts"]=parts
    if source is not None: meta["source"]=source
    meta["lineage"]={"expected_records":(lineage or {}).get("expected_records",0),
                     "complete":bool((lineage or {}).get("complete")),"conflicts":(lineage or {}).get("conflicts",[])}
    return {"run_id":digest(raw,params,source)[:20],"stages":stages,"manifest":meta,"parameters":params}

def execute(raw,params=None,parts=None,source=None):
    result=calculate(raw,params,parts=parts,source=source)
    # 只有完整算完才落库；INSERT OR IGNORE 保留同一来源的上一完整版本。
    return store.save(result["run_id"],result,source)

def finalize_source(source):
    raw,parts=store.assemble(source)
    stored=store.get_source_params(source)
    return execute(raw,stored,parts=parts,source=source)

def stage_preview(index,payload):
    if "rows" in payload and index>0:
        if not isinstance(payload["rows"],list) or any(not isinstance(row,dict) for row in payload["rows"]): raise DomainError("BAD_ROWS","记录需要对象列表")
        if not isinstance(payload.get("context",{}),dict): raise DomainError("BAD_CONTEXT","上下文需要对象")
        return scalar(STAGES[index](payload["rows"],payload.get("context",{"parameters":{},"quarantine":[]})))
    raw=payload.get("csv")
    raw=raw.encode() if isinstance(raw,str) else load_sample(payload.get("sample","dirty.csv"))
    return calculate(raw,payload.get("parameters",{}),index)["stages"][-1]
