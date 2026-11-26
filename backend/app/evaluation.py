"""Evaluation: retrieval metrics (Recall@K, Precision@K, MRR), generation comparison (baseline vs prompt-engineered vs RAG)."""
import json
import re
import threading
import time
import traceback
import uuid

import numpy as np

from .core import DATA, MODELS, execute, jdump, row, rows
from . import llm, rag

JOBS: dict = {}
MODES = ("baseline", "engineered", "rag")


def benchmark():
    return json.loads((DATA / "eval" / "rag_benchmark.json").read_text(encoding="utf-8"))["items"]


def retrieval_eval(ks=(1, 3, 5), items=None):
    items = items or benchmark()
    kmax = max(ks)
    per, agg = [], {f"{m}@{k}": [] for k in ks for m in ("recall", "precision", "hit")}
    agg["mrr"] = []
    t0 = time.perf_counter()
    for it in items:
        hits = rag.store.search(it["question"], kmax)
        files = [h["filename"] for h in hits]
        rel = set(it["relevant"])
        first = next((i + 1 for i, f in enumerate(files) if f in rel), None)
        rec = {"id": it["id"], "question": it["question"], "relevant": it["relevant"], "retrieved": files,
               "scores": [h["score"] for h in hits], "rr": round(1 / first, 4) if first else 0.0}
        agg["mrr"].append(rec["rr"])
        for k in ks:
            topk = files[:k]
            found = rel & set(topk)
            rec[f"recall@{k}"] = round(len(found) / len(rel), 4)
            rec[f"precision@{k}"] = round(sum(f in rel for f in topk) / k, 4)
            rec[f"hit@{k}"] = 1.0 if found else 0.0
            for m in ("recall", "precision", "hit"):
                agg[f"{m}@{k}"].append(rec[f"{m}@{k}"])
        per.append(rec)
    summary = {k: round(float(np.mean(v)), 4) for k, v in agg.items()}
    summary.update({"n_questions": len(items), "seconds": round(time.perf_counter() - t0, 2),
                    "embedder": rag.store.embedder.info(), "n_chunks": int(rag.store.index.ntotal)})
    return summary, per


def semantic_similarity(a, b):
    v = rag.store.embedder.encode([a, b])
    return round(float(v[0] @ v[1]), 4)


# ---------------------------------------------------------------- answer-quality metrics
_CITE = re.compile(r"\[(\d+)\]")


def answer_relevance(question, answer):
    """Cosine similarity between question and answer embeddings (does the answer address the question?)."""
    return semantic_similarity(question, answer)


def citation_metrics(answer, hits, threshold=None):
    """Citation validity: share of [n] markers that point to a retrieved source (1..k).
    Citation correctness: share of [n] markers whose sentence is supported by *that* source
    (best cosine similarity with the cited passage's sentences >= grounding threshold)."""
    th = float(threshold if threshold is not None else rag.get_setting("grounding_threshold"))
    text = re.sub(r"([.!?।])\s*((?:\[\d+\]\s*)+)", lambda m: " " + m.group(2).strip() + m.group(1) + " ", answer or "")
    sents = [s.strip(" -*•#\t") for s in rag._SENT.split(text) if s and _CITE.search(s)]
    pairs = [(s, int(n)) for s in sents for n in dict.fromkeys(_CITE.findall(s))]
    if not pairs:
        return {"n_citations": 0, "citation_validity": None, "citation_correctness": None}
    valid = [(s, n) for s, n in pairs if 1 <= n <= len(hits)]
    correct = 0
    emb = rag.store.embedder
    for s, n in valid:
        src = rag.split_claims(hits[n - 1]["text"]) + [hits[n - 1]["text"]]
        sim = float((emb.encode([_CITE.sub("", s)]) @ emb.encode(src).T).max())
        correct += sim >= th
    return {"n_citations": len(pairs), "citation_validity": round(len(valid) / len(pairs), 4),
            "citation_correctness": round(correct / len(pairs), 4)}


