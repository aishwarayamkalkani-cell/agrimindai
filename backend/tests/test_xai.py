"""Automated tests for the Grok / xAI integration (mocked).

A local HTTP server imitates the xAI Chat Completions API (same JSON shapes, status codes and headers),
and the app talks to it through the real `openai` client. No real xAI requests are made here; the genuine
integration test is tests/test_xai_live.py, which runs only when XAI_API_KEY is set.
"""
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from fastapi.testclient import TestClient  # noqa: E402

from app import core, evaluation, llm, main, rag  # noqa: E402

KEY = "xai-TESTKEY-0123456789abcdef"


class FakeXAI(BaseHTTPRequestHandler):
    script: list = []          # queued (status, body, headers, delay) overrides
    requests: list = []

    def log_message(self, *a):
        pass

    def _send(self, status, body, headers=None, delay=0):
        if delay:
            time.sleep(delay)
        data = json.dumps(body).encode()
        try:
            self.send_response(status)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if self.path.endswith("/models"):
            return self._send(200, {"object": "list", "data": [{"id": "grok-4-1-fast-reasoning", "object": "model"},
                                                                {"id": "grok-4-1-fast-non-reasoning", "object": "model"}]})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeXAI.requests.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        if FakeXAI.script:
            status, payload, headers, delay = FakeXAI.script.pop(0)
            return self._send(status, payload, headers, delay)
        if self.headers.get("Authorization") != f"Bearer {KEY}":
            return self._send(401, {"error": {"message": "Incorrect API key provided", "type": "invalid_request_error", "code": "invalid_api_key"}})
        if body["model"] not in ("grok-4-1-fast-reasoning", "grok-4-1-fast-non-reasoning"):
            return self._send(404, {"error": {"message": f"The model {body['model']} does not exist", "code": "model_not_found"}})
        system, user = body["messages"][0]["content"], body["messages"][-1]["content"]
        if "fact-checking judge" in system:
            n = len(re.findall(r"^\d+\. ", user, re.M))
            text = json.dumps({"verdicts": [{"claim": i + 1, "verdict": "supported" if i == 0 else "unsupported"} for i in range(n)]})
        elif "SOURCES:" in user:
            srcs = re.findall(r"\[(\d+)\] \(from: [^\n]*\)\n(?:\[[^\]]*\]\n)?([^\n]+)", user)
            text = " ".join(f"{s.strip()} [{n}]" for n, s in srcs[:2])
        else:
            text = "Grok says: consult the local agriculture office and follow good agronomic practice for best results."
        self._send(200, {"id": "chatcmpl-test", "object": "chat.completion", "created": 1, "model": body["model"],
                         "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                         "usage": {"prompt_tokens": 120, "completion_tokens": 40, "total_tokens": 260,
                                   "completion_tokens_details": {"reasoning_tokens": 100}}})


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeXAI)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1"
    srv.shutdown()


@pytest.fixture(scope="module")
def client(server):
    with TestClient(main.app) as c:
        core.set_setting("llm_provider", "xai")
        core.set_setting("xai_base_url", server)  # set directly: the admin API only accepts https URLs
        core.set_setting("xai_api_key", KEY)
        core.set_setting("xai_model", "grok-4-1-fast-reasoning")
        core.set_setting("llm_timeout", "5")
        yield c
        for k in ("llm_provider", "xai_base_url", "xai_api_key", "xai_model", "llm_timeout"):
            core.set_setting(k, None)


@pytest.fixture(scope="module")
def admin(client):
    r = client.post("/api/auth/register", json={"name": "Admin", "email": "a@x.in", "password": "Secret123!"})
    core.execute("UPDATE users SET role='admin' WHERE email='a@x.in'")
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    FakeXAI.script, FakeXAI.requests = [], []
    sleeps = []
    monkeypatch.setattr(llm, "_sleep", sleeps.append)
    yield sleeps


