"""End-to-end exercise of every AgriMind feature against a running server, with concurrent load.
Usage: python e2e_load.py BASE_URL BACKEND_DIR"""
import io
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

BASE, BACKEND = sys.argv[1], Path(sys.argv[2])
c = httpx.Client(base_url=BASE, timeout=120)
results = []


def check(label, r, ok=(200,)):
    good = r.status_code in ok
    results.append((label, r.status_code, good))
    return r


# --- startup / frontend
check("health", c.get("/api/health"))
check("frontend /", c.get("/"))
check("frontend deep link /disease", c.get("/disease"))

# --- auth
r = check("register admin", c.post("/api/auth/register", json={"name": "Admin User", "email": "admin@example.com", "password": "Testpass123!"}))
assert r.json()["user"]["role"] == "admin"
r = check("register farmer", c.post("/api/auth/register", json={"name": "Farmer Ravi", "email": "ravi@example.com", "password": "Farmpass123!"}))
assert r.json()["user"]["role"] == "farmer"
r = check("login", c.post("/api/auth/login", json={"email": "admin@example.com", "password": "Testpass123!"}))
H = {"Authorization": f"Bearer {r.json()['token']}"}
check("login wrong password -> 401", c.post("/api/auth/login", json={"email": "admin@example.com", "password": "nope12345"}), ok=(401,))
check("me", c.get("/api/auth/me", headers=H))
check("no token -> 401", c.get("/api/auth/me"), ok=(401,))

# --- disease
for leaf in ["Tomato___Late_blight", "Potato___Early_blight", "Corn_(maize)___Common_rust_"]:
    r = check(f"disease {leaf}", c.post("/api/disease/predict", headers=H,
              files={"file": (f"{leaf}.jpg", (BACKEND / "data/sample_leaves" / f"{leaf}.jpg").read_bytes(), "image/jpeg")}))
    print(f"  {leaf} -> {r.json()['top']['class']} ({r.json()['top']['confidence']})")
check("disease info", c.get("/api/disease/info", headers=H))

# --- crop recommendation, soil, fertiliser, irrigation (offline ET0), district stats
r = check("crop recommend", c.post("/api/farming/recommend-crop", headers=H, json={"N": 90, "P": 42, "K": 43, "temperature": 21, "humidity": 82, "ph": 6.5, "rainfall": 203}))
print("  crop ->", r.json()["recommendations"][0]["crop"])
check("soil analyse", c.post("/api/soil/analyse", headers=H, json={"N": 250, "P": 20, "K": 200, "ph": 6.5, "oc": 0.6, "ec": 0.5}))
check("fertiliser", c.post("/api/farming/fertiliser", headers=H, json={"N": 100, "P2O5": 50, "K2O": 50, "area_ha": 2}))
meta = check("farming meta", c.get("/api/farming/meta", headers=H)).json()
crop = meta["irrigation_crops"][0]
check("irrigation (manual ET0)", c.post("/api/farming/irrigation", headers=H, json={"crop": crop, "et0": [5, 5.2, 4.8, 5.1, 5, 4.9, 5.3], "rain": [0, 0, 3, 0, 0, 0, 0]}))
check("districts", c.get("/api/farming/districts", headers=H, params={"state": "Karnataka"}))
for st in ["Karnataka", "Maharashtra", "Uttar Pradesh", "Punjab"]:
    check(f"crop stats {st}", c.get("/api/farming/crop-stats", headers=H, params={"state": st}))
check("farm advisor (LLM fallback)", c.post("/api/farming/advisor", headers=H, json={"question": "When should I sow ragi?"}), ok=(200, 502, 503))

# --- knowledge / keyword search / chat
r = check("keyword search", c.get("/api/search", headers=H, params={"q": "drip irrigation water saving"}))
print("  search top ->", r.json()["results"][0]["text"][:70].replace("\n", " "))
check("chat (RAG, Grok fallback)", c.post("/api/chat", headers=H, json={"message": "How do I control tomato late blight?"}))
check("conversations", c.get("/api/conversations", headers=H))
check("schemes", c.get("/api/schemes", headers=H))
check("dashboard", c.get("/api/dashboard", headers=H))

