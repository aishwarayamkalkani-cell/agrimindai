"""AgriMind AI — FastAPI application."""
import csv
import io
import json
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field, field_validator

from . import agro, evaluation, llm, rag
from .core import (DATA, SECRET_KEYS, ROOT, admin_user, all_settings, check_pw, current_user, execute, hash_pw, init_db,
                   jdump, log_query, make_token, row, rows, set_setting)
from .disease import disease_model

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("agrimind")
MAX_UPLOAD = 20 * 1024 * 1024

@asynccontextmanager
async def lifespan(_app):
    startup()
    yield


app = FastAPI(title="AgriMind AI", version="1.0.0", description="Agricultural advisory system using Grok (xAI) LLMs and RAG", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    # Allow embedding only by this site and the Hugging Face Spaces page (which shows the app in an iframe).
    resp.headers["Content-Security-Policy"] = "frame-ancestors 'self' https://huggingface.co"
    resp.headers["Referrer-Policy"] = "same-origin"
    return resp


def startup():
    init_db()
    t = time.time()
    rag.store.load()
    rag.seed_demo_documents()
    log.info("Knowledge base ready: %s chunks, embedder=%s (%.1fs)", rag.store.index.ntotal, rag.store.embedder.signature, time.time() - t)


async def read_upload(f: UploadFile):
    raw = await f.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "File too large (max 20 MB)")
    if not raw:
        raise HTTPException(400, "Empty file")
    return raw


# ======================================================================= auth
class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    language: str = "en"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


_attempts: dict = defaultdict(list)


@app.post("/api/auth/register")
def register(body: RegisterIn):
    if row("SELECT id FROM users WHERE email=?", (body.email.lower(),)):
        raise HTTPException(409, "An account with this email already exists")
    first = row("SELECT COUNT(*) n FROM users")["n"] == 0
    uid = execute("INSERT INTO users(email,name,password_hash,role,language,created_at) VALUES(?,?,?,?,?,?)",
                  (body.email.lower(), body.name.strip(), hash_pw(body.password), "admin" if first else "farmer",
                   body.language if body.language in rag.LANG_NAMES else "en", time.time()))
    u = row("SELECT id,email,name,role,language FROM users WHERE id=?", (uid,))
    return {"token": make_token(u), "user": u}


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request):
    key = f"{request.client.host if request.client else '-'}:{body.email.lower()}"
    _attempts[key] = [t for t in _attempts[key] if time.time() - t < 300]
    if len(_attempts[key]) >= 8:
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")
    u = row("SELECT * FROM users WHERE email=?", (body.email.lower(),))
    if not u or not check_pw(body.password, u["password_hash"]):
        _attempts[key].append(time.time())
        raise HTTPException(401, "Incorrect email or password")
    if not u["active"]:
        raise HTTPException(403, "This account has been disabled by an administrator")
    execute("UPDATE users SET last_login=? WHERE id=?", (time.time(), u["id"]))
    _attempts.pop(key, None)
    return {"token": make_token(u), "user": {k: u[k] for k in ("id", "email", "name", "role", "language")}}


@app.get("/api/auth/me")
def me(u=Depends(current_user)):
    return u


class ProfileIn(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=80)
    language: str | None = None
    current_password: str | None = None
    new_password: str | None = Field(None, min_length=8, max_length=128)


@app.patch("/api/auth/me")
def update_me(body: ProfileIn, u=Depends(current_user)):
    if body.name:
        execute("UPDATE users SET name=? WHERE id=?", (body.name.strip(), u["id"]))
    if body.language in rag.LANG_NAMES:
        execute("UPDATE users SET language=? WHERE id=?", (body.language, u["id"]))
    if body.new_password:
        full = row("SELECT password_hash FROM users WHERE id=?", (u["id"],))
        if not body.current_password or not check_pw(body.current_password, full["password_hash"]):
            raise HTTPException(400, "Current password is incorrect")
        execute("UPDATE users SET password_hash=? WHERE id=?", (hash_pw(body.new_password), u["id"]))
    return row("SELECT id,email,name,role,language FROM users WHERE id=?", (u["id"],))


