"""Lite (low-memory, Render free tier) mode: keyword search, ONNX disease model, nothing heavy loaded."""
import sys
from pathlib import Path

from app import agro, rag
from app.disease import DiseaseModel

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "sample_leaves"


def test_lite_mode_never_loads_sentence_transformer(monkeypatch):
    monkeypatch.setenv("AGRIMIND_LITE", "1")
    monkeypatch.delenv("EMBEDDING_BACKEND", raising=False)
    assert rag.embedding_backend() == "tfidf"
    e = rag.Embedder("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    assert e.kind == "tfidf-fallback" and e.model is None
    assert "Lite mode" in e.info()["note"]
    e.fit(["drip irrigation saves water", "late blight of tomato", "PM-KISAN income support"])
    v = e.encode(["tomato blight"])
    assert v.shape[0] == 1 and abs(float((v[0] ** 2).sum()) - 1) < 1e-4


def test_render_env_selects_keyword_search(monkeypatch):
    monkeypatch.delenv("AGRIMIND_LITE", raising=False)
    monkeypatch.delenv("EMBEDDING_BACKEND", raising=False)
    monkeypatch.setenv("RENDER", "true")
    assert rag.embedding_backend() == "tfidf"
    monkeypatch.setenv("EMBEDDING_BACKEND", "sentence-transformers")
    assert rag.embedding_backend() == "sentence-transformers"


def test_onnx_disease_model_predicts_samples():
    m = DiseaseModel()
    hits = 0
    for name in ["Tomato___Late_blight", "Potato___Early_blight", "Tomato___healthy", "Corn_(maize)___Common_rust_"]:
        out = m.predict((SAMPLES / f"{name}.jpg").read_bytes())
        assert m.backend == "onnx" and len(out["predictions"]) == 3
        hits += out["top"]["class"] == name
    assert hits >= 3


def test_district_stats_compact_and_correct():
    d = agro._production()
    assert str(d.Crop.dtype) == "category" and d.memory_usage(deep=True).sum() < 20 * 2**20
    s = agro.crop_stats("Karnataka", None, "Kharif")
    assert s["top_crops"] and all(c["avg_area_ha"] > 0 for c in s["top_crops"])
    assert "Kharif" in agro.crop_stats_options()["seasons"]
