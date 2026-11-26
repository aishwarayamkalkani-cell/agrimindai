"""End-to-end API tests. Run from backend/:  python -m pytest -q

The LLM is replaced by a deterministic test double (monkeypatched) because tests must not call paid APIs;
everything else - auth, ingestion, FAISS retrieval, groundedness scoring, models - runs for real.
"""
import io
import re
from pathlib import Path

import pytest

from fastapi.testclient import TestClient  # noqa: E402

from app import llm, main, rag  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"


def fake_generate(system, messages, temperature=None, timeout=120):
    """Test double: in RAG mode copy the first sentence of each source with its citation; otherwise a generic answer."""
    user = messages[-1]["content"]
    if "SOURCES:" in user:
        parts = re.findall(r"\[(\d+)\] \(from: [^\n]*\)\n(?:\[[^\]]*\]\n)?([^\n]+)", user)
        text = " ".join(f"{s.strip()} [{n}]" for n, s in parts[:2])
    else:
        text = "Farmers should consult the local agriculture office for advice on this topic and follow good practices."
    return {"text": text, "latency_ms": 1.0, "provider": "test-double", "model": "fake"}


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(scope="module")
def admin(client):
    r = client.post("/api/auth/register", json={"name": "Admin", "email": "admin@test.in", "password": "Secret123!"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin"  # first user becomes admin
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def farmer(client, admin):
    r = client.post("/api/auth/register", json={"name": "Ravi", "email": "ravi@test.in", "password": "Secret123!"})
    assert r.json()["user"]["role"] == "farmer"
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_health_and_seed(client):
    h = client.get("/api/health").json()
    assert h["documents"] >= 8 and h["chunks"] > 50 and h["disease_model"]


def test_auth_rules(client, admin, farmer):
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/admin/users", headers=farmer).status_code == 403
    assert client.post("/api/auth/login", json={"email": "ravi@test.in", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "ravi@test.in", "password": "Secret123!"}).status_code == 200
    assert client.post("/api/auth/register", json={"name": "X", "email": "bad", "password": "short"}).status_code == 422
    assert client.get("/api/dashboard", headers={"Authorization": "Bearer forged.token.value"}).status_code == 401


def test_upload_search_delete(client, farmer):
    txt = b"# Coconut notes\n\nCoconut root wilt disease causes flaccidity of leaflets and yellowing. Remove badly affected palms."
    r = client.post("/api/documents", headers=farmer, files={"file": ("coconut.md", txt, "text/markdown")})
    assert r.status_code == 200, r.text
    doc = r.json()
    assert client.post("/api/documents", headers=farmer, files={"file": ("dup.md", txt, "text/markdown")}).status_code == 400
    hits = client.get("/api/search", params={"q": "coconut root wilt", "k": 3}, headers=farmer).json()["results"]
    assert hits[0]["document_id"] == doc["id"]
    # docx and csv extraction
    import docx
    d = docx.Document(); d.add_paragraph("Arecanut yellow leaf disease is a phytoplasma disease affecting arecanut palms in Karnataka.")
    buf = io.BytesIO(); d.save(buf)
    assert client.post("/api/documents", headers=farmer, files={"file": ("areca.docx", buf.getvalue(), "application/octet-stream")}).status_code == 200
    csv = b"crop,season,note\nragi,kharif,sow in July with 30 cm row spacing in southern Karnataka dry zone\n"
    assert client.post("/api/documents", headers=farmer, files={"file": ("ragi.csv", csv, "text/csv")}).status_code == 200
    assert client.post("/api/documents", headers=farmer, files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 400
    assert client.delete(f"/api/documents/{doc['id']}", headers=farmer).status_code == 200
    hits = client.get("/api/search", params={"q": "coconut root wilt", "k": 3}, headers=farmer).json()["results"]
    assert all(h["document_id"] != doc["id"] for h in hits)


def test_pdf_ingestion(client, admin):
    from reportlab.pdfgen import canvas
    buf = io.BytesIO(); c = canvas.Canvas(buf)
    c.drawString(72, 720, "Mango hoppers are controlled by pruning dense canopy and spraying neem oil."); c.showPage(); c.save()
    pdf = buf.getvalue()
    r = client.post("/api/documents", headers=admin, files={"file": ("mango.pdf", pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/documents/{r.json()['id']}/chunks", headers=admin).json()[0]["page"] == 1


def test_chat_without_llm_falls_back(client, farmer):
    r = client.post("/api/chat", headers=farmer, json={"message": "What is the premium for PMFBY kharif crops?"})
    assert r.status_code == 200
    m = r.json()["message"]
    assert m["meta"]["fallback"] and m["citations"]


def test_chat_rag_with_llm(client, farmer, monkeypatch):
    monkeypatch.setattr(llm, "generate", fake_generate)
    r = client.post("/api/chat", headers=farmer, json={"message": "How do I control fall armyworm in maize?"}).json()
    assert "[1]" in r["message"]["content"]
    assert r["message"]["meta"]["grounding"]["groundedness"] == 1.0  # copied source sentences are fully supported
    cid = r["conversation_id"]
    r2 = client.post("/api/chat", headers=farmer, json={"message": "and in which crop stage?", "conversation_id": cid})
    assert r2.status_code == 200
    conv = client.get(f"/api/conversations/{cid}", headers=farmer).json()
    assert len(conv["messages"]) == 4


def test_conversation_isolation(client, admin, farmer):
    convs = client.get("/api/conversations", headers=farmer).json()
    assert client.get(f"/api/conversations/{convs[0]['id']}", headers=admin).status_code == 404


def test_lab_compare_and_generation_eval(client, admin, monkeypatch):
    monkeypatch.setattr(llm, "generate", fake_generate)
    r = client.post("/api/lab/compare", headers=admin, json={"question": "What subsidy is available for drip irrigation?",
                                                              "reference": "55% for small and marginal farmers"}).json()
    res = r["results"]
    assert set(res) == {"baseline", "engineered", "rag"}
    assert res["rag"]["groundedness"] > res["baseline"]["groundedness"]
    from app import evaluation
    summary, details = evaluation.generation_eval(n=3)
    assert summary["rag"]["groundedness"] >= summary["baseline"]["groundedness"] and len(details) == 3


def test_retrieval_eval(client, admin):
    from app import evaluation
    s, per = evaluation.retrieval_eval()
    assert s["n_questions"] == 36 and 0 <= s["mrr"] <= 1 and s["recall@5"] >= s["recall@1"]
    assert all(0 <= p["precision@3"] <= 1 for p in per)


def test_disease_prediction(client, farmer):
    samples = sorted((DATA / "sample_leaves").glob("*.jpg"))
    correct = 0
    for f in samples:
        r = client.post("/api/disease/predict", headers=farmer, files={"file": (f.name, f.read_bytes(), "image/jpeg")}).json()
        assert abs(sum(p["confidence"] for p in r["predictions"]) - 1) < 0.5
        correct += r["top"]["class"].replace(",", "").replace(" ", "_") == f.stem
    assert correct >= len(samples) * 0.7  # held-out images
    assert client.post("/api/disease/predict", headers=farmer, files={"file": ("x.jpg", b"not an image", "image/jpeg")}).status_code == 400


def test_soil_crop_fertiliser_irrigation(client, farmer):
    s = client.post("/api/soil/analyse", headers=farmer, json={"N": 200, "P": 30, "K": 300, "ph": 8.9, "oc": 0.3, "ec": 0.5, "ai_summary": False}).json()
    assert s["ratings"]["N"]["rating"] == "Low" and s["ratings"]["P"]["rating"] == "High" and s["ratings"]["K"]["rating"] == "High"
    assert s["ph"]["class"].startswith("Strongly alkaline")
    c = client.post("/api/farming/recommend-crop", headers=farmer, json={"N": 90, "P": 42, "K": 43, "temperature": 21, "humidity": 82, "ph": 6.5, "rainfall": 203}).json()
    assert c["recommendations"][0]["crop"] == "rice"
    f = client.post("/api/farming/fertiliser", headers=farmer, json={"N": 100, "P2O5": 46, "K2O": 60, "area_ha": 1}).json()
    assert f["products_per_ha_kg"] == {"DAP": 100.0, "Urea": round((100 - 18) / 0.46, 1), "MOP": 100.0}
    i = client.post("/api/farming/irrigation", headers=farmer, json={"crop": "Maize", "stage": "mid", "method": "drip", "et0": [5, 5], "rain": [0, 10]}).json()
    assert i["kc"] == 1.2 and i["days"][0]["net_mm"] == 6.0 and i["days"][1]["net_mm"] == 0.0
    st = client.get("/api/farming/crop-stats", headers=farmer, params={"state": "Karnataka", "season": "Kharif"}).json()
    assert st["top_crops"]


def test_market_csv_import(client, farmer):
    csv = ("State,District,Market,Commodity,Variety,Grade,Arrival_Date,Min_x0020_Price,Max_x0020_Price,Modal_x0020_Price\n"
           "Karnataka,Kolar,Kolar,Tomato,Local,FAQ,01/03/2025,800,1600,1200\n"
           "Karnataka,Kolar,Kolar,Tomato,Local,FAQ,02/03/2025,900,1700,1300\n").encode()
    r = client.post("/api/market/import", headers=farmer, files={"file": ("prices.csv", csv, "text/csv")}).json()
    assert r["stored"] == 2
    t = client.get("/api/market/trend", headers=farmer, params={"commodity": "Tomato"}).json()
    assert t["stats"]["latest"] == 1300 and len(t["series"]) == 2


def test_admin(client, admin, farmer):
    s = client.put("/api/admin/settings", headers=admin, json={"top_k": 5}).json()["settings"]
    assert s["top_k"] == "5"
    users = client.get("/api/admin/users", headers=admin).json()
    rid = next(u["id"] for u in users if u["email"] == "ravi@test.in")
    assert client.patch(f"/api/admin/users/{rid}", headers=admin, json={"active": False}).status_code == 200
    assert client.get("/api/dashboard", headers=farmer).status_code == 401  # disabled account
    client.patch(f"/api/admin/users/{rid}", headers=admin, json={"active": True})
    assert client.get("/api/admin/stats", headers=admin).json()["queries"] > 0
    assert client.get("/api/admin/queries", headers=admin).json()


def test_sentence_transformer_path(tmp_path, monkeypatch):
    """Exercise the Sentence-Transformers branch with a tiny randomly initialised model built offline
    (checks the integration, not retrieval quality). Skipped in the lite build, which does not install it."""
    pytest.importorskip("sentence_transformers")
    monkeypatch.setenv("EMBEDDING_BACKEND", "sentence-transformers")
    from sentence_transformers import SentenceTransformer, models
    from transformers import BertConfig, BertModel, BertTokenizerFast
    words = sorted(set(re.findall(r"[a-z]+", " ".join(p.read_text().lower() for p in (DATA / "knowledge").glob("*.md")))))[:3000]
    (tmp_path / "vocab.txt").write_text("\n".join(["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]"] + words))
    tok = BertTokenizerFast(vocab_file=str(tmp_path / "vocab.txt"))
    BertModel(BertConfig(vocab_size=len(words) + 5, hidden_size=32, num_hidden_layers=1, num_attention_heads=2, intermediate_size=64)).save_pretrained(tmp_path / "m")
    tok.save_pretrained(tmp_path / "m")
    tr = models.Transformer(str(tmp_path / "m"))
    SentenceTransformer(modules=[tr, models.Pooling(tr.get_word_embedding_dimension())]).save(str(tmp_path / "st"))
    e = rag.Embedder(str(tmp_path / "st"))
    assert e.kind == "sentence-transformers" and e.dim == 32
    v = e.encode(["rice blast", "tomato late blight"])
    assert v.shape == (2, 32) and abs(float((v[0] ** 2).sum()) - 1) < 1e-4
