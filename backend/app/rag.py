"""Document processing, embeddings, FAISS vector index and Retrieval-Augmented Generation."""
import csv
import hashlib
import io
import json
import logging
import os
import re
import threading
import time

import faiss
import numpy as np

from .core import DATA, STORE, UPLOADS, execute, get_setting, row, rows
from . import llm

log = logging.getLogger("agrimind.rag")
INDEX_FILE, META_FILE = STORE / "index.faiss", STORE / "index_meta.json"
LANG_NAMES = {"en": "English", "kn": "Kannada (ಕನ್ನಡ)", "hi": "Hindi (हिन्दी)"}
ALLOWED = {".pdf", ".docx", ".txt", ".md", ".csv"}


# ------------------------------------------------------------------ extraction & chunking
def extract(filename: str, raw: bytes) -> list[tuple[str, int | None]]:
    """Return a list of (text, page) segments."""
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        return [(p.extract_text() or "", i + 1) for i, p in enumerate(reader.pages)]
    if ext == ".docx":
        import docx
        d = docx.Document(io.BytesIO(raw))
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for r in t.rows:
                parts.append(" | ".join(c.text.strip() for c in r.cells))
        return [("\n".join(parts), None)]
    text = raw.decode("utf-8", errors="replace")
    if ext == ".csv":
        rdr = list(csv.reader(io.StringIO(text)))
        if not rdr:
            return [("", None)]
        head, out = rdr[0], []
        for r in rdr[1:]:
            out.append("; ".join(f"{h.strip()}: {v.strip()}" for h, v in zip(head, r) if v.strip()))
        return [("\n".join(out), None)]
    return [(text, None)]


_SENT_SPLIT = re.compile(r"(?<=[.!?।])\s+|\n(?=\s*[-*•|\d])|\n{2,}")


def _sections(text):
    """Split markdown-like text into (heading_path, body) sections; plain text becomes one section."""
    out, path, buf = [], [], []
    for line in text.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            if "".join(buf).strip():
                out.append((" > ".join(path), "\n".join(buf).strip()))
            level = len(m.group(1))
            path = path[: level - 1] + [m.group(2).strip()]
            buf = []
        else:
            buf.append(line)
    if "".join(buf).strip():
        out.append((" > ".join(path), "\n".join(buf).strip()))
    return out


def chunk(segments, size=900, overlap=150):
    """Section-aware chunking: chunks never cross a heading; consecutive chunks overlap by whole sentences;
    each chunk is prefixed with its heading path for context."""
    chunks = []
    for text, page in segments:
        text = re.sub(r"[ \t]+", " ", text or "").strip()
        for heading, body in _sections(text):
            sents = [s.strip() for s in _SENT_SPLIT.split(body) if s and s.strip()]
            prefix = f"[{heading}]\n" if heading else ""
            buf: list[str] = []
            for s in sents:
                while len(s) > size:  # pathological long sentence/table row
                    buf.append(s[:size]); s = s[size:]
                if buf and len(prefix) + sum(len(x) + 1 for x in buf) + len(s) > size:
                    chunks.append((prefix + "\n".join(buf), page))
                    keep, n = [], 0
                    for x in reversed(buf):  # sentence-level overlap
                        if n + len(x) > overlap:
                            break
                        keep.insert(0, x); n += len(x)
                    buf = keep
                buf.append(s)
            if buf:
                chunks.append((prefix + "\n".join(buf), page))
    return [(c.strip(), pg) for c, pg in chunks if len(c.strip()) > 40]


# ------------------------------------------------------------------ embeddings
def embedding_backend() -> str:
    """'tfidf' (keyword search, low memory) or 'sentence-transformers' (multilingual semantic search).

    EMBEDDING_BACKEND=auto (default) picks keyword search on Render or when AGRIMIND_LITE=1,
    and the Sentence-Transformer elsewhere (if installed)."""
    mode = os.environ.get("EMBEDDING_BACKEND", "auto").strip().lower()
    if mode in ("tfidf", "keyword", "lite"):
        return "tfidf"
    if mode == "auto" and (os.environ.get("RENDER") or os.environ.get("AGRIMIND_LITE", "").strip() in ("1", "true", "yes")):
        return "tfidf"
    return "sentence-transformers"


