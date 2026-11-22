import csv,io
from decimal import Decimal
from app.modules.m5_discounts.rules import card_days

COLUMNS=["run_id","input_sha256","rule_version","source","card","business_day","events","fare_versions",
         "source_lines","parts","location","base_total","transfer_hits","transfer_discount",
         "capped_events","cap_discount","expected","reported","difference","status",
         "credential","transfer_basis","cap_basis","lineage_complete"]

def build_card_day_csv(run):
    """可发布的卡日结算：一行一个卡日，带凭证、换乘/封顶依据、处理位置与来源摘要。"""
    meta=run["manifest"];rows=run["stages"][4]["rows"]
    stream=io.StringIO(newline="");writer=csv.writer(stream)
    writer.writerow(COLUMNS)
    for day in card_days(rows,run.get("parameters")):
        writer.writerow([run["run_id"],meta["input_sha256"],meta["rule_version"],meta.get("source",""),
                         day["card"],day["business_day"],len(day["events"]),"/".join(day["fare_versions"]),
                         ",".join(str(x) for x in day["source_lines"]),",".join(day["parts"]),day["location"],
                         day["base_total"],day["transfer_hits"],day["transfer_discount"],
                         day["capped_events"],day["cap_discount"],day["expected"],day["reported"],
                         day["difference"],day["status"],day["receipts"],day["transfer_basis"],day["cap_basis"],
                         "是" if meta.get("lineage",{}).get("complete") else "否"])
    total=sum((Decimal(day["expected"]) for day in card_days(rows,run.get("parameters"))),Decimal(0))
    writer.writerow(["合计","","","","","","","","","","","","","","",str(total),"","","","","","","",
                     "是" if meta.get("lineage",{}).get("complete") else "否"])
    return "﻿"+stream.getvalue()
