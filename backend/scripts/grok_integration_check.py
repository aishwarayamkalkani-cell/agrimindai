"""Genuine Grok (xAI) integration check for AgriMind AI.

Makes REAL, billed requests (about 12 short calls) to the xAI API using XAI_API_KEY from the environment or
backend/.env, and writes a report to backend/grok_integration_report.md (+ .json).

    cd backend
    .venv\\Scripts\\activate          (Windows)
    python scripts/grok_integration_check.py
"""
import json
import os
import re
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("AGRIMIND_STORE", tempfile.mkdtemp(prefix="agrimind_grokcheck_"))  # keep your real DB untouched

from app import core, evaluation, llm, rag  # noqa: E402

results, t_start = [], time.time()


def step(name):
    def deco(fn):
        t0 = time.perf_counter()
        try:
            detail = fn()
            results.append({"step": name, "ok": True, "seconds": round(time.perf_counter() - t0, 2), "detail": detail})
            print(f"PASS  {name}")
        except Exception as e:  # noqa: BLE001
            results.append({"step": name, "ok": False, "seconds": round(time.perf_counter() - t0, 2),
                            "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(limit=3)})
            print(f"FAIL  {name}: {e}")
        return fn
    return deco


core.init_db()
for k in ("llm_provider", "xai_base_url", "xai_model", "xai_api_key", "llm_timeout"):
    core.set_setting(k, None)
key = core.get_setting("xai_api_key")
if not key:
    sys.exit("XAI_API_KEY is not set. Put it in backend/.env (XAI_API_KEY=...) or the environment and run again.")
print(f"Provider: {llm.provider_info()['label']}  base URL: {core.get_setting('xai_base_url')}  model: {core.get_setting('xai_model')}")
print("Loading knowledge base (first run downloads the embedding model)...")
rag.store.load()
rag.seed_demo_documents()


@step("1. List models available to this API key")
def _():
    m = llm.list_models()
    if m.get("error"):
        raise RuntimeError(m["error"])
    configured = core.get_setting("xai_model")
    if configured not in m["models"]:
        raise RuntimeError(f"Configured model '{configured}' is not in the list: {m['models']}")
    return {"models": m["models"], "configured_model_available": True}


@step("2. Plain Grok completion (connectivity, latency, token usage)")
def _():
    r = llm.generate("You are a concise agricultural assistant.",
                     [{"role": "user", "content": "In one sentence: why should farmers test soil before applying fertiliser?"}], temperature=0)
    if not r["usage"] or not r["usage"].get("total_tokens"):
        raise RuntimeError("No token usage returned")
    return {k: r[k] for k in ("model", "latency_ms", "usage", "retries", "finish_reason", "text")}


@step("3. RAG answer grounded in retrieved documents, with citations")
def _():
    r = rag.answer("What premium does a farmer pay under PMFBY for a kharif crop?", "en", mode="rag")
    if r.get("fallback"):
        raise RuntimeError(r.get("error"))
    cites = sorted(set(int(n) for n in re.findall(r"\[(\d+)\]", r["text"])))
    if not cites:
        raise RuntimeError("Answer contains no [n] citations")
    bad = [n for n in cites if n > len(r["citations"])]
    if bad:
        raise RuntimeError(f"Citations point to non-existent sources: {bad}")
    cm = evaluation.citation_metrics(r["text"], [{"text": c["snippet"]} for c in r["citations"]])
    return {"answer": r["text"], "cited_sources": [r["citations"][n - 1]["title"] for n in cites],
            "grounding": {k: v for k, v in r["grounding"].items() if k != "claims"}, "citation_metrics": cm,
            "usage": r.get("usage"), "latency_ms": r["latency_ms"]}


@step("4. Out-of-scope question is flagged instead of invented")
def _():
    r = rag.answer("What is the minimum support price for saffron in Kashmir in 2026?", "en", mode="rag")
    return {"answer": r["text"], "grounding": {k: v for k, v in r["grounding"].items() if k != "claims"}}


@step("5. Kannada answer (multilingual retrieval + generation)")
def _():
    r = rag.answer("ಟೊಮೆಟೊದಲ್ಲಿ ಎಲೆ ಮುರುಟು ವೈರಸ್ ಹೇಗೆ ಹರಡುತ್ತದೆ?", "kn", mode="rag")
    if not re.search(r"[ಀ-೿]", r["text"]):
        raise RuntimeError("Answer is not in Kannada script")
    return {"answer": r["text"], "top_source": r["citations"][0]["title"] if r["citations"] else None}


@step("6. Three-way comparison (baseline / prompt-engineered / RAG) with Grok-as-judge faithfulness")
def _():
    r = evaluation.compare_modes("How much water can drip irrigation save compared with flood irrigation?",
                                 reference="Drip saves 30-60% water compared with flood irrigation.", judge=True)
    out = {}
    for m, x in r["results"].items():
        if "error" in x:
            raise RuntimeError(f"{m}: {x['error']}")
        out[m] = {k: x.get(k) for k in ("answer_relevance", "faithfulness", "groundedness", "unsupported_rate",
                                        "citation_validity", "citation_correctness", "semantic_similarity", "latency_ms", "usage")}
    return out


@step("7. Invalid API key is reported as an authentication error (no retry, key not echoed)")
def _():
    core.set_setting("xai_api_key", "xai-deliberately-invalid-key")
    try:
        llm.generate("s", [{"role": "user", "content": "hi"}])
        raise RuntimeError("Request with an invalid key unexpectedly succeeded")
    except llm.LLMUnavailable as e:
        if e.kind != "auth" or "deliberately-invalid" in str(e):
            raise RuntimeError(f"Unexpected error handling: kind={e.kind} msg={e}")
        return {"kind": e.kind, "message": str(e)}
    finally:
        core.set_setting("xai_api_key", None)


@step("8. Unknown model is reported clearly")
def _():
    core.set_setting("xai_model", "grok-model-that-does-not-exist")
    try:
        llm.generate("s", [{"role": "user", "content": "hi"}])
        raise RuntimeError("Unknown model unexpectedly succeeded")
    except llm.LLMUnavailable as e:
        return {"kind": e.kind, "message": str(e)}
    finally:
        core.set_setting("xai_model", None)


report = {"run_at": time.strftime("%Y-%m-%d %H:%M:%S"), "provider": llm.provider_info(), "embedder": rag.store.embedder.info(),
          "passed": sum(r["ok"] for r in results), "total": len(results), "seconds": round(time.time() - t_start, 1),
          "results": results}
blob = json.dumps(report, indent=2, ensure_ascii=False)
assert key not in blob
(ROOT / "grok_integration_report.json").write_text(blob, encoding="utf-8")
md = ["# Grok integration report\n", f"Run: {report['run_at']} · model `{report['provider']['model']}` · "
      f"embeddings `{report['embedder']['kind']}` · **{report['passed']}/{report['total']} steps passed** in {report['seconds']} s\n"]
for r in results:
    md.append(f"## {'✅' if r['ok'] else '❌'} {r['step']}  ({r['seconds']} s)\n")
    md.append("```json\n" + json.dumps(r.get("detail") if r["ok"] else r["error"], indent=2, ensure_ascii=False)[:4000] + "\n```\n")
(ROOT / "grok_integration_report.md").write_text("\n".join(md), encoding="utf-8")
print(f"\n{report['passed']}/{report['total']} passed. Report: {ROOT / 'grok_integration_report.md'}")
sys.exit(0 if report["passed"] == report["total"] else 1)
