from flask import render_template
from app.config import MODULES,TITLE,SHORT,MAX_UPLOAD_BYTES,MAX_PARTS
from app.pipeline import execute,load_sample
from app.modules.m5_discounts.rules import card_days
from app import store

def register_pages(app):
    def page(index,page_title=None,nav_index=None):
        run=store.latest() or execute(load_sample("dirty.csv"))
        stage=run["stages"][index]
        rows=stage["rows"]
        choices=[['event_id','card','route','event_time','result','reported'],['event_id','card','route','line_group'],['event_id','card','fare_version','base_fare','reported','at'],['journey','card','route','business_day','at'],['event_id','card','route','base_fare','transfer_anchor','transfer_discount','cap_discount','expected','day_paid'],['event_id','card','expected','reported','difference','status'],['event_id','card','expected','reported','status']]
        columns=choices[index]
        labels={'event_id':'事件','card':'卡号','route':'线路','event_time':'刷卡时间','result':'刷卡状态','reported':'实扣 / 元','line_group':'线路组','fare_version':'票价版','base_fare':'基础票价','at':'事件时间 UTC','journey':'行程编号','business_day':'业务日','transfer_anchor':'锚点','transfer_discount':'换乘优惠','cap_discount':'封顶减免','expected':'应扣 / 元','day_paid':'日累计','difference':'差额 / 元','status':'结论','accepted':'采纳行','versions':'版本','expected_total':'应扣总额','daily_caps':'卡日数量','transfer_hits':'换乘次数','input':'输入行','quarantine':'隔离行','duplicate':'重复行','blank':'空白行','repeated_headers':'重复表头','encoding':'编码','routes':'线路数','cards':'卡数','journeys':'行程数','records':'记录数','source_lines':'来源行数','sha256':'摘要','ready':'可归档','differences':'差异项','lineage_complete':'逐条去向完整','dispositions':'去向记录','part':'分块','location':'处理位置','credential':'凭证','transfer_basis':'换乘依据','cap_basis':'封顶依据','cap_before':'封顶前日累计','cap_remaining_before':'封顶余额','anchor_event':'前次锚点','anchor_route':'锚点线路','window_minutes':'间隔 / 分钟','lineage_accepted':'去向·采纳','lineage_quarantine':'去向·隔离','lineage_excluded':'去向·排除','lineage_missing':'去向·缺失','lineage_conflicts':'去向·冲突','received':'已收分块','received_count':'已收块数','missing':'缺少分块','bytes':'来源字节','source':'来源','parts':'分块数','status':'状态','updated_at':'更新时间','part_digests':'分块摘要'}
        for key,label in {'accepted_inputs': '采纳来源行', 'quarantine_inputs': '隔离来源行', 'output_records': '结果记录', 'input': '输入行', 'excluded': '排除行', 'balanced': '行数平衡', 'expected_total': '预期合计', 'reported_total': '申报合计', 'differences': '差异项', 'blank': '空行', 'repeated_headers': '分段表头', 'encoding': '编码', 'duplicate': '重复行', 'quarantine': '隔离行', 'accepted': '采纳行', 'sha256': '校验摘要', 'ready': '可归档', 'lineage_missing': '去向缺失', 'lineage_conflicts': '去向冲突', 'lineage_accepted': '去向·采纳', 'lineage_quarantine': '去向·隔离', 'lineage_excluded': '去向·排除'}.items(): labels.setdefault(key,label)
        days=card_days(rows,run.get("parameters")) if index>=4 else []
        return render_template(f"m{index+1}.html",title=TITLE,short=SHORT,modules=MODULES,index=index,run=run,stage=stage,rows=rows,columns=columns[:12],history=store.history(),labels=labels,days=days,max_upload=MAX_UPLOAD_BYTES,max_parts=MAX_PARTS,
                       lineage=run.get("manifest",{}).get("lineage"),parameters=run.get("parameters") or {},
                       page_title=page_title,nav_index=index if nav_index is None else nav_index)
    def batches():
        run=store.latest() or execute(load_sample("dirty.csv"))
        days=card_days(run["stages"][5]["rows"],run.get("parameters"))
        sources=store.all_sources()
        return render_template("batches.html",title=TITLE,short=SHORT,modules=MODULES,index=4,nav_index=7,run=run,
                               page_title="批次复核（超限日批）",
                               stage=run["stages"][5],rows=run["stages"][5]["rows"],columns=[],history=store.history(),
                               labels={'card':'卡号','business_day':'业务日','receipts':'凭证','transfer_basis':'换乘依据','cap_basis':'封顶依据','location':'处理位置','expected':'应扣 / 元','reported':'实扣 / 元','difference':'差额','status':'结论','transfer_hits':'换乘次数','capped_events':'封顶笔数','transfer_discount':'换乘优惠','cap_discount':'封顶减免','source':'来源','parts':'分块数','received':'已收分块','missing':'缺少分块','bytes':'字节','run_id':'批次','complete':'收齐','status':'状态','updated_at':'更新时间','part':'分块','sha256':'摘要','received_at':'收块时间'},
                               days=days,sources=sources,max_upload=MAX_UPLOAD_BYTES,max_parts=MAX_PARTS,
                               lineage=run.get("manifest",{}).get("lineage"),parameters=run.get("parameters") or {})
    app.add_url_rule("/",view_func=lambda:page(4))
    app.add_url_rule("/batches",endpoint="batches",view_func=batches)
    for index,(slug,name) in enumerate(MODULES):
        app.add_url_rule("/"+slug,endpoint="page_"+slug,view_func=lambda index=index:page(index))
