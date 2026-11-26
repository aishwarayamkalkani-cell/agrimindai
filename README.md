# AgriMind AI

**An Intelligent Agricultural Advisory and Knowledge Assistance System Using Generative AI, Large Language Models and Retrieval-Augmented Generation**

AgriMind AI is a full-stack web application for farmers and extension workers (focused on Karnataka/India). It combines a RAG-based conversational assistant, a trained leaf-disease classifier, soil-test interpretation, ML crop recommendation, FAO-56 irrigation planning, government-scheme guidance, weather and mandi-price intelligence, an LLM comparison laboratory and a full evaluation dashboard. The interface is available in English, ಕನ್ನಡ and हिन्दी.

---

## 1. Quick start (Windows laptop)

Requirements: **Python 3.10–3.13** (tick "Add Python to PATH" when installing). Node.js is *not* needed — the frontend is already built in `frontend/dist`.

1. Double-click **`setup-windows.bat`**. It creates `backend\.venv`, installs PyTorch (the CUDA build if `nvidia-smi` finds an NVIDIA GPU, otherwise CPU), installs the other packages and re-trains the small crop model so it matches your scikit-learn version. It also copies `backend\.env.example` to `backend\.env`.
2. Create an API key at <https://console.x.ai> (API Keys) and put it in `backend\.env` as `XAI_API_KEY=...`, or add it later in **Admin → Model configuration**. The key stays in the Python backend and is never sent to the browser.
3. Optional but recommended: double-click **`test-grok-windows.bat`**. It runs the automated tests and then a **genuine Grok integration check** (about 12 short, billed requests). The results go to `backend\grok_integration_report.md`.
4. Double-click **`start-windows.bat`**, then open <http://127.0.0.1:8000>.
5. **Create an account — the first account becomes the administrator.** Further accounts are farmers; the admin can promote them.

The first start downloads the multilingual Sentence-Transformer model (`paraphrase-multilingual-MiniLM-L12-v2`, about 470 MB) from Hugging Face and embeds the bundled knowledge base. Later starts are fast.

### Grok model configuration
| Setting (`backend/.env`) | Admin field | Default |
|---|---|---|
| `XAI_API_KEY` | xAI API key (write-only: shown as "saved", never displayed again) | — |
| `XAI_BASE_URL` | API base URL (must be https) | `https://api.x.ai/v1` |
| `XAI_MODEL` | Grok model | `grok-4-1-fast-reasoning` |
| `LLM_PROVIDER` | Provider | `xai` (or `ollama`) |
| `LLM_TIMEOUT` | Request timeout (s) | `90` |

A key or model saved in Admin overrides `.env`. **Save and test connection** makes one real request and shows the provider status, active model, latency and token usage. **List available models** asks xAI which models your key can use. `grok-4-1-fast-reasoning` is a reasoning model, so its answers use extra reasoning tokens. For faster, cheaper answers pick `grok-4-1-fast-non-reasoning`, or a newer Grok model your account lists.

Grok is called through xAI's OpenAI-compatible Chat Completions API with the official `openai` Python client. Rate-limit (429), server (5xx), timeout and connection errors are retried up to 3 times with exponential backoff, honouring `Retry-After`. Authentication, unknown-model and bad-request errors are reported immediately with a clear message. If Grok is unavailable, the assistant still shows the retrieved passages and says why.

### Optional: local LLM with Ollama
Install Ollama from <https://ollama.com>, run `ollama pull llama3.2:3b` (or any model), then choose **Ollama** in Admin → Model configuration and press *Save and test connection*. Ollama is called through the same OpenAI-compatible client (`http://localhost:11434/v1`).

### Optional: GPU
`setup-windows.bat` installs a CUDA build of PyTorch automatically when an NVIDIA driver is present. If you need a different CUDA version, pick the command at <https://pytorch.org/get-started/locally/> and run it inside `backend\.venv`. Admin → System statistics shows whether CUDA is in use. Everything also runs on CPU.

### Linux / macOS
```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-full.txt && python training/train_crop.py
cd .. && ./start-dev.sh
```
Frontend development with hot reload: `cd frontend && npm install && npm run dev` (proxies `/api` to port 8000).

---

## 1a. Deploy online (Render free tier, 512 MB RAM)

The repository is ready for Render: `render.yaml` deploys the **lite build** (`backend/requirements.txt`).

* No PyTorch or Sentence-Transformer: leaf-disease detection runs the same MobileNetV3 model exported to ONNX
  (`backend/models/disease_model.onnx`, identical predictions on all 19 sample leaves) and knowledge search uses
  keyword (TF-IDF) retrieval. Nothing is trained at build or startup; library versions are pinned so the bundled crop
  model loads directly.
