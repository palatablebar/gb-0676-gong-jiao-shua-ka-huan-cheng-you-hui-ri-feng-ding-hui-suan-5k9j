import sqlite3,json,hashlib
from datetime import datetime,timezone
from app.config import DATA_DIR,MAX_SOURCE_BYTES
from app.errors import DomainError

TABLES=[
 "CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY,payload TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,decision TEXT NOT NULL DEFAULT '待复核',source TEXT)",
 "CREATE TABLE IF NOT EXISTS parts (source TEXT NOT NULL,part INTEGER NOT NULL,parts INTEGER NOT NULL,sha256 TEXT NOT NULL,payload BLOB NOT NULL,received_at TEXT NOT NULL,PRIMARY KEY(source,part))",
 "CREATE TABLE IF NOT EXISTS sources (source TEXT PRIMARY KEY,parts INTEGER NOT NULL,params TEXT NOT NULL,run_id TEXT,status TEXT NOT NULL DEFAULT 'uploading',updated_at TEXT NOT NULL)",
 "CREATE TABLE IF NOT EXISTS source_runs (source TEXT NOT NULL,run_id TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(source,run_id))",
]

def _now():
    return datetime.now(timezone.utc).isoformat()

def connect():
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(DATA_DIR/"records.db",timeout=20)
    db.execute("PRAGMA journal_mode=WAL")
    for statement in TABLES: db.execute(statement)
    columns={row[1] for row in db.execute("PRAGMA table_info(runs)")}
    if "source" not in columns: db.execute("ALTER TABLE runs ADD COLUMN source TEXT")
    return db

def save(run_id,payload,source=None):
    """只插入、不覆盖：同一批次重复计算保留首次完整结果及其复核状态。"""
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO runs(id,payload,source) VALUES (?,?,?)",(run_id,json.dumps(payload,ensure_ascii=False),source))
        if source is not None:
            now=_now()
            db.execute("INSERT OR IGNORE INTO source_runs(source,run_id,created_at) VALUES (?,?,?)",(source,run_id,now))
            db.execute("UPDATE sources SET run_id=?,status='sealed',updated_at=? WHERE source=?",(run_id,now,source))
    return get(run_id)

def has(run_id):
    with connect() as db: return db.execute("SELECT 1 FROM runs WHERE id=?",(run_id,)).fetchone() is not None

def get(run_id):
    with connect() as db: row=db.execute("SELECT payload,version,decision,source FROM runs WHERE id=?",(run_id,)).fetchone()
    if not row: raise DomainError("NOT_FOUND","批次不存在",404)
    return {**json.loads(row[0]),"version":row[1],"decision":row[2],"stored_source":row[3]}

def latest():
    with connect() as db: row=db.execute("SELECT id FROM runs ORDER BY rowid DESC LIMIT 1").fetchone()
    return get(row[0]) if row else None

def history():
    with connect() as db: return [{"run_id":i,"version":v,"decision":d,"source":s} for i,v,d,s in db.execute("SELECT id,version,decision,source FROM runs ORDER BY rowid DESC")]

def review(run_id,version,decision):
    if decision not in {"已复核","退回复核"}: raise DomainError("BAD_DECISION","复核状态无效")
    with connect() as db:
        cursor=db.execute("UPDATE runs SET version=version+1,decision=? WHERE id=? AND version=?",(decision,run_id,version))
        if cursor.rowcount!=1:
            if not db.execute("SELECT 1 FROM runs WHERE id=?",(run_id,)).fetchone(): raise DomainError("NOT_FOUND","批次不存在",404)
            raise DomainError("STALE_VERSION","版本已更新，请刷新",409)
    return get(run_id)