def test_success_request_shape_and_usage(client):
    r = llm.generate("SYS", [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"}, {"role": "user", "content": "q2"}])
    req = FakeXAI.requests[-1]
    assert req["path"] == "/v1/chat/completions" and req["auth"] == f"Bearer {KEY}"
    assert req["body"]["model"] == "grok-4-1-fast-reasoning"
    assert [m["role"] for m in req["body"]["messages"]] == ["system", "user", "assistant", "user"]
    assert r["provider"] == "xai" and r["text"].startswith("Grok says")
    assert r["usage"] == {"prompt_tokens": 120, "completion_tokens": 40, "total_tokens": 260, "reasoning_tokens": 100}
    assert r["retries"] == 0 and r["finish_reason"] == "stop"


def test_rate_limit_retry_honours_retry_after(client, reset):
    FakeXAI.script = [(429, {"error": {"message": "Rate limit exceeded"}}, {"retry-after": "2"}, 0)] * 2
    r = llm.generate("s", [{"role": "user", "content": "hello"}])
    assert r["retries"] == 2 and reset == [2.0, 2.0] and len(FakeXAI.requests) == 3


def test_rate_limit_exhausted(client, reset):
    FakeXAI.script = [(429, {"error": {"message": "Rate limit exceeded"}}, {}, 0)] * 4
    with pytest.raises(llm.LLMUnavailable) as e:
        llm.generate("s", [{"role": "user", "content": "x"}])
    assert e.value.kind == "rate_limit" and "429" in str(e.value) and len(reset) == llm.MAX_RETRIES


def test_server_error_then_success(client):
    FakeXAI.script = [(503, {"error": {"message": "overloaded"}}, {}, 0)]
    assert llm.generate("s", [{"role": "user", "content": "x"}])["retries"] == 1


def test_auth_error_no_retry_and_key_not_leaked(client):
    core.set_setting("xai_api_key", "xai-WRONG-secretvalue")
    try:
        with pytest.raises(llm.LLMUnavailable) as e:
            llm.generate("s", [{"role": "user", "content": "x"}])
        assert e.value.kind == "auth" and len(FakeXAI.requests) == 1
        assert "secretvalue" not in str(e.value)
    finally:
        core.set_setting("xai_api_key", KEY)


def test_unknown_model(client):
    core.set_setting("xai_model", "grok-does-not-exist")
    try:
        with pytest.raises(llm.LLMUnavailable) as e:
            llm.generate("s", [{"role": "user", "content": "x"}])
        assert e.value.kind == "model"
    finally:
        core.set_setting("xai_model", "grok-4-1-fast-reasoning")


def test_timeout(client):
    core.set_setting("llm_timeout", "0.4")
    FakeXAI.script = [(200, {}, {}, 1.0)] * 4
    try:
        with pytest.raises(llm.LLMUnavailable) as e:
            llm.generate("s", [{"role": "user", "content": "x"}])
        assert e.value.kind == "timeout"
    finally:
        core.set_setting("llm_timeout", "5")


def test_network_error_and_missing_key(client, server):
    core.set_setting("xai_base_url", "http://127.0.0.1:9/v1")
    try:
        with pytest.raises(llm.LLMUnavailable) as e:
            llm.generate("s", [{"role": "user", "content": "x"}])
        assert e.value.kind == "network"
    finally:
        core.set_setting("xai_base_url", server)
    core.set_setting("xai_api_key", None)
    old = core.DEFAULTS["xai_api_key"]; core.DEFAULTS["xai_api_key"] = ""
    try:
        with pytest.raises(llm.LLMUnavailable) as e:
            llm.generate("s", [{"role": "user", "content": "x"}])
        assert e.value.kind == "config"
    finally:
        core.DEFAULTS["xai_api_key"] = old
        core.set_setting("xai_api_key", KEY)


def test_list_models(client):
    assert "grok-4-1-fast-reasoning" in llm.list_models()["models"]


def test_settings_never_expose_key(client, admin):
    for path in ("/api/admin/settings", "/api/health", "/api/admin/stats", "/api/dashboard"):
        assert KEY not in client.get(path, headers=admin).text
    s = client.get("/api/admin/settings", headers=admin).json()
    assert s["settings"]["xai_api_key_set"] is True and "xai_api_key" not in s["settings"]
    assert s["provider"]["provider"] == "xai" and s["provider"]["model"] == "grok-4-1-fast-reasoning"
    # empty string keeps the key; the response never contains it
    r = client.put("/api/admin/settings", headers=admin, json={"xai_api_key": "", "xai_model": "grok-4-1-fast-reasoning"})
    assert r.json()["settings"]["xai_api_key_set"] and KEY not in r.text
    assert client.put("/api/admin/settings", headers=admin, json={"llm_provider": "gemini"}).status_code == 400
    assert client.put("/api/admin/settings", headers=admin, json={"xai_base_url": "http://evil.example/v1"}).status_code == 400
    t = client.post("/api/admin/settings/test", headers=admin).json()
    assert t["ok"] and t["usage"]["total_tokens"] == 260 and KEY not in json.dumps(t)
    assert KEY not in client.get("/api/admin/queries", headers=admin).text


def test_gemini_install_migrates(client):
    core.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('llm_provider','gemini')")
    core.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('gemini_api_key','old')")
    core.init_db()
    assert core.get_setting("llm_provider") == "xai"
    assert core.row("SELECT * FROM settings WHERE key='gemini_api_key'") is None


def test_chat_rag_with_grok(client, admin):
    r = client.post("/api/chat", headers=admin, json={"message": "How do I manage late blight in tomato?"}).json()["message"]
    assert r["meta"]["provider"] == "xai" and not r["meta"]["fallback"]
    assert re.search(r"\[\d\]", r["content"]) and r["citations"]
    assert r["meta"]["grounding"]["groundedness"] == 1.0
    assert r["meta"]["usage"]["reasoning_tokens"] == 100
    sent = FakeXAI.requests[-1]["body"]["messages"][-1]["content"]
    assert "SOURCES:" in sent and "[1] (from:" in sent  # Grok received the retrieved documents


def test_grok_failure_falls_back_to_retrieval(client, admin):
    FakeXAI.script = [(429, {"error": {"message": "Rate limit exceeded"}}, {}, 0)] * 4
    r = client.post("/api/chat", headers=admin, json={"message": "What is SRI in rice?"})
    m = r.json()["message"]
    assert r.status_code == 200 and m["meta"]["fallback"] and "429" in m["content"] and m["citations"]


def test_citation_metrics():
    hits = rag.store.search("PMFBY premium kharif", 3)
    sent = next(c for c in rag.split_claims(hits[0]["text"]) if not c.startswith("[") and c.endswith("."))
    good = f"{sent[:-1]} [1]."
    m = evaluation.citation_metrics(good + " Something unrelated about cricket scores in Mumbai today. [2] Also invented. [9]", hits)
    assert m["n_citations"] == 3 and m["citation_validity"] == round(2 / 3, 4)
    assert m["citation_correctness"] == round(1 / 3, 4)
    assert evaluation.citation_metrics("No citations at all here.", hits)["citation_validity"] is None
    # marker placed after the full stop belongs to the preceding sentence
    after = evaluation.citation_metrics(sent + " [1] Cricket scores in Mumbai were high today. [2]", hits)
    assert after["citation_correctness"] == 0.5


def test_lab_comparison_all_metrics(client, admin):
    r = client.post("/api/lab/compare", headers=admin, json={"question": "How much water can drip irrigation save?",
                                                             "reference": "Drip saves 30–60% water.", "judge": True}).json()
    res = r["results"]
    for m in ("baseline", "engineered", "rag"):
        x = res[m]
        for k in ("answer_relevance", "groundedness", "unsupported_rate", "latency_ms", "semantic_similarity", "faithfulness"):
            assert x[k] is not None, (m, k)
        assert x["usage"]["total_tokens"] == 260 and x["judge_usage"]["total_tokens"] == 260
    assert res["rag"]["citation_validity"] == 1.0 and res["baseline"]["citation_validity"] is None
    assert res["rag"]["groundedness"] > res["baseline"]["groundedness"]


def test_generation_eval_summary(client):
    s, per = evaluation.generation_eval(n=2, judge=False)
    assert s["llm"]["provider"] == "xai" and s["rag"]["total_tokens"] == 260 and s["rag"]["reasoning_tokens"] == 100
    assert s["rag"]["citation_rate"] == 1.0 and s["baseline"]["citation_rate"] == 0.0 and s["judge"] is False
    assert len(per) == 2 and per[0]["rag"]["total_tokens"] == 260