* Measured memory: about 233 MB after startup and **364 MB peak** with 8–16 parallel requests over every feature.
* Steps: push to GitHub → Render → **New + → Blueprint** → pick the repo → paste `XAI_API_KEY` → **Apply**.
* Environment switches: `AGRIMIND_LITE=1` / `EMBEDDING_BACKEND=tfidf` force keyword search (automatic on Render);
  `EMBEDDING_BACKEND=sentence-transformers` with `requirements-full.txt` restores multilingual semantic search on a
  machine with 2 GB+ RAM. Render's free disk is temporary: accounts and chats reset when the service restarts.
* The `Dockerfile` builds the same lite image for any Docker host and listens on `$PORT`.
* `python backend/scripts/e2e_smoke.py http://127.0.0.1:8000 backend` exercises every feature against a fresh running server.

---

## 2. Features

| Module | What it does | How it works |
|---|---|---|
| **AI Assistant** | ChatGPT-style chat with saved conversation history, citations and a groundedness badge | RAG: query → multilingual embedding → FAISS top-K → prompt with numbered sources and citation rules → Grok (xAI) or Ollama → citation-aware answer → claim-level groundedness scoring |
| **Knowledge Base** | Upload PDF, DOCX, TXT, Markdown, CSV; semantic search; inspect passages; delete | pypdf / python-docx / CSV row extraction → section-aware chunking with sentence overlap → Sentence-Transformers → FAISS `IndexIDMap2(IndexFlatIP)` persisted to disk |
| **Crop Disease Detection** | Upload or photograph a leaf; top-3 diagnosis, advice, confidence warnings, model metrics | MobileNetV3-Large (ImageNet-pretrained) fine-tuned on 19 PlantVillage classes; flip test-time augmentation; entropy and leaf-pixel checks |
| **Soil Intelligence** | Soil Health Card ratings for N, P, K, OC, pH, EC; crop suitability; actions; plain-language summary | Standard Indian soil-test thresholds, FAO/Maas–Hoffman crop pH and salinity tolerance, LLM summary from the computed facts only |
| **Smart Farming** | Crop recommendation, fertiliser calculator, irrigation planner, district crop history, AI farm advisor | Gaussian NB selected by 5-fold CV over 4 models; DAP/urea/MOP arithmetic; FAO-56 ETc = Kc × ET₀ with live Open-Meteo ET₀; 242k rows of district-season production statistics |
| **Government Schemes** | PM-KISAN, PMFBY, KCC, PMKSY-PDMC, Soil Health Card, e-NAM, AIF, PM-KMY | Verified against official/PIB sources (24 Nov 2026), each with source links; also indexed for the assistant |
| **Weather & Markets** | 7-day forecast + past week, spray windows, disease-risk and heat alerts; mandi prices with trends | Open-Meteo (no key); Agmarknet daily prices via data.gov.in API (free key) and Agmarknet CSV import, stored in SQLite so history builds up |
| **LLM Lab** | Same question to **Baseline**, **Prompt-engineered** and **RAG-grounded** configurations of the *same* Grok model | Side-by-side answers with answer relevance, faithfulness (Grok-as-judge), citation validity and correctness, groundedness, unsupported-claim rate, similarity to a reference, latency, token usage (prompt / completion / reasoning) and claim-level verdicts |
| **Evaluation** | Retrieval benchmark, Grok comparison runs, classifier metrics, history, CSV/JSON download | Recall@K, Precision@K, Hit@K, MRR; answer relevance, faithfulness, citation correctness, groundedness, unsupported-claim rate, semantic similarity, latency, tokens; accuracy/F1/confusion matrices |
| **Admin** | Users (roles, disable, delete), query monitoring, Grok model configuration (write-only key, model, connectivity test, provider status), re-indexing, system statistics | JWT role checks on every admin route |

Security: bcrypt password hashing, signed JWT (24 h), per-user conversation isolation, admin-only routes, login throttling, upload type/size limits (20 MB), write-only API keys (never returned by any endpoint, removed from error messages, never sent to the frontend), https-only xAI base URL, security headers and parameterised SQL everywhere.

---

## 3. Architecture

