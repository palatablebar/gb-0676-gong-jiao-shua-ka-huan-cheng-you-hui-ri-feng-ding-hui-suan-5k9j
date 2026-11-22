from decimal import Decimal
from app.values import number,instant,money
from app.errors import DomainError

def _minutes(value):
    text=value.quantize(Decimal("0.01")).normalize()
    return format(text,"f")

def evaluate(rows,context):
    params=context.get("parameters",{});cap=number(params.get("daily_cap","6.00"));off=number(params.get("transfer_discount","1.00"));window=number(params.get("transfer_minutes","60"))
    if cap<0 or off<0 or window<0:raise DomainError("BAD_DISCOUNT","优惠参数不能为负")
    spent={};anchor={};good=[]
    # 同一卡日整体归集后再排序，分块顺序不影响换乘锚点与封顶累计。
    for row in sorted(rows,key=lambda r:(r["card"],r["business_day"],instant(r["at"]),r["event_id"])):
        key=(row["card"],row["business_day"]);base=number(row["base_fare"]);previous=anchor.get(key);eligible=False
        delta=None;before=spent.get(key,Decimal(0));remaining=max(Decimal(0),cap-before)
        if previous:
            delta=Decimal(str((instant(row["at"])-instant(previous["at"])).total_seconds()))/60
            eligible=previous["route"]!=row["route"] and Decimal(0)<=delta<window
        if not previous:
            transfer_basis="本卡日本笔之前无有效付费锚点（首笔、失败或零扣费行程不延长锚点）"
        elif previous["route"]==row["route"]:
            transfer_basis=f"前次 {previous['event_id']} 同为线路 {previous['route']}，距 {_minutes(delta)} 分钟；同线路不优惠"
        elif delta>=window:
            transfer_basis=f"前次 {previous['event_id']} 线路 {previous['route']}，距 {_minutes(delta)} 分钟 ≥ 换乘窗 {_minutes(window)} 分钟；截止点排除"
        else:
            transfer_basis=f"前次 {previous['event_id']} 线路 {previous['route']}，距 {_minutes(delta)} 分钟 < 换乘窗 {_minutes(window)} 分钟且线路不同；触发换乘"
        transfer=min(base,off) if eligible else Decimal(0)
        after_transfer=base-transfer;charge=min(after_transfer,remaining)
        cap_discount=after_transfer-charge;spent[key]=before+charge
        if after_transfer<=remaining:
            cap_basis=f"日累计 {money(before)}，封顶余 {money(remaining)}，本笔 {money(after_transfer)} 全额计入；未触顶"
        else:
            cap_basis=f"日累计 {money(before)}，封顶余 {money(remaining)}，本笔 {money(after_transfer)} 仅计 {money(charge)}，封顶减免 {money(cap_discount)}"
        part=row.get("_part");part_end=row.get("_part_end",part);start=row.get("_start_line");end=row.get("_end_line")
        lines=f"{start or row.get('_line','—')}"+(f"-{end}" if end and end!=start else "")
        if part is None:location=f"整包 · 行 {lines}"
        elif part_end is not None and part_end!=part:location=f"分块 {part}→{part_end} · 行 {lines} · 记录 {row.get('_record','—')}"
        else:location=f"分块 {part} · 行 {lines} · 记录 {row.get('_record','—')}"
        good.append({**row,
            "credential":f"{row.get('fare_version','未标注票价版')} · 基础 {money(base)} · {row['at']}",
            "anchor_event":previous["event_id"] if previous else "—",
            "anchor_at":previous["at"] if previous else "—",
            "anchor_route":previous["route"] if previous else "—",
            "window_minutes":_minutes(delta) if delta is not None else "—",
            "transfer_basis":transfer_basis,
            "cap_before":money(before),
            "cap_remaining_before":money(remaining),
            "cap_basis":cap_basis,
            "location":location,
            "transfer_anchor":previous["event_id"] if eligible else "—",
            "transfer_discount":money(transfer),"cap_discount":money(cap_discount),
            "expected":money(charge),"day_paid":money(spent[key])})
        if charge>0:anchor[key]=row
    return {"rows":good,"quarantine":[],"metrics":{"expected_total":money(sum((number(r["expected"]) for r in good),Decimal(0))),"daily_caps":len(spent),"transfer_hits":sum(r["transfer_anchor"]!="—" for r in good)}}

def card_days(rows,params=None):
    """按卡号+业务日归集结算凭据，供复核页沿超限日批核对。"""
    cap_limit=number((params or {}).get("daily_cap","6.00"));groups={}
    for row in sorted(rows,key=lambda r:(r["card"],r["business_day"],instant(r["at"]),r["event_id"])):
        groups.setdefault((row["card"],row["business_day"]),[]).append(row)
    days=[]
    for (card,day),items in sorted(groups.items()):
        expected=sum((Decimal(str(r["expected"])) for r in items),Decimal(0))
        reported=sum((Decimal(str(r["reported"])) for r in items),Decimal(0))
        transfer=sum((Decimal(str(r["transfer_discount"])) for r in items),Decimal(0))
        capped_total=sum((Decimal(str(r["cap_discount"])) for r in items),Decimal(0))
        parts=sorted({str(r.get("_part")) for r in items if r.get("_part") is not None},key=lambda x:int(x))
        versions=sorted({r.get("fare_version","") for r in items})
        lines=sorted({x for r in items for x in r.get("_sources",[])})
        ranges=[]
        for r in items:
            start=r.get("_start_line") or r.get("_line");end=r.get("_end_line") or start
            text=str(start) if end in (None,start) else f"{start}-{end}"
            if text not in ranges: ranges.append(text)
        hits=[r for r in items if r.get("transfer_anchor")!="—"]
        capped=[r for r in items if Decimal(str(r.get("cap_discount","0")))>0]
        transfer_basis=(f"触发 {len(hits)} 次：{'、'.join(r['event_id'] for r in hits)}；其余按同线路或无锚点不优惠"
                        if hits else "本卡日无换乘优惠（首笔 / 同线路 / 锚点间隔≥换乘窗）")
        cap_basis=(f"封顶减免 {len(capped)} 笔：{'、'.join(r['event_id'] for r in capped)}；日累计只计 {money(expected)}"
                   if capped else f"日累计 {money(expected)}，未触顶 {money(cap_limit)}")
        days.append({
            "card":card,"business_day":day,
            "receipts":"、".join(f"{v} 票价版" for v in versions),
            "fare_versions":versions,
            "source_lines":lines,"parts":parts,
            "location":(f"分块 {','.join(parts)} · 行 {','.join(ranges)}" if parts
                        else f"整包 · 行 {','.join(ranges)}"),
            "transfer_basis":transfer_basis,
            "cap_basis":cap_basis,
            "transfer_hits":len(hits),"capped_events":len(capped),
            "transfer_discount":money(transfer),"cap_discount":money(capped_total),
            "base_total":money(sum((Decimal(str(r["base_fare"])) for r in items),Decimal(0))),
            "expected":money(expected),"reported":money(reported),
            "difference":money(expected-reported),
            "status":"通过" if expected==reported else "差异",
            "events":[{"event_id":r["event_id"],"route":r["route"],"at":r["at"],
                       "credential":r["credential"],"transfer_basis":r["transfer_basis"],
                       "cap_basis":r["cap_basis"],"location":r["location"],
                       "transfer_discount":r["transfer_discount"],"cap_discount":r["cap_discount"],
                       "expected":r["expected"],"reported":r["reported"],"day_paid":r["day_paid"]} for r in items]})
    return days