# ======================================================================= system
@app.get("/api/health")
def health():
    return {"status": "ok", "llm": llm.provider_info(), "embedder": rag.store.embedder.info() if rag.store.embedder else None,
            "disease_model": disease_model.available(), "documents": row("SELECT COUNT(*) n FROM documents")["n"],
            "chunks": int(rag.store.index.ntotal) if rag.store.index else 0}


@app.get("/api/dashboard")
def dashboard(u=Depends(current_user)):
    mine = row("SELECT COUNT(*) n FROM query_logs WHERE user_id=?", (u["id"],))["n"]
    recent = rows("SELECT feature, query, created_at FROM query_logs WHERE user_id=? ORDER BY id DESC LIMIT 6", (u["id"],))
    convs = rows("SELECT id,title,updated_at FROM conversations WHERE user_id=? ORDER BY updated_at DESC LIMIT 5", (u["id"],))
    m = evaluation.classification_metrics()
    return {"my_queries": mine, "recent": recent, "conversations": convs, "season": agro.current_season(),
            "documents": row("SELECT COUNT(*) n FROM documents")["n"], "chunks": int(rag.store.index.ntotal),
            "llm": llm.provider_info(), "embedder": rag.store.embedder.info(),
            "disease_accuracy": m["disease"]["test_accuracy"] if m["disease"] else None,
            "crop_accuracy": m["crop"]["test_accuracy"] if m["crop"] else None}


# ======================================================================= chat
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = None
    language: str = "en"
    use_rag: bool = True


def _own_conv(cid, u):
    c = row("SELECT * FROM conversations WHERE id=?", (cid,))
    if not c or (c["user_id"] != u["id"]):
        raise HTTPException(404, "Conversation not found")
    return c


@app.get("/api/conversations")
def list_convs(u=Depends(current_user)):
    return rows("SELECT c.id, c.title, c.updated_at, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id=c.id) n "
                "FROM conversations c WHERE user_id=? ORDER BY updated_at DESC", (u["id"],))


@app.get("/api/conversations/{cid}")
def get_conv(cid: int, u=Depends(current_user)):
    c = _own_conv(cid, u)
    msgs = rows("SELECT id, role, content, citations, meta, created_at FROM messages WHERE conversation_id=? ORDER BY id", (cid,))
    for m in msgs:
        m["citations"] = json.loads(m["citations"] or "[]")
        m["meta"] = json.loads(m["meta"] or "{}")
    return {**c, "messages": msgs}


@app.delete("/api/conversations/{cid}")
def del_conv(cid: int, u=Depends(current_user)):
    _own_conv(cid, u)
    execute("DELETE FROM messages WHERE conversation_id=?", (cid,))
    execute("DELETE FROM conversations WHERE id=?", (cid,))
    return {"ok": True}


@app.post("/api/chat")
def chat(body: ChatIn, u=Depends(current_user)):
    now = time.time()
    if body.conversation_id:
        _own_conv(body.conversation_id, u)
        cid = body.conversation_id
    else:
        cid = execute("INSERT INTO conversations(user_id,title,created_at,updated_at) VALUES(?,?,?,?)",
                      (u["id"], body.message.strip()[:60], now, now))
    hist = [{"role": m["role"], "content": m["content"]} for m in
            rows("SELECT role, content FROM messages WHERE conversation_id=? ORDER BY id", (cid,))]
    execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,?,?,?)", (cid, "user", body.message, now))
    try:
        res = rag.answer(body.message, body.language, hist, mode="rag" if body.use_rag else "engineered")
    except llm.LLMUnavailable as e:
        log_query(u["id"], "chat", body.message, language=body.language, ok=False, error=str(e))
        raise HTTPException(503, str(e))
    meta = {"latency_ms": res["latency_ms"], "provider": res["provider"], "model": res["model"], "mode": res["mode"],
            "usage": res.get("usage"),
            "grounding": {k: v for k, v in res["grounding"].items() if k != "claims"}, "fallback": res.get("fallback", False)}
    mid = execute("INSERT INTO messages(conversation_id,role,content,citations,meta,created_at) VALUES(?,?,?,?,?,?)",
                  (cid, "assistant", res["text"], jdump(res["citations"]), jdump(meta), time.time()))
    execute("UPDATE conversations SET updated_at=? WHERE id=?", (time.time(), cid))
    log_query(u["id"], "chat", body.message, language=body.language, provider=res["provider"], model=res["model"],
              latency_ms=res["latency_ms"], n_sources=len(res["citations"]), groundedness=res["grounding"].get("groundedness"),
              ok=not res.get("fallback"), error=res.get("error"))
    return {"conversation_id": cid, "message": {"id": mid, "role": "assistant", "content": res["text"],
                                                "citations": res["citations"], "meta": meta}}


