REASONS={
 "BAD_COLUMNS":"列数不匹配","EMPTY_VALUE":"必填值为空","INVALID_NUMBER":"数字格式错误",
 "INVALID_TIME":"时间缺少偏移或格式错误","DUPLICATE_CONFLICT":"同键取值冲突",
 "UNKNOWN_REFERENCE":"引用不存在","STALE_VERSION":"版本已更新","EMPTY_FILE":"文件为空",
 "HEADER_ONLY":"仅有表头","BLANK_ONLY":"全部为空行","DUPLICATE_EXACT":"完全相同重复行",
 "BLANK_ROW":"空白行","REPEATED_HEADER":"分段表头","LINEAGE_INCOMPLETE":"来源行缺少逐条去向",
 "LINEAGE_OVERLAP":"同一来源行被重复裁决","SOURCE_CONFLICT":"同一来源分块内容不一致",
 "CHUNK_INCOMPLETE":"来源分块尚未收齐","EMPTY_PART":"分块为空","TOO_MANY_PARTS":"分块数量超限",
 "SOURCE_TOO_LARGE":"来源总量超过上限","BAD_CHUNK":"分块编号或数量无效",
}
def reject(row, code, detail):
    return {**row,"reason":code,"detail":detail}
def sources(row):
    return row.get("_sources", [row.get("_line",0)])