```
React + TypeScript (Vite, Tailwind, Recharts)   — EN / ಕನ್ನಡ / हिन्दी, light & dark
        │  /api (JSON, JWT)
FastAPI ────────────────────────────────────────────────────────────────
  core.py        SQLite (users, conversations, messages, documents, chunks,
                 query_logs, eval_runs, settings, market_prices), auth, settings
  rag.py         extraction → chunking → Sentence-Transformers → FAISS → prompts
                 → generation → groundedness
  llm.py         Grok via xAI OpenAI-compatible API (primary) | Ollama (local)
                 retries/backoff, timeouts, error classification, token usage
  disease.py     PyTorch / timm MobileNetV3 inference (CUDA if available)
  agro.py        soil rules, crop model, fertiliser, FAO-56 irrigation, crop stats,
                 Open-Meteo weather, Agmarknet prices
  evaluation.py  retrieval + generation benchmarks, background jobs
```

## 4. Data and models (all real, nothing fabricated)

| Asset | Source |
|---|---|
| Leaf images | PlantVillage (Hughes & Salathé 2015, github.com/spMohanty/PlantVillage-Dataset) — 4,111 colour images, 19 classes (tomato 10, maize 4, potato 3, bell pepper 2) |
| Pretrained CNN | timm `mobilenetv3_large_100` ImageNet weights |
| Crop recommendation | Crop Recommendation Dataset (A. Ingle, Kaggle), 2,200 rows, 22 crops |
| District crop statistics | District-wise season-wise crop production (DES, Ministry of Agriculture; data.gov.in), 1997–2015 |
| Knowledge base | 8 demonstration documents written for this project from standard agronomy references (FAO-56, Soil Health Card ratings, ICAR/UAS package-of-practice guidance, official scheme pages) |
| RAG benchmark | 36 questions (34 English, 1 Kannada, 1 Hindi) with gold source documents and reference answers — `backend/data/eval/rag_benchmark.json` |

### Results measured while building (reproducible)

| Model | Test set | Result |
|---|---|---|
| Leaf disease classifier | 617 held-out images | **accuracy 93.8 %, macro-F1 93.9 %** (CPU, 7 epochs) |
| Crop recommender (Gaussian NB, chosen over RF / GB / LR by CV) | 440 held-out rows | accuracy 99.5 %, macro-F1 99.5 % — inflated by a very clean benchmark dataset; see limitations |
| Retrieval (TF-IDF fallback; the build machine could not download the Sentence-Transformer) | 36 questions | MRR 0.891, Recall@1 83.3 %, Recall@5 94.4 % |

Run **Evaluation → Retrieval** on your laptop to get the numbers for the real multilingual embedding model (expect the Kannada/Hindi questions to improve, because the fallback is lexical). **No Grok results are included here.** The Grok comparison needs your xAI key, so its numbers come only from your own runs; the app never shows invented scores.

### Metric definitions
Retrieval:
- **Recall@K**: share of a question's relevant documents that appear in the top-K passages. **Precision@K**: share of the top-K passages that come from a relevant document. **MRR**: mean of 1/rank of the first relevant passage.

Grok comparison (all three configurations use the same model, and every answer is scored against the same retrieved passages):
- **Answer relevance**: cosine similarity between the question and answer embeddings.
- **Faithfulness**: the answer is split into claims (sentences). Grok, acting as judge at temperature 0, labels each claim *supported*, *unsupported* or *contradicted* using only the retrieved passages. Faithfulness = supported ÷ claims, and the contradicted rate is reported too. This costs one extra request per answer and can be switched off.
- **Citation validity**: share of `[n]` markers that point to a retrieved source. **Citation correctness**: share of `[n]` markers whose sentence matches passage *n* (best cosine similarity ≥ the grounding threshold).
- **Groundedness**: share of claims whose best embedding similarity with any retrieved passage sentence ≥ the grounding threshold (default 0.55). **Unsupported-claim rate** = 1 − groundedness.
- **Semantic similarity**: cosine similarity between the answer and the benchmark reference answer.
- **Latency**: wall-clock time of the API call, including any retries. **Tokens**: `prompt_tokens`, `completion_tokens`, `reasoning_tokens` and `total_tokens` exactly as the API reports them. xAI counts reasoning tokens separately from completion tokens, but includes them in the total.

## 5. Retraining the models
```bash
cd backend
python training/train_crop.py                                   # seconds
python training/fetch_plantvillage.py --out ../datasets         # needs git, ~75 MB
python training/train_disease.py --data ../datasets/PlantVillage-Dataset/raw/color --weights ../datasets/mobilenetv3_large_100_ra-f55367f5.pth
```
Training uses CUDA automatically when available (about 7 minutes on a 2-core CPU, under a minute on a GPU). Metrics are written to `backend/models/*_metrics.json` and shown in the app.

