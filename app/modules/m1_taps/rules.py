import csv,io
from app.config import COLUMNS
from app.errors import DomainError
from app.reasons import reject

class TrackedLines:
    """按物理行喂给 csv，同时记录每条逻辑记录消费了哪些物理行。"""
    def __init__(self,text):
        self.stream=io.StringIO(text,newline="");self.line_num=0;self.consumed=[]
    def __iter__(self): return self
    def __next__(self):
        line=self.stream.readline()
        if not line: raise StopIteration
        self.line_num+=1;self.consumed.append(self.line_num);return line

def decode(raw):
    for encoding in ("utf-8-sig","gb18030"):
        try: return raw.decode(encoding),encoding
        except UnicodeDecodeError: continue
    raise DomainError("ENCODING","无法识别文件编码")

def line_offsets(raw):
    offsets=[0]
    for index,byte in enumerate(raw):
        if byte==10: offsets.append(index+1)
    return offsets

def part_of(parts,offsets,line):
    """来源物理行起始字节落入哪个上传分块；分块只是传输边界。"""
    if not parts: return None
    index=line-1
    offset=offsets[index] if 0<=index<len(offsets) else len(offsets) and offsets[-1]
    for item in parts:
        if item["start"]<=offset<item["end"]: return item["part"]
    return parts[-1]["part"] if offset>=parts[-1]["start"] else parts[0]["part"]

def evaluate(raw,context=None):
    context=context or {}
    text,encoding=decode(raw)
    if not text: raise DomainError("EMPTY_FILE","文件为空")
    if not text.strip(): raise DomainError("BLANK_ONLY","全部为空行")
    parts=context.get("parts") or []
    offsets=line_offsets(raw) if parts else []
    stream=TrackedLines(text);reader=csv.reader(stream);header=next(reader,None)
    if header!=COLUMNS: raise DomainError("BAD_HEADER","表头不匹配")
    rows=[];bad=[];dispositions=[];seen={}
    duplicate=blank=repeated=count=0
    def tracked(cells,start_line,end_line,kind,**extra):
        record=len(dispositions)+1
        item={"record":record,"start_line":start_line,"end_line":end_line,
              "part":part_of(parts,offsets,start_line),"part_end":part_of(parts,offsets,end_line),"kind":kind,
              "raw":cells,"reason":"","detail":""}
        item.update(extra);dispositions.append(item);return item
    try:
        while True:
            stream.consumed=[];cells=next(reader,None)
            if cells is None: break
            count+=1
            start_line=stream.consumed[0] if stream.consumed else stream.line_num
            end_line=stream.consumed[-1] if stream.consumed else stream.line_num
            line=end_line
            if not cells or not any(c.strip() for c in cells):
                blank+=1;tracked(cells,start_line,end_line,"blank",reason="BLANK_ROW",detail="空白行")
                continue
            if cells==header:
                repeated+=1;tracked(cells,start_line,end_line,"repeated_header",reason="REPEATED_HEADER",detail="分段表头")
                continue
            row={"_record":len(dispositions)+1,"_line":line,"_start_line":start_line,"_end_line":end_line,
                 "_part":part_of(parts,offsets,start_line),"_part_end":part_of(parts,offsets,end_line),
                 "_sources":[line],"_raw":cells}
            if len(cells)!=len(header):
                bad.append(reject(row,"BAD_COLUMNS","列数不匹配"))
                tracked(cells,start_line,end_line,"quarantine",reason="BAD_COLUMNS",detail="列数不匹配")
                continue
            row.update(dict(zip(header,[x.strip() for x in cells])))
            if not row[header[0]]:
                bad.append(reject(row,"EMPTY_VALUE","业务键为空"))
                tracked(cells,start_line,end_line,"quarantine",reason="EMPTY_VALUE",detail="业务键为空")
                continue
            key=row[header[0]]
            if key in seen:
                previous=seen[key]
                if cells==previous["_raw"]:
                    duplicate+=1;tracked(cells,start_line,end_line,"duplicate",reason="DUPLICATE_EXACT",detail="与首条完全相同")
                else:
                    bad.append(reject(row,"DUPLICATE_CONFLICT","同键不同值"))
                    tracked(cells,start_line,end_line,"quarantine",reason="DUPLICATE_CONFLICT",detail="同键不同值")
                continue
            seen[key]=row;rows.append(row)
            tracked(cells,start_line,end_line,"accepted")
    except csv.Error: raise DomainError("BAD_CSV","引号未闭合或文件损坏")
    if count==0: raise DomainError("HEADER_ONLY","仅有表头")
    if not rows and not bad: raise DomainError("BLANK_ONLY","全部为空行")
    accepted=sum(1 for d in dispositions if d["kind"]=="accepted")
    if accepted!=len(rows) or len(dispositions)!=count:
        raise DomainError("LINEAGE_INCOMPLETE","采信去向与输入记录数不一致")
    return {"rows":rows,"quarantine":bad,
            "dispositions":dispositions,
            "metrics":{"input":count,"accepted":len(rows),"quarantine":len(bad),"duplicate":duplicate,
                       "blank":blank,"repeated_headers":repeated,"encoding":encoding}}