def put_part(source,part,total,payload,params):
    """按来源保存分块。同块同内容重试幂等；同块不同内容拒绝，绝不静默覆盖原始刷卡。"""
    sha=hashlib.sha256(payload).hexdigest();now=_now();params_text=json.dumps(params,sort_keys=True,ensure_ascii=False)
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO sources(source,parts,params,status,updated_at) VALUES (?,?,?,'uploading',?)",(source,total,params_text,now))
        row=db.execute("SELECT parts,params FROM sources WHERE source=?",(source,)).fetchone()
        if row[0]!=total: raise DomainError("BAD_CHUNK","分块总数与该来源已登记值不一致",409)
        if row[1]!=params_text: raise DomainError("SOURCE_CONFLICT","同一来源的参数不一致",409)
        if (db.execute("SELECT COALESCE(SUM(length(payload)),0) FROM parts WHERE source=?",(source,)).fetchone()[0]+len(payload))>MAX_SOURCE_BYTES:
            raise DomainError("SOURCE_TOO_LARGE",f"来源总量超过{MAX_SOURCE_BYTES//1024//1024}MB上限，请按业务键拆分来源",413)
        if part>total: raise DomainError("BAD_CHUNK",f"part {part} 超出分块总数 {total}")
        cursor=db.execute("INSERT OR IGNORE INTO parts(source,part,parts,sha256,payload,received_at) VALUES (?,?,?,?,?,?)",(source,part,total,sha,payload,now))
        if cursor.rowcount==0:
            existing=db.execute("SELECT sha256,parts FROM parts WHERE source=? AND part=?",(source,part)).fetchone()
            if existing[0]!=sha: raise DomainError("SOURCE_CONFLICT","同一来源同一分块内容不一致，原始分块已保留",409)
            if existing[1]!=total: raise DomainError("BAD_CHUNK","分块总数不一致",409)
            db.execute("UPDATE parts SET received_at=? WHERE source=? AND part=?",(now,source,part))
    return source_status(source)

def source_status(source):
    with connect() as db:
        row=db.execute("SELECT parts,params,run_id,status,updated_at FROM sources WHERE source=?",(source,)).fetchone()
        if not row: raise DomainError("NOT_FOUND","来源不存在",404)
        parts=db.execute("SELECT part,parts,sha256,length(payload),received_at FROM parts WHERE source=? ORDER BY part",(source,)).fetchall()
    total=row[0];received=[p[0] for p in parts];missing=[i for i in range(1,total+1) if i not in set(received)]
    return {"source":source,"parts":total,"received":received,"missing":missing,"received_count":len(received),
            "complete":not missing and len(received)==total,"bytes":sum(p[3] for p in parts),
            "run_id":row[2],"status":row[3],"updated_at":row[4],
            "part_digests":[{"part":p[0],"sha256":p[2],"bytes":p[3],"received_at":p[4]} for p in parts]}

def assemble(source):
    status=source_status(source)
    if not status["complete"]: raise DomainError("CHUNK_INCOMPLETE",f"分块未收齐，缺少 {status['missing']}",409)
    with connect() as db: rows=db.execute("SELECT part,payload,sha256,received_at FROM parts WHERE source=? ORDER BY part",(source,)).fetchall()
    raw=b"".join(r[1] for r in rows)
    for part,payload,sha,_ in rows:
        if hashlib.sha256(payload).hexdigest()!=sha: raise DomainError("SOURCE_CONFLICT",f"分块 {part} 校验失败，原始分块已保留",409)
    parts=[]
    start=0
    for part,payload,sha,received in rows:
        parts.append({"part":part,"start":start,"end":start+len(payload),"bytes":len(payload),"sha256":sha,"received_at":received})
        start+=len(payload)
    return raw,parts

def all_sources():
    """批次复核页需要看到尚未收齐的来源，而不只是已生成批次的来源。"""
    with connect() as db: names=[r[0] for r in db.execute("SELECT source FROM sources ORDER BY updated_at DESC")]
    result=[]
    for name in names:
        try: result.append(source_status(name))
        except DomainError: continue
    return result

def get_source_params(source):
    with connect() as db: row=db.execute("SELECT params FROM sources WHERE source=?",(source,)).fetchone()
    if not row: raise DomainError("NOT_FOUND","来源不存在",404)
    return json.loads(row[0])

def source_runs(source):
    with connect() as db: return [{"run_id":r,"created_at":t} for r,t in db.execute("SELECT run_id,created_at FROM source_runs WHERE source=? ORDER BY created_at",(source,))]
