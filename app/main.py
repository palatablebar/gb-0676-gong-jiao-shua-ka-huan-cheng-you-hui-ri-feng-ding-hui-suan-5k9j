from flask import Flask,jsonify,request
from app.config import MODULES,MAX_UPLOAD_BYTES,MAX_PARTS
from app.errors import DomainError
from app import pipeline,store
from app.web import register_pages
import importlib,json

def _positive(name,value,limit):
    if not isinstance(value,int) or isinstance(value,bool) or not 1<=value<=limit:
        raise DomainError("BAD_CHUNK",f"{name} 必须是 1..{limit} 的整数")
    return value

def _source(name):
    if not isinstance(name,str) or not name.strip() or len(name)>128:
        raise DomainError("BAD_SOURCE","来源标识需要 1..128 个字符")
    return name.strip()

def create_app():
    application=Flask(__name__,template_folder="templates",static_folder="static")
    application.config["MAX_CONTENT_LENGTH"]=MAX_UPLOAD_BYTES+64*1024
    @application.errorhandler(DomainError)
    def domain_error(error): return jsonify({"code":error.code,"message":error.message}),error.status
    @application.errorhandler(KeyError)
    @application.errorhandler(TypeError)
    @application.errorhandler(ValueError)
    def invalid_shape(error): return jsonify({"code":"INVALID_INPUT","message":"字段或参数无效，请核对输入"}),422
    @application.errorhandler(413)
    def too_large(error): return jsonify({"code":"TOO_LARGE","message":f"单次上传超过{MAX_UPLOAD_BYTES//1024//1024}MB，请改走分块上传"}),413
    @application.errorhandler(500)
    def internal(error): return jsonify({"code":"INTERNAL","message":"处理中断，上一完整版本保留"}),500
    @application.get("/healthz")
    def health(): return {"status":"ok"}
    @application.post("/api/runs")
    def runs():
        payload=request.get_json(silent=True)
        if not isinstance(payload,dict): raise DomainError("BAD_BODY","请求需要对象")
        params=payload.get("parameters",{})
        if not isinstance(params,dict): raise DomainError("BAD_PARAMETERS","参数需要对象")
        raw=payload.get("csv")
        if raw is not None and not isinstance(raw,str): raise DomainError("BAD_CSV","CSV需要文本")
        return pipeline.execute(raw.encode() if raw is not None else pipeline.load_sample(payload.get("sample","dirty.csv")),params)
    @application.post("/api/upload")
    def upload():
        file=request.files.get("file")
        if not file: raise DomainError("NO_FILE","请选择CSV文件")
        data=file.read()
        if len(data)>MAX_UPLOAD_BYTES: raise DomainError("TOO_LARGE",f"单个文件超过{MAX_UPLOAD_BYTES//1024//1024}MB，请改走 /api/sources/<source>/parts/<n> 分块上传",413)
        return pipeline.execute(data)
    @application.post("/api/sources/<source>/parts/<int:part>")
    def put_part(source,part):
        source=_source(source);part=_positive("part",part,MAX_PARTS)
        params=request.form.get("params") or "{}"
        try: params=json.loads(params)
        except ValueError: raise DomainError("BAD_PARAMETERS","参数需要JSON对象")
        if not isinstance(params,dict): raise DomainError("BAD_PARAMETERS","参数需要对象")
        parts=request.form.get("parts")
        if parts is not None:
            try: parts=int(parts)
            except ValueError: raise DomainError("BAD_CHUNK","分块总数需要整数")
        else: parts=_positive("parts",part,MAX_PARTS)
        _positive("parts",parts,MAX_PARTS)
        if part>parts: raise DomainError("BAD_CHUNK",f"part {part} 超出分块总数 {parts}")
        file=request.files.get("file")
        if file is None: raise DomainError("NO_FILE","请选择该分块的CSV内容")
        raw=file.read()
        if not raw: raise DomainError("EMPTY_PART","分块为空")
        if len(raw)>MAX_UPLOAD_BYTES: raise DomainError("TOO_LARGE",f"单个分块超过{MAX_UPLOAD_BYTES//1024//1024}MB，请继续拆分",413)
        status=store.put_part(source,part,parts,raw,params)
        return status
    @application.get("/api/sources/<source>")
    def get_source(source): return store.source_status(_source(source))
    @application.post("/api/sources/<source>/finalize")
    def finalize(source):
        source=_source(source)
        return pipeline.finalize_source(source)
    @application.get("/api/sources/<source>/runs")
    def source_history(source): return {"source":_source(source),"runs":store.source_runs(source)}
    @application.get("/api/runs")
    def history(): return {"runs":store.history()}
    @application.get("/api/runs/<run_id>")
    def run_detail(run_id): return store.get(run_id)
    @application.post("/api/runs/<run_id>/review")
    def review(run_id):
        p=request.get_json(silent=True) or {}
        if not isinstance(p.get("version"),int): raise DomainError("BAD_VERSION","请提供版本号")
        return store.review(run_id,p["version"],p.get("decision"))
    @application.get("/api/runs/<run_id>/settlement")
    def settlement(run_id):
        from app.settlement import build_card_day_csv
        return application.response_class(build_card_day_csv(store.get(run_id)),mimetype="text/csv",headers={"Content-Disposition":'attachment; filename="card-day-settlement.csv"'})
    @application.get("/api/runs/<run_id>/archive")
    def archive(run_id):
        from app.archive import build_archive
        run=store.get(run_id)
        lineage=run.get("manifest",{}).get("lineage")
        if not lineage:
            raise DomainError("LINEAGE_INCOMPLETE","该批次为旧版，无逐条去向，请按当前规则重算后再导出封存证据",409)
        if not lineage.get("complete"):
            raise DomainError("LINEAGE_INCOMPLETE","来源行缺少逐条去向，不能导出封存证据",409)
        return application.response_class(build_archive(run),mimetype="text/csv",headers={"Content-Disposition":'attachment; filename="evidence.csv"'})
    for index,(slug,title) in enumerate(MODULES,1):
        module=importlib.import_module(f"app.modules.m{index}_{slug}.handler")
        application.register_blueprint(module.bp)
    register_pages(application)
    return application
app=create_app()
if __name__=="__main__": app.run(host="0.0.0.0",port=8000,threaded=True)
