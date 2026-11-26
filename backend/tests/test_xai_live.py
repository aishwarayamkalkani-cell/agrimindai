"""GENUINE xAI integration test - makes real, billed requests to https://api.x.ai/v1.

Skipped unless XAI_API_KEY is set (environment or backend/.env). Run:
    python -m pytest tests/test_xai_live.py -v -s
or the reporting script:  python scripts/grok_integration_check.py
"""
import re

import pytest

from app import core  # noqa: F401  (loads backend/.env)

KEY = core.DEFAULTS["xai_api_key"]  # from the environment or backend/.env, placeholder ignored
pytestmark = pytest.mark.skipif(not KEY, reason="XAI_API_KEY not set - live xAI test skipped")


@pytest.fixture(scope="module")
def ready():
    from app import rag
    core.init_db()
    for k in ("xai_base_url", "xai_model", "xai_api_key", "llm_timeout"):
        core.set_setting(k, None)  # use the real values from the environment / backend/.env
    core.set_setting("llm_provider", "xai")
    rag.store.load()
    rag.seed_demo_documents()
    return rag


def test_live_models_and_connectivity(ready):
    from app import llm
    models = llm.list_models()
    assert not models.get("error"), models.get("error")
    print("\nAvailable models:", models["models"])
    r = llm.generate("You are concise.", [{"role": "user", "content": "In one sentence: why test soil before fertilising?"}], temperature=0)
    print("Model:", r["model"], "| latency ms:", r["latency_ms"], "| usage:", r["usage"], "\nAnswer:", r["text"])
    assert r["text"] and r["usage"] and r["usage"]["total_tokens"] > 0


def test_live_rag_answer_with_citations(ready):
    r = ready.answer("What premium does a farmer pay under PMFBY for a kharif crop?", "en", mode="rag")
    print("\nRAG answer:", r["text"], "\nGrounding:", {k: v for k, v in r["grounding"].items() if k != "claims"})
    assert not r.get("fallback")
    assert re.search(r"\[\d+\]", r["text"]), "Grok did not cite sources"
    assert "2" in r["text"]  # the 2% kharif cap is in the retrieved scheme document
    assert r["grounding"]["groundedness"] is not None


def test_live_kannada_answer(ready):
    r = ready.answer("ಟೊಮೆಟೊದಲ್ಲಿ ಎಲೆ ಮುರುಟು ವೈರಸ್ ಹೇಗೆ ಹರಡುತ್ತದೆ?", "kn", mode="rag")
    print("\nKannada answer:", r["text"][:400])
    assert re.search(r"[ಀ-೿]", r["text"]), "answer is not in Kannada script"


def test_live_three_way_comparison(ready):
    from app import evaluation
    r = evaluation.compare_modes("How much water can drip irrigation save compared with flood irrigation?",
                                 reference="Drip saves 30-60% water compared with flood irrigation.", judge=True)
    for m, x in r["results"].items():
        assert "error" not in x, x.get("error")
        print(f"\n{m}: relevance={x['answer_relevance']} faithfulness={x.get('faithfulness')} groundedness={x['groundedness']} "
              f"citations={x['citation_correctness']} latency={x['latency_ms']}ms tokens={x['usage']}")


def test_live_bad_key_is_reported():
    from app import llm
    core.set_setting("xai_api_key", "xai-invalid-key-for-testing")
    try:
        with pytest.raises(llm.LLMUnavailable) as e:
            llm.generate("s", [{"role": "user", "content": "hi"}])
        assert e.value.kind == "auth"
    finally:
        core.set_setting("xai_api_key", None)