JUDGE_SYSTEM = """You are a strict fact-checking judge for agricultural advice.
For each numbered CLAIM decide, using ONLY the SOURCES, whether it is:
- "supported": the sources state or directly imply it,
- "contradicted": the sources say something incompatible,
- "unsupported": the sources do not contain enough information.
General background knowledge does not count as support.
Reply with JSON only: {"verdicts": [{"claim": 1, "verdict": "supported"}, ...]}"""


def judge_faithfulness(claims, hits):
    """LLM-as-judge faithfulness (RAGAS-style): share of claims the judge model marks as supported by the
    retrieved sources. Uses the configured LLM at temperature 0."""
    if not claims or not hits:
        return {"faithfulness": None, "contradicted_rate": None, "judge_usage": None, "verdicts": []}
    user = f"SOURCES:\n{rag.format_sources(hits)}\n\nCLAIMS:\n" + "\n".join(f"{i + 1}. {c}" for i, c in enumerate(claims))
    r = llm.generate(JUDGE_SYSTEM, [{"role": "user", "content": user}], temperature=0)
    m = re.search(r"\{.*\}", r["text"], re.S)
    try:
        verdicts = json.loads(m.group(0))["verdicts"] if m else []
    except (ValueError, KeyError, TypeError):
        verdicts = []
    by = {int(v.get("claim", 0)): str(v.get("verdict", "")).lower() for v in verdicts if isinstance(v, dict)}
    if not by:
        return {"faithfulness": None, "contradicted_rate": None, "judge_usage": r.get("usage"), "verdicts": [],
                "judge_error": "Judge reply was not valid JSON"}
    labels = [by.get(i + 1, "unsupported") for i in range(len(claims))]
    return {"faithfulness": round(labels.count("supported") / len(claims), 4),
            "contradicted_rate": round(labels.count("contradicted") / len(claims), 4),
            "judge_usage": r.get("usage"), "verdicts": labels}


def compare_modes(question, lang="en", reference=None, k=None, judge=True):
    """Run the same LLM in the three configurations on one question and score each answer
    against the same retrieved evidence."""
    k = int(k or rag.get_setting("top_k"))
    hits = rag.store.search(question, k)
    out = {}
    for mode in MODES:
        system, user = rag.build_prompt(mode, question, lang, hits)
        try:
            res = llm.generate(system, [{"role": "user", "content": user}])
        except llm.LLMUnavailable as e:
            out[mode] = {"error": str(e), "error_kind": e.kind}
            continue
        g = rag.groundedness(res["text"], hits)
        claims = [c["text"] for c in g.get("claims", [])]
        x = {"answer": res["text"], "latency_ms": res["latency_ms"], "provider": res["provider"], "model": res["model"],
             "usage": res.get("usage"), "retries": res.get("retries", 0),
             "groundedness": g["groundedness"], "unsupported_rate": g["unsupported_rate"], "n_claims": g["n_claims"],
             "claims": g.get("claims", []), "words": len(res["text"].split()),
             "answer_relevance": answer_relevance(question, res["text"]),
             "semantic_similarity": semantic_similarity(res["text"], reference) if reference else None,
             **citation_metrics(res["text"], hits)}
        x["has_citations"] = x["n_citations"] > 0
        if judge:
            try:
                x.update(judge_faithfulness(claims, hits))
                for c, v in zip(x["claims"], x.get("verdicts", [])):
                    c["judge"] = v
            except llm.LLMUnavailable as e:
                x.update(faithfulness=None, judge_error=str(e))
        out[mode] = x
    return {"question": question, "language": lang, "citations": rag.citations_from(hits), "results": out, "judge": judge}


METRIC_KEYS = ("answer_relevance", "faithfulness", "contradicted_rate", "citation_validity", "citation_correctness",
               "groundedness", "unsupported_rate", "semantic_similarity", "latency_ms")
TOKEN_KEYS = ("prompt_tokens", "completion_tokens", "reasoning_tokens", "total_tokens")