class Embedder:
    def __init__(self, name: str):
        self.name, self.kind, self.model, self.vec, self.error = name, None, None, None, None
        if embedding_backend() == "tfidf":  # lite mode: never import torch / load the 470 MB model
            self.kind, self.device, self.dim, self.lite = "tfidf-fallback", "cpu", None, True
            log.info("Lite mode: keyword (TF-IDF) retrieval; Sentence-Transformer not loaded.")
            return
        self.lite = False
        try:
            import torch
            from sentence_transformers import SentenceTransformer
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self.model = SentenceTransformer(name, device=device)
            self.kind, self.device = "sentence-transformers", device
            m = self.model
            self.dim = (m.get_embedding_dimension if hasattr(m, "get_embedding_dimension") else m.get_sentence_embedding_dimension)()
        except Exception as e:  # noqa: BLE001  (not installed, no internet on first run, etc.)
            log.warning("Sentence-Transformer '%s' unavailable (%s). Using TF-IDF/LSA fallback embeddings.", name, e)
            self.kind, self.device, self.dim, self.error = "tfidf-fallback", "cpu", None, str(e)[:300]

    @property
    def signature(self):
        return f"{self.kind}:{self.name}"

    def fit(self, corpus: list[str]):
        if self.kind == "sentence-transformers":
            return
        from sklearn.feature_extraction.text import TfidfVectorizer
        corpus = corpus or ["agriculture crop soil water farmer"]
        self.vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, max_features=4096, stop_words="english")
        self.vec.fit(corpus)
        self.dim = len(self.vec.vocabulary_)

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim or 1), dtype="float32")
        if self.kind == "sentence-transformers":
            v = self.model.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
        else:
            v = self.vec.transform(texts).toarray()
            v = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)
        return np.asarray(v, dtype="float32")

    def info(self):
        d = {"kind": self.kind, "model": self.name, "dim": self.dim, "device": self.device}
        if self.kind != "sentence-transformers" and getattr(self, "lite", False):
            d["note"] = ("Lite mode (low-memory server): keyword TF-IDF retrieval. Set EMBEDDING_BACKEND=sentence-transformers "
                         "on a machine with more RAM for multilingual semantic search.")
        elif self.kind != "sentence-transformers":
            d["note"] = ("Sentence-Transformer model could not be loaded (it downloads from Hugging Face on first run). "
                         "Using a lexical TF-IDF fallback so search keeps working; semantic and cross-language "
                         "retrieval need the Sentence-Transformer model.")
        return d


# ------------------------------------------------------------------ vector store
class VectorStore:
    def __init__(self):
        self.lock = threading.RLock()
        self.embedder: Embedder | None = None
        self.index = None

    def load(self):
        with self.lock:
            self.embedder = Embedder(get_setting("embedding_model"))
            meta = json.loads(META_FILE.read_text()) if META_FILE.exists() else {}
            n_chunks = row("SELECT COUNT(*) n FROM chunks")["n"]
            if (self.embedder.kind == "sentence-transformers" and INDEX_FILE.exists()
                    and meta.get("signature") == self.embedder.signature and meta.get("n") == n_chunks):
                self.index = faiss.read_index(str(INDEX_FILE))
            else:
                self.rebuild()

    def rebuild(self):
        with self.lock:
            ch = rows("SELECT id, text FROM chunks ORDER BY id")
            self.embedder.fit([c["text"] for c in ch])
            self.index = faiss.IndexIDMap2(faiss.IndexFlatIP(self.embedder.dim))
            if ch:
                vecs = self.embedder.encode([c["text"] for c in ch])
                self.index.add_with_ids(vecs, np.array([c["id"] for c in ch], dtype="int64"))
            self._save()

    def _save(self):
        faiss.write_index(self.index, str(INDEX_FILE))
        META_FILE.write_text(json.dumps({"signature": self.embedder.signature, "n": int(self.index.ntotal),
                                         "dim": self.embedder.dim, "saved": time.time()}))

    def add(self, ids, texts):
        with self.lock:
            if self.embedder.kind != "sentence-transformers":
                return self.rebuild()  # fallback vectoriser is corpus-fitted
            self.index.add_with_ids(self.embedder.encode(texts), np.array(ids, dtype="int64"))
            self._save()

    def remove(self, ids):
        with self.lock:
            if ids:
                self.index.remove_ids(np.array(ids, dtype="int64"))
                self._save()

    def search(self, query: str, k: int = 4, doc_ids: list[int] | None = None):
        with self.lock:
            if self.index is None or self.index.ntotal == 0:
                return []
            qv = self.embedder.encode([query])
            D, I = self.index.search(qv, min(self.index.ntotal, k * 4 if doc_ids else k))
        hits = []
        for score, cid in zip(D[0], I[0]):
            if cid < 0:
                continue
            c = row("SELECT c.id, c.text, c.page, c.idx, c.document_id, d.title, d.filename FROM chunks c "
                    "JOIN documents d ON d.id=c.document_id WHERE c.id=?", (int(cid),))
            if c and (not doc_ids or c["document_id"] in doc_ids):
                c["score"] = round(float(score), 4)
                hits.append(c)
        return hits[:k]