# ======================================================================= knowledge base
@app.get("/api/documents")
def list_docs(u=Depends(current_user)):
    return rows("SELECT d.*, u.name uploader FROM documents d LEFT JOIN users u ON u.id=d.uploaded_by ORDER BY d.id DESC")


@app.post("/api/documents")
async def upload_doc(file: UploadFile = File(...), u=Depends(current_user)):
    raw = await read_upload(file)
    try:
        d = rag.ingest(Path(file.filename or "upload.txt").name, raw, user_id=u["id"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001  (corrupt PDF/DOCX)
        raise HTTPException(400, f"Could not process file: {e}")
    log_query(u["id"], "upload", d["filename"])
    return d


@app.get("/api/documents/{doc_id}/chunks")
def doc_chunks(doc_id: int, u=Depends(current_user)):
    return rows("SELECT id, idx, page, text FROM chunks WHERE document_id=? ORDER BY idx", (doc_id,))


@app.delete("/api/documents/{doc_id}")
def delete_doc(doc_id: int, u=Depends(current_user)):
    d = row("SELECT * FROM documents WHERE id=?", (doc_id,))
    if not d:
        raise HTTPException(404, "Not found")
    if u["role"] != "admin" and d["uploaded_by"] != u["id"]:
        raise HTTPException(403, "You can only delete documents you uploaded")
    rag.delete_document(doc_id)
    return {"ok": True}


@app.get("/api/search")
def search(q: str = Query(min_length=2, max_length=500), k: int = Query(5, ge=1, le=20), u=Depends(current_user)):
    t = time.perf_counter()
    hits = rag.store.search(q, k)
    ms = round((time.perf_counter() - t) * 1000, 1)
    log_query(u["id"], "search", q, latency_ms=ms, n_sources=len(hits))
    return {"results": hits, "latency_ms": ms, "embedder": rag.store.embedder.info()}


# ======================================================================= disease detection
@app.post("/api/disease/predict")
async def disease_predict(file: UploadFile = File(...), u=Depends(current_user)):
    if not disease_model.available():
        raise HTTPException(503, "Disease model not found. Run training/train_disease.py first.")
    raw = await read_upload(file)
    t = time.perf_counter()
    try:
        res = disease_model.predict(raw)
    except ValueError as e:
        raise HTTPException(400, str(e))
    res["latency_ms"] = round((time.perf_counter() - t) * 1000, 1)
    log_query(u["id"], "disease", f"{file.filename} → {res['top']['class']} ({res['top']['confidence']:.2f})",
              latency_ms=res["latency_ms"])
    return res


@app.get("/api/disease/info")
def disease_info(u=Depends(current_user)):
    return {"metrics": disease_model.metrics,
            "samples": sorted(p.name for p in (DATA / "sample_leaves").glob("*.jpg"))}


@app.get("/api/disease/samples/{name}")
def disease_sample(name: str):
    p = (DATA / "sample_leaves" / Path(name).name)
    if not p.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(p)


# ======================================================================= soil & smart farming
class SoilIn(BaseModel):
    N: float = Field(ge=0, le=2000)
    P: float = Field(ge=0, le=500)
    K: float = Field(ge=0, le=2000)
    ph: float = Field(ge=3, le=11)
    oc: float | None = Field(None, ge=0, le=10)
    ec: float | None = Field(None, ge=0, le=20)
    rainfall: float | None = Field(None, ge=0, le=6000)
    irrigated: bool = False
    language: str = "en"
    ai_summary: bool = True


@app.post("/api/soil/analyse")
def soil(body: SoilIn, u=Depends(current_user)):
    a = agro.soil_analysis(body.N, body.P, body.K, body.ph, body.oc, body.ec, body.rainfall, body.irrigated)
    a["summary"], a["summary_source"] = agro.soil_summary_template(a), "rule-based"
    if body.ai_summary:
        try:
            facts = json.dumps({k: a[k] for k in ("ratings", "ph", "ec", "tips")} | {"top_crops": a["suitability"][:5]},
                               ensure_ascii=False)
            r = llm.generate(rag.EXPERT_SYSTEM + rag.lang_instruction(body.language),
                             [{"role": "user", "content": "Explain this soil test result to a farmer in under 150 words, "
                               "with 3 concrete action points. Use only these facts:\n" + facts}])
            a["summary"], a["summary_source"] = r["text"], f"{r['provider']}:{r['model']}"
        except llm.LLMUnavailable as e:
            a["summary_note"] = str(e)
    log_query(u["id"], "soil", f"N{body.N} P{body.P} K{body.K} pH{body.ph}")
    return a


class CropIn(BaseModel):
    N: float = Field(ge=0, le=300)
    P: float = Field(ge=0, le=300)
    K: float = Field(ge=0, le=300)
    temperature: float = Field(ge=-5, le=55)
    humidity: float = Field(ge=0, le=100)
    ph: float = Field(ge=3, le=11)
    rainfall: float = Field(ge=0, le=4000)


@app.post("/api/farming/recommend-crop")
def recommend(body: CropIn, u=Depends(current_user)):
    r = agro.recommend_crops(body.model_dump())
    log_query(u["id"], "crop-recommendation", json.dumps(body.model_dump()))
    return r


class FertIn(BaseModel):
    N: float = Field(ge=0, le=600)
    P2O5: float = Field(ge=0, le=400)
    K2O: float = Field(ge=0, le=400)
    area_ha: float = Field(1.0, gt=0, le=1000)
    adjust: dict[str, str] | None = None


@app.post("/api/farming/fertiliser")
def fertiliser(body: FertIn, u=Depends(current_user)):
    return agro.fertiliser_plan(body.N, body.P2O5, body.K2O, body.area_ha, body.adjust)


class IrrIn(BaseModel):
    crop: str
    stage: str = "mid"
    method: str = "drip"
    area_ha: float = Field(1.0, gt=0, le=1000)
    lat: float | None = None
    lon: float | None = None
    et0: list[float] | None = None
    rain: list[float] | None = None

    @field_validator("stage")
    @classmethod
    def _st(cls, v):
        if v not in ("initial", "development", "mid", "late"):
            raise ValueError("stage must be initial, development, mid or late")
        return v


@app.get("/api/farming/meta")
def farming_meta(u=Depends(current_user)):
    return {"irrigation_crops": list(agro.KC), "methods": list(agro.EFF), "season": agro.current_season(),
            "crop_stats": agro.crop_stats_options()}


@app.post("/api/farming/irrigation")
def irrigation(body: IrrIn, u=Depends(current_user)):
    if body.crop not in agro.KC or body.method not in agro.EFF:
        raise HTTPException(400, "Unknown crop or method")
    dates, source = None, "manual"
    if body.lat is not None and body.lon is not None:
        try:
            w = agro.weather(body.lat, body.lon)
            fc = w["forecast"]
            et0, rain, dates, source = [d["et0"] or 0 for d in fc], [d["rain"] or 0 for d in fc], [d["date"] for d in fc], w["source"]
        except Exception as e:  # noqa: BLE001
            if not body.et0:
                raise HTTPException(502, f"Weather service unavailable ({e}); enter ET0 manually.")
            et0, rain = body.et0, body.rain or [0] * len(body.et0)
    elif body.et0:
        et0, rain = body.et0, body.rain or [0] * len(body.et0)
    else:
        raise HTTPException(400, "Provide a location or ET0 values")
    r = agro.irrigation_plan(body.crop, body.stage, et0, rain, body.method, body.area_ha, dates)
    r["weather_source"] = source
    log_query(u["id"], "irrigation", f"{body.crop} {body.stage} {body.method}")
    return r


@app.get("/api/farming/districts")
def get_districts(state: str, u=Depends(current_user)):
    return agro.districts(state)


@app.get("/api/farming/crop-stats")
def get_crop_stats(state: str, district: str | None = None, season: str | None = None, u=Depends(current_user)):
    return agro.crop_stats(state, district, season)


class AdvisorIn(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    context: dict = {}
    language: str = "en"


@app.post("/api/farming/advisor")
def advisor(body: AdvisorIn, u=Depends(current_user)):
    ctx = json.dumps(body.context, ensure_ascii=False)[:4000]
    q = f"{body.question}\n\nFarm context (from AgriMind tools): {ctx}\nCurrent season: {agro.current_season()}."
    try:
        res = rag.answer(q, body.language, mode="rag")
    except llm.LLMUnavailable as e:
        raise HTTPException(503, str(e))
    log_query(u["id"], "advisor", body.question, language=body.language, provider=res["provider"], latency_ms=res["latency_ms"],
              groundedness=res["grounding"].get("groundedness"), ok=not res.get("fallback"))
    return {"answer": res["text"], "citations": res["citations"], "grounding": {k: v for k, v in res["grounding"].items() if k != "claims"},
            "provider": res["provider"], "model": res["model"], "latency_ms": res["latency_ms"], "usage": res.get("usage")}


# ======================================================================= schemes
@app.get("/api/schemes")
def schemes(u=Depends(current_user)):
    return json.loads((DATA / "schemes.json").read_text(encoding="utf-8"))


# ======================================================================= weather & market
@app.get("/api/weather/geocode")
def wx_geo(q: str = Query(min_length=2), u=Depends(current_user)):
    try:
        return agro.geocode(q)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Geocoding service unavailable: {e}")


@app.get("/api/weather")
def wx(lat: float, lon: float, u=Depends(current_user)):
    try:
        return agro.weather(lat, lon)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Weather service unavailable: {e}")


@app.get("/api/market/overview")
def mk_overview(u=Depends(current_user)):
    return agro.price_overview()


@app.get("/api/market/trend")
def mk_trend(commodity: str, market: str | None = None, state: str | None = None, u=Depends(current_user)):
    return agro.price_trend(commodity, market, state)


class FetchIn(BaseModel):
    state: str | None = None
    commodity: str | None = None


@app.post("/api/market/fetch")
def mk_fetch(body: FetchIn, u=Depends(current_user)):
    try:
        return agro.fetch_live_prices(body.state, body.commodity)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"data.gov.in request failed: {e}")


@app.post("/api/market/import")
async def mk_import(file: UploadFile = File(...), u=Depends(current_user)):
    raw = await read_upload(file)
    try:
        return agro.import_price_csv(raw)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ======================================================================= LLM lab & evaluation
class LabIn(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    language: str = "en"
    reference: str | None = None
    judge: bool = True


@app.post("/api/lab/compare")
def lab(body: LabIn, u=Depends(current_user)):
    r = evaluation.compare_modes(body.question, body.language, body.reference or None, judge=body.judge)
    for m, x in r["results"].items():
        log_query(u["id"], f"lab:{m}", body.question, language=body.language, provider=x.get("provider"), model=x.get("model"),
                  latency_ms=x.get("latency_ms"), groundedness=x.get("groundedness"), ok="error" not in x, error=x.get("error"))
    return r


@app.get("/api/lab/benchmark")
def lab_bench(u=Depends(current_user)):
    return evaluation.benchmark()


@app.get("/api/eval/classification")
def eval_cls(u=Depends(current_user)):
    return evaluation.classification_metrics()


class EvalIn(BaseModel):
    kind: str
    n: int = Field(8, ge=1, le=36)
    ks: list[int] = [1, 3, 5]
    language: str | None = None
    judge: bool = True


@app.post("/api/eval/run")
def eval_run(body: EvalIn, u=Depends(current_user)):
    if body.kind not in ("retrieval", "generation"):
        raise HTTPException(400, "kind must be retrieval or generation")
    return evaluation.start_job(body.kind, u["id"], body.model_dump())


@app.get("/api/eval/jobs/{jid}")
def eval_job(jid: str, u=Depends(current_user)):
    if jid not in evaluation.JOBS:
        raise HTTPException(404, "Unknown job")
    return evaluation.JOBS[jid]


@app.get("/api/eval/runs")
def eval_runs(u=Depends(current_user)):
    return evaluation.list_runs()


@app.get("/api/eval/runs/{rid}")
def eval_run_get(rid: int, u=Depends(current_user)):
    r = evaluation.get_run(rid)
    if not r:
        raise HTTPException(404, "Not found")
    return r


@app.get("/api/eval/runs/{rid}/download")
def eval_download(rid: int, fmt: str = "csv", u=Depends(current_user)):
    r = evaluation.get_run(rid)
    if not r:
        raise HTTPException(404, "Not found")
    if fmt == "json":
        return Response(json.dumps(r, indent=2, ensure_ascii=False), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="agrimind_eval_{rid}.json"'})
    flat = []
    for d in r["details"]:
        rec = {}
        for k, v in d.items():
            if isinstance(v, dict):
                rec.update({f"{k}.{kk}": vv for kk, vv in v.items()})
            else:
                rec[k] = "; ".join(map(str, v)) if isinstance(v, list) else v
        flat.append(rec)
    buf = io.StringIO()
    cols = list(dict.fromkeys(k for rec in flat for k in rec))
    w = csv.DictWriter(buf, fieldnames=cols)
    w.writeheader()
    w.writerows(flat)
    return Response("﻿" + buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="agrimind_eval_{rid}.csv"'})


# ======================================================================= admin
def _cuda_available():
    try:
        import torch
        return bool(torch.cuda.is_available())
    except ImportError:  # lite build without PyTorch
        return False


@app.get("/api/admin/stats")
def admin_stats(a=Depends(admin_user)):
    day = 86400
    since = time.time() - 30 * day
    per_day = rows("SELECT date(created_at,'unixepoch','localtime') d, COUNT(*) n, AVG(latency_ms) lat FROM query_logs "
                   "WHERE created_at>? GROUP BY d ORDER BY d", (since,))
    feats = rows("SELECT feature, COUNT(*) n, AVG(latency_ms) lat, AVG(groundedness) g, SUM(1-ok) errors FROM query_logs "
                 "GROUP BY feature ORDER BY n DESC")
    langs = rows("SELECT COALESCE(language,'en') language, COUNT(*) n FROM query_logs WHERE feature='chat' GROUP BY language")
    return {"users": row("SELECT COUNT(*) n FROM users")["n"], "active_users": row("SELECT COUNT(*) n FROM users WHERE active=1")["n"],
            "documents": row("SELECT COUNT(*) n FROM documents")["n"], "chunks": int(rag.store.index.ntotal),
            "conversations": row("SELECT COUNT(*) n FROM conversations")["n"], "queries": row("SELECT COUNT(*) n FROM query_logs")["n"],
            "eval_runs": row("SELECT COUNT(*) n FROM eval_runs")["n"], "per_day": per_day, "features": feats, "languages": langs,
            "llm": llm.provider_info(), "embedder": rag.store.embedder.info(),
            "cuda": _cuda_available(), "price_rows": row("SELECT COUNT(*) n FROM market_prices")["n"]}


@app.get("/api/admin/users")
def admin_users(a=Depends(admin_user)):
    return rows("SELECT u.id,u.email,u.name,u.role,u.active,u.language,u.created_at,u.last_login,"
                "(SELECT COUNT(*) FROM query_logs q WHERE q.user_id=u.id) queries FROM users u ORDER BY u.id")


class UserPatch(BaseModel):
    role: str | None = None
    active: bool | None = None


@app.patch("/api/admin/users/{uid}")
def admin_user_patch(uid: int, body: UserPatch, a=Depends(admin_user)):
    if uid == a["id"]:
        raise HTTPException(400, "You cannot change your own role or status")
    if body.role is not None:
        if body.role not in ("admin", "farmer", "expert"):
            raise HTTPException(400, "Invalid role")
        execute("UPDATE users SET role=? WHERE id=?", (body.role, uid))
    if body.active is not None:
        execute("UPDATE users SET active=? WHERE id=?", (int(body.active), uid))
    return row("SELECT id,email,name,role,active FROM users WHERE id=?", (uid,))


@app.delete("/api/admin/users/{uid}")
def admin_user_delete(uid: int, a=Depends(admin_user)):
    if uid == a["id"]:
        raise HTTPException(400, "You cannot delete yourself")
    for c in rows("SELECT id FROM conversations WHERE user_id=?", (uid,)):
        execute("DELETE FROM messages WHERE conversation_id=?", (c["id"],))
    execute("DELETE FROM conversations WHERE user_id=?", (uid,))
    execute("DELETE FROM users WHERE id=?", (uid,))
    return {"ok": True}


@app.get("/api/admin/queries")
def admin_queries(limit: int = Query(100, le=1000), feature: str | None = None, a=Depends(admin_user)):
    q = "SELECT q.*, u.email FROM query_logs q LEFT JOIN users u ON u.id=q.user_id"
    p = []
    if feature:
        q += " WHERE q.feature=?"; p.append(feature)
    return rows(q + " ORDER BY q.id DESC LIMIT ?", (*p, limit))


@app.get("/api/admin/settings")
def admin_settings(a=Depends(admin_user)):
    return {"settings": all_settings(), "provider": llm.provider_info()}


@app.put("/api/admin/settings")
def admin_settings_put(body: dict, a=Depends(admin_user)):
    """Secrets: an empty string keeps the stored key, null removes it, any other value replaces it.
    Secrets are never echoed back."""
    reindex = False
    for k, v in body.items():
        if k.endswith(("_set", "_source")):
            continue
        if k not in SECRET_KEYS and v is not None and str(v) == str(rag.get_setting(k)):
            continue  # unchanged: keep following the environment default
        if k in SECRET_KEYS:
            if v == "":
                continue
            if v is not None:
                v = str(v).strip()
        if k == "llm_provider" and v not in ("xai", "ollama"):
            raise HTTPException(400, "Provider must be xai or ollama")
        if k == "xai_base_url" and v and not str(v).startswith("https://"):
            raise HTTPException(400, "The xAI base URL must use https://")
        try:
            if k in ("top_k", "chunk_size", "chunk_overlap"):
                v = int(v)
            if k in ("temperature", "grounding_threshold", "llm_timeout"):
                v = float(v)
        except (TypeError, ValueError):
            raise HTTPException(400, f"Invalid value for {k}")
        if k == "embedding_model" and v != rag.get_setting("embedding_model"):
            reindex = True
        set_setting(k, v)
    if reindex:
        rag.store.load()
    return {"settings": all_settings(), "provider": llm.provider_info()}


@app.post("/api/admin/settings/test")
def admin_test_llm(a=Depends(admin_user)):
    """Makes one real request to the configured provider and reports status, model, latency and token usage."""
    info = llm.provider_info()
    try:
        r = llm.generate("You are a concise assistant.", [{"role": "user", "content": "Reply with one short sentence about soil health."}],
                         temperature=0, max_tokens=400)
        log_query(a["id"], "llm-test", "connectivity test", provider=r["provider"], model=r["model"], latency_ms=r["latency_ms"])
        return {"ok": True, **info, **r}
    except llm.LLMUnavailable as e:
        log_query(a["id"], "llm-test", "connectivity test", provider=info["provider"], model=info["model"], ok=False, error=str(e))
        return {"ok": False, "kind": e.kind, "error": str(e), **info}


@app.get("/api/admin/models")
def admin_models(a=Depends(admin_user)):
    return llm.list_models()


@app.post("/api/admin/reindex")
def admin_reindex(a=Depends(admin_user)):
    t = time.time()
    rag.store.rebuild()
    return {"chunks": int(rag.store.index.ntotal), "seconds": round(time.time() - t, 2), "embedder": rag.store.embedder.info()}


# ======================================================================= frontend (built SPA)
DIST = ROOT.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, 404)
        f = DIST / path
        if path and f.is_file() and DIST in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