def generation_eval(n=8, lang_filter=None, progress=None, judge=True):
    items = [i for i in benchmark() if (lang_filter is None or i.get("language", "en") == lang_filter)][:n]
    per = []
    agg = {m: {**{k: [] for k in METRIC_KEYS + TOKEN_KEYS}, "citation_rate": [], "judge_tokens": [], "errors": 0}
           for m in MODES}
    for idx, it in enumerate(items):
        r = compare_modes(it["question"], it.get("language", "en"), it["reference"], judge=judge)
        rec = {"id": it["id"], "question": it["question"], "reference": it["reference"]}
        for m in MODES:
            x = r["results"][m]
            if "error" in x:
                agg[m]["errors"] += 1
                rec[m] = {"error": x["error"]}
                continue
            for key in METRIC_KEYS:
                if x.get(key) is not None:
                    agg[m][key].append(x[key])
            for key in TOKEN_KEYS:
                if x.get("usage") and x["usage"].get(key) is not None:
                    agg[m][key].append(x["usage"][key])
            if x.get("judge_usage") and x["judge_usage"].get("total_tokens") is not None:
                agg[m]["judge_tokens"].append(x["judge_usage"]["total_tokens"])
            agg[m]["citation_rate"].append(1.0 if x["has_citations"] else 0.0)
            rec[m] = {k: x.get(k) for k in ("answer", "has_citations", "n_citations") + METRIC_KEYS}
            rec[m].update({f"{k}": (x.get("usage") or {}).get(k) for k in TOKEN_KEYS})
        per.append(rec)
        if progress:
            progress(idx + 1, len(items))
        if all(agg[m]["errors"] == idx + 1 for m in MODES):
            raise RuntimeError(r["results"]["rag"]["error"])
    summary = {m: {k: (round(float(np.mean(v)), 4) if isinstance(v, list) and v else (v if not isinstance(v, list) else None))
                   for k, v in d.items()} for m, d in agg.items()}
    summary.update(n_questions=len(items), llm=llm.provider_info(), judge=judge,
                   grounding_threshold=float(rag.get_setting("grounding_threshold")),
                   embedder=rag.store.embedder.info())
    return summary, per


def classification_metrics():
    out = {}
    for name in ("disease", "crop"):
        f = MODELS / f"{name}_metrics.json"
        out[name] = json.loads(f.read_text()) if f.exists() else None
    return out


def start_job(kind, user_id, params):
    jid = uuid.uuid4().hex[:12]
    JOBS[jid] = {"id": jid, "kind": kind, "status": "running", "progress": 0, "total": 0, "started": time.time()}

    def prog(i, n):
        JOBS[jid].update(progress=i, total=n)

    def run():
        try:
            if kind == "retrieval":
                summary, details = retrieval_eval(tuple(params.get("ks", (1, 3, 5))))
            else:
                summary, details = generation_eval(int(params.get("n", 8)), params.get("language"), prog, bool(params.get("judge", True)))
            rid = execute("INSERT INTO eval_runs(kind,config,summary,details,created_by,created_at) VALUES(?,?,?,?,?,?)",
                          (kind, jdump(params), jdump(summary), jdump(details), user_id, time.time()))
            JOBS[jid].update(status="done", run_id=rid)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            JOBS[jid].update(status="error", error=str(e)[:500])

    threading.Thread(target=run, daemon=True).start()
    return JOBS[jid]


def list_runs(limit=50):
    rs = rows("SELECT id, kind, config, summary, created_by, created_at FROM eval_runs ORDER BY id DESC LIMIT ?", (limit,))
    for r in rs:
        r["config"], r["summary"] = json.loads(r["config"] or "{}"), json.loads(r["summary"] or "{}")
    return rs


def get_run(rid):
    r = row("SELECT * FROM eval_runs WHERE id=?", (rid,))
    if r:
        for k in ("config", "summary", "details"):
            r[k] = json.loads(r[k] or "null")
    return r