store = VectorStore()


# ------------------------------------------------------------------ ingestion
def ingest(filename: str, raw: bytes, user_id=None, is_demo=False, title=None):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED:
        raise ValueError(f"Unsupported file type {ext}. Allowed: {', '.join(sorted(ALLOWED))}")
    sha = hashlib.sha256(raw).hexdigest()
    if row("SELECT id FROM documents WHERE sha256=?", (sha,)):
        raise ValueError("This document is already in the knowledge base.")
    segs = extract(filename, raw)
    pieces = chunk(segs, int(get_setting("chunk_size")), int(get_setting("chunk_overlap")))
    if not pieces:
        raise ValueError("No extractable text found (scanned PDFs need OCR first).")
    if not title:
        first = next((t for t, _ in segs if t.strip()), "")
        m = re.match(r"\s*#\s*(.+)", first)
        title = m.group(1).strip() if m else os.path.splitext(filename)[0].replace("_", " ")
    doc_id = execute("INSERT INTO documents(filename,title,file_type,size_bytes,n_chunks,uploaded_by,is_demo,created_at,sha256)"
                     " VALUES(?,?,?,?,?,?,?,?,?)", (filename, title, ext[1:], len(raw), len(pieces), user_id,
                                                    int(is_demo), time.time(), sha))
    (UPLOADS / f"{doc_id}_{os.path.basename(filename)}").write_bytes(raw)
    ids = [execute("INSERT INTO chunks(document_id,idx,text,page) VALUES(?,?,?,?)", (doc_id, i, t, pg))
           for i, (t, pg) in enumerate(pieces)]
    store.add(ids, [t for t, _ in pieces])
    return row("SELECT * FROM documents WHERE id=?", (doc_id,))


def delete_document(doc_id: int):
    ids = [r["id"] for r in rows("SELECT id FROM chunks WHERE document_id=?", (doc_id,))]
    d = row("SELECT * FROM documents WHERE id=?", (doc_id,))
    execute("DELETE FROM chunks WHERE document_id=?", (doc_id,))
    execute("DELETE FROM documents WHERE id=?", (doc_id,))
    if store.embedder and store.embedder.kind != "sentence-transformers":
        store.rebuild()
    else:
        store.remove(ids)
    if d:
        f = UPLOADS / f"{doc_id}_{os.path.basename(d['filename'])}"
        f.unlink(missing_ok=True)


def seed_demo_documents():
    folder = DATA / "knowledge"
    have = {r["filename"] for r in rows("SELECT filename FROM documents")}
    for f in sorted(folder.glob("*")):
        if f.suffix.lower() in ALLOWED and f.name not in have:
            try:
                ingest(f.name, f.read_bytes(), is_demo=True)
            except ValueError as e:
                log.warning("Skipping %s: %s", f.name, e)


# ------------------------------------------------------------------ prompts
BASE_SYSTEM = "You are a helpful assistant."

EXPERT_SYSTEM = """You are AgriMind, an agricultural extension advisor for farmers in India (especially Karnataka).
Guidelines:
- Give practical, step-by-step guidance a smallholder farmer can act on; prefer integrated and low-cost practices first.
- Mention crop stage, season (Kharif/Rabi/Zaid), soil and local conditions when they change the advice.
- For pesticides/fertilisers give the product type and stress following the label dose and safety interval; never invent dosages you are unsure of.
- If the question lacks key details (crop, stage, location), state your assumptions briefly.
- If you are not sure, say so and recommend the local Krishi Vigyan Kendra (KVK) or agriculture officer.
- Use short headings and bullet points. Keep answers under 250 words unless asked for more.
- Answer only agricultural and rural-livelihood questions; politely decline unrelated requests."""

RAG_RULES = """
You are given numbered SOURCES retrieved from the AgriMind knowledge base.
- Base your answer on the SOURCES. Cite every factual statement with its source number in square brackets, e.g. [1] or [2][3].
- If the SOURCES do not contain the answer, say clearly that the knowledge base does not cover it, then give only brief general guidance marked "(general knowledge)".
- Do not invent numbers, dosages, scheme amounts or dates that are not in the SOURCES."""


def lang_instruction(lang):
    if lang in ("kn", "hi"):
        return (f"\nRespond entirely in {LANG_NAMES[lang]}, using simple words a farmer understands. "
                "Keep crop, chemical and scheme names recognisable (you may add the English name in brackets).")
    return "\nRespond in English."


