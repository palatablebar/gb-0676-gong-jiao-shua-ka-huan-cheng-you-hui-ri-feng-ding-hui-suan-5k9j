import csv,io,json

def build_archive(run):
    """唯一证据导出：每条来源记录一行，带逐条去向、处理位置与结算凭据。"""
    stream=io.StringIO(newline="");writer=csv.writer(stream)
    writer.writerow(["run_id","input_sha256","rule_version","kind","record","line_range","part","location",
                     "reason","detail","credential","transfer_basis","cap_basis","expected","reported","source","evidence"])
    meta=run["manifest"];source=meta.get("source") or ""
    lineage=run["stages"][5].get("dispositions") or []
    final={row.get("_record"):row for row in run["stages"][-1]["rows"]}
    quarantine={q.get("_record"):q for q in run["stages"][-1].get("cumulative_quarantine",[])}
    parts={p["part"]:p for p in meta.get("parts",[])}
    for item in lineage:
        record=item["record"];part=item.get("part");part_end=item.get("part_end",part)
        lines=f"{item.get('start_line')}-{item.get('end_line')}"
        if part is None: location=f"整包 · 行 {lines}"
        elif part_end is not None and part_end!=part: location=f"分块 {part}→{part_end} · 行 {lines}"
        else: location=f"分块 {part} · 行 {lines}"
        part_label=f"{part}→{part_end}" if part is not None and part_end not in (None,part) else (part or "")
        row=final.get(record);q=quarantine.get(record)
        writer.writerow([run["run_id"],meta["input_sha256"],meta["rule_version"],item.get("kind",""),
                         record,json.dumps({"start":item.get("start_line"),"end":item.get("end_line")}),part_label,location,
                         item.get("reason",""),item.get("detail",""),
                         (row or {}).get("credential",""),
                         (row or {}).get("transfer_basis",(q or {}).get("detail","")),
                         (row or {}).get("cap_basis",""),
                         (row or {}).get("expected",(q or {}).get("reason","")),
                         (row or {}).get("reported",""),source,
                         json.dumps({"raw":item.get("raw",[]),"record":row or q or item},ensure_ascii=False)])
    writer.writerow([run["run_id"],meta["input_sha256"],meta["rule_version"],"source","","","","",
                     "","","","","","","",source,
                     json.dumps({k:meta.get(k) for k in ("parameters","generated_at","elapsed_ms","parts","lineage")},ensure_ascii=False)])
    return "﻿"+stream.getvalue()