## 6. Tests
```bash
cd backend && python -m pytest -q          # 30 automated tests (offline) + 5 live tests skipped without a key
python scripts/grok_integration_check.py   # genuine xAI check, writes grok_integration_report.md
```
- `tests/test_api.py` (14 tests) covers authentication and authorisation, ingestion of PDF/DOCX/TXT/MD/CSV, FAISS search and deletion, chat history and isolation, RAG answers with citations, groundedness, the three-way comparison, retrieval metrics, disease inference on held-out images, soil/crop/fertiliser/irrigation calculations, market CSV import, admin controls and the Sentence-Transformers code path.
- `tests/test_xai.py` (16 tests) runs the real `openai` client against a local server that returns xAI-format responses. It covers request format, token usage including reasoning tokens, 429 retry honouring `Retry-After`, exhausted rate limits, 5xx recovery, timeouts, connection failure, missing key, invalid key (no retry, key not echoed), unknown model, model listing, write-only key handling across every endpoint, migration of old Gemini settings, RAG chat through Grok, fallback when Grok fails, citation metrics and the full comparison and evaluation summaries.
- `tests/test_xai_live.py` (5 tests) makes **real** requests when `XAI_API_KEY` is set: model listing, a completion with token usage, a cited RAG answer, a Kannada answer, the three-way comparison with the judge, and invalid-key handling.

Mocked responses are used only in the automated tests. `test-grok-windows.bat` runs both the tests and the live check on Windows.

## 7. Limitations (say these in your viva)
- PlantVillage images are lab photos of single leaves; accuracy on field photos will be lower. Only the 19 trained classes can be predicted.
- The crop-recommendation dataset is a clean benchmark; its N/P/K scale is not soil-test kg/ha, and near-perfect scores do not transfer to real farms.
- Groundedness, answer relevance and citation correctness are embedding-similarity proxies. Faithfulness uses Grok to judge Grok's own answers, which can be lenient (self-evaluation bias). For a viva, back these up with a small manual review of sampled answers.
- Grok results vary between runs and over time as xAI updates models. Record the model ID shown in each run.
- District statistics end in 2015; market prices appear only after you fetch or import them.
- Scheme rules change — the app shows the verification date and official links.
- The knowledge base is a demonstration corpus; upload ICAR, UAS or KVK publications to extend it.

## 8. Project structure
```
agrimind/
├─ setup-windows.bat, start-windows.bat, test-grok-windows.bat, start-dev.sh
├─ backend/
│  ├─ app/            core.py, rag.py, llm.py, disease.py, agro.py, evaluation.py, main.py
│  ├─ data/           knowledge/*.md, schemes.json, eval/rag_benchmark.json, datasets, sample_leaves/
│  ├─ models/         disease_model.pt, crop_model.joblib, *_metrics.json
│  ├─ training/       train_disease.py, train_crop.py, fetch_plantvillage.py
│  ├─ scripts/        grok_integration_check.py (genuine xAI check)
│  ├─ tests/          test_api.py, test_xai.py, test_xai_live.py, conftest.py
│  └─ storage/        created at runtime: SQLite DB, FAISS index, uploads (delete to reset)
└─ frontend/          React + TypeScript source; dist/ is the built app served by FastAPI
```
## 9. API reference
Interactive documentation is at <http://127.0.0.1:8000/docs> while the server is running. LLM-related endpoints:

| Method & path | Role | Purpose |
|---|---|---|
| `POST /api/chat` | user | RAG chat with Grok; returns answer, citations, grounding, latency, `usage` |
| `POST /api/farming/advisor` | user | Farm plan from farm context + retrieved documents |
| `POST /api/soil/analyse` | user | Soil ratings; Grok writes the plain-language summary from the computed facts |
| `POST /api/lab/compare` | user | Baseline vs prompt-engineered vs RAG-grounded Grok on one question (`judge`, `reference` optional) |
| `POST /api/eval/run` | user | Background retrieval or generation evaluation (`kind`, `n`, `judge`) |
| `GET /api/eval/runs/{id}/download?fmt=csv\|json` | user | Measured results |
| `GET /api/admin/settings` | admin | Settings without secrets (`xai_api_key_set`, `xai_api_key_source`) plus provider status |
| `PUT /api/admin/settings` | admin | Update settings; for keys: `""` keeps, `null` removes, a value replaces |
| `POST /api/admin/settings/test` | admin | One real request; returns ok/error kind, model, latency, token usage |
| `GET /api/admin/models` | admin | Models available to the configured key |
| `GET /api/health` | public | Provider, model and whether it is configured (never the key) |