def format_sources(hits):
    return "\n\n".join(f"[{i + 1}] (from: {h['title']}{', p.' + str(h['page']) if h.get('page') else ''})\n{h['text']}"
                       for i, h in enumerate(hits))


def build_prompt(mode: str, question: str, lang: str, hits=None):
    if mode == "baseline":
        return BASE_SYSTEM, question
    if mode == "engineered":
        return EXPERT_SYSTEM + lang_instruction(lang), question
    return (EXPERT_SYSTEM + RAG_RULES + lang_instruction(lang),
            f"SOURCES:\n{format_sources(hits or [])}\n\nQUESTION: {question}")


def citations_from(hits):
    return [{"n": i + 1, "document_id": h["document_id"], "title": h["title"], "filename": h["filename"],
             "page": h.get("page"), "score": h["score"], "snippet": h["text"][:400]} for i, h in enumerate(hits)]


# ------------------------------------------------------------------ groundedness
_SENT = re.compile(r"(?<=[.!?।])\s+|\n+")


def split_claims(answer: str):
    out = []
    for s in _SENT.split(answer or ""):
        s = re.sub(r"\[\d+\]", "", s).strip(" -*•#\t")
        if len(s) >= 25 and not s.endswith(":"):
            out.append(s)
    return out


def groundedness(answer: str, hits, threshold=None):
    """Embedding-based support check: a claim is supported if its best cosine similarity with any retrieved
    chunk is >= threshold. Returns groundedness (supported share) and unsupported-claim rate."""
    claims = split_claims(answer)
    if not claims or not hits:
        return {"groundedness": None, "unsupported_rate": None, "n_claims": len(claims), "claims": []}
    th = float(threshold if threshold is not None else get_setting("grounding_threshold"))
    emb = store.embedder
    # compare against chunk windows (sentences of sources) for finer matching
    src_sents = [s for h in hits for s in split_claims(h["text"])] or [h["text"] for h in hits]
    C, S = emb.encode(claims), emb.encode(src_sents + [h["text"] for h in hits])
    sims = C @ S.T
    best = sims.max(axis=1)
    sup = best >= th
    return {"groundedness": round(float(sup.mean()), 4), "unsupported_rate": round(float(1 - sup.mean()), 4),
            "n_claims": len(claims), "threshold": th,
            "claims": [{"text": c, "support": round(float(b), 3), "supported": bool(s)} for c, b, s in zip(claims, best, sup)]}


# ------------------------------------------------------------------ answering
def answer(question: str, lang="en", history=None, mode="rag", k=None):
    k = int(k or get_setting("top_k"))
    hits = store.search(question if not history else _retrieval_query(question, history), k) if mode == "rag" else []
    system, user_msg = build_prompt(mode, question, lang, hits)
    msgs = list(history or [])[-8:] + [{"role": "user", "content": user_msg}]
    t0 = time.perf_counter()
    try:
        res = llm.generate(system, msgs)
    except llm.LLMUnavailable as e:
        if mode != "rag":
            raise
        res = {"text": _extractive(hits, lang, str(e)), "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
               "provider": "none (retrieval only)", "model": store.embedder.name, "fallback": True, "error": str(e)}
    g = groundedness(res["text"], hits) if hits and not res.get("fallback") else {"groundedness": None, "unsupported_rate": None}
    return {**res, "citations": citations_from(hits), "grounding": g, "mode": mode}


def _retrieval_query(q, history):
    prev = [m["content"] for m in history if m["role"] == "user"]
    return (prev[-1][:300] + " " + q) if prev and len(q.split()) < 8 else q


def _extractive(hits, lang, err):
    head = {"en": "⚠️ The language model is not available, so here are the most relevant passages from the knowledge base:",
            "kn": "⚠️ ಭಾಷಾ ಮಾದರಿ ಲಭ್ಯವಿಲ್ಲ. ಜ್ಞಾನ ಭಂಡಾರದಿಂದ ಅತ್ಯಂತ ಸಂಬಂಧಿತ ಭಾಗಗಳು ಇಲ್ಲಿವೆ (ಇಂಗ್ಲಿಷ್‌ನಲ್ಲಿ):",
            "hi": "⚠️ भाषा मॉडल उपलब्ध नहीं है, इसलिए ज्ञान आधार से सबसे प्रासंगिक अंश यहाँ हैं (अंग्रेज़ी में):"}[lang if lang in LANG_NAMES else "en"]
    if not hits:
        return head + "\n\n_No matching passages found._\n\n`" + err + "`"
    body = "\n\n".join(f"**[{i + 1}] {h['title']}**\n> " + h["text"][:600].replace("\n", "\n> ") for i, h in enumerate(hits))
    return f"{head}\n\n{body}\n\n_Reason: {err}_"