# upload documents (txt, pdf, docx)
from docx import Document  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402
buf = io.BytesIO(); cv = canvas.Canvas(buf)
for i in range(40):
    cv.drawString(40, 800 - (i % 50) * 15, f"Arecanut yellow leaf disease note {i}: manage with balanced nutrition and drainage.")
    if i % 20 == 19:
        cv.showPage()
cv.save()
d = Document(); [d.add_paragraph(f"Coconut root wilt guidance paragraph {i}. Apply organic manure and irrigate in summer.") for i in range(60)]
dbuf = io.BytesIO(); d.save(dbuf)
for name, data, mime in [("notes.txt", ("Sugarcane ratoon management. " * 400).encode(), "text/plain"),
                         ("arecanut.pdf", buf.getvalue(), "application/pdf"),
                         ("coconut.docx", dbuf.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")]:
    check(f"upload {name}", c.post("/api/documents", headers=H, files={"file": (name, data, mime)}))
check("search uploaded doc", c.get("/api/search", headers=H, params={"q": "coconut root wilt"}))
check("documents list", c.get("/api/documents", headers=H))

# --- evaluation, lab, admin
check("eval classification", c.get("/api/eval/classification", headers=H))
job = check("eval run retrieval (36 q)", c.post("/api/eval/run", headers=H, json={"kind": "retrieval", "n": 36})).json()
jid = job.get("job_id") or job.get("id")
for _ in range(120):
    j = c.get(f"/api/eval/jobs/{jid}", headers=H).json()
    if j.get("status") in ("done", "error", "failed"):
        break
    time.sleep(0.5)
results.append(("eval job finished", j.get("status"), j.get("status") == "done"))
check("eval runs", c.get("/api/eval/runs", headers=H))
check("lab benchmark", c.get("/api/lab/benchmark", headers=H))
check("lab compare (no key)", c.post("/api/lab/compare", headers=H, json={"question": "How much water does rice need?", "judge": False}), ok=(200, 400, 502, 503))
for ep in ["stats", "users", "queries", "settings"]:
    check(f"admin {ep}", c.get(f"/api/admin/{ep}", headers=H))
check("admin reindex", c.post("/api/admin/reindex", headers=H))

# --- concurrent load: 8 workers x mixed heavy requests
leaves = sorted((BACKEND / "data/sample_leaves").glob("*.jpg"))


def hit(i):
    cl = httpx.Client(base_url=BASE, timeout=120)
    k = i % 4
    if k == 0:
        f = leaves[i % len(leaves)]
        return cl.post("/api/disease/predict", headers=H, files={"file": (f.name, f.read_bytes(), "image/jpeg")}).status_code
    if k == 1:
        return cl.get("/api/farming/crop-stats", headers=H, params={"state": ["Karnataka", "Bihar", "Odisha", "Assam"][i % 4]}).status_code
    if k == 2:
        return cl.post("/api/chat", headers=H, json={"message": f"Fertiliser dose for ragi question {i}"}).status_code
    return cl.post("/api/farming/recommend-crop", headers=H, json={"N": 20 + i, "P": 30, "K": 30, "temperature": 26, "humidity": 60, "ph": 6.8, "rainfall": 100}).status_code


t = time.time()
with ThreadPoolExecutor(8) as ex:
    codes = list(ex.map(hit, range(160)))
results.append((f"concurrent load: 160 mixed requests, 8 parallel ({time.time() - t:.0f}s)", sorted(set(codes)), set(codes) == {200}))

bad = [r for r in results if not r[2]]
for label, code, good in results:
    print(("PASS " if good else "FAIL ") + f"{label}: {code}")
print(f"\n{len(results) - len(bad)}/{len(results)} checks passed")
sys.exit(1 if bad else 0)
