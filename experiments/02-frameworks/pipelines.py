"""
Experiment 02: the same corpus and questions through LangChain and LlamaIndex.

Each configuration retrieves context for the 48 labelled questions; run.ts then
answers every configuration with the same model, prompt and judge, so only the
retrieval differs. "default" = what the frameworks' getting-started guides do
(default splitter, default top-k, default BM25 tokenisation); "tuned" = the
smallest change that makes it work for Chinese. One configuration is also run
end to end as shipped (LlamaIndex query engine with its own prompt).

  npx electron tools/retrieval-bench/with-keys.cjs --profile <userData> --run \
    "%LOCALAPPDATA%/llm-bench/experiments/venv/Scripts/python.exe" experiments/02-frameworks/pipelines.py

Reads <BENCH_DIR>/experiments/02-data.json, writes 02-contexts.json there.
Network: IPv4 only (HTTP clients here resolve through the same IPv4 proxy).
"""
import json
import os
import socket
import sys
import time
import traceback

# IPv4 only (AGENTS.md): make every resolver return A records
_getaddrinfo = socket.getaddrinfo
socket.getaddrinfo = lambda host, port, family=0, *a, **k: _getaddrinfo(host, port, socket.AF_INET, *a, **k)

BENCH = os.environ.get("BENCH_DIR") or os.path.join(os.environ["LOCALAPPDATA"], "llm-bench")
RAW = os.path.join(BENCH, "experiments")
DS_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DS_KEY = os.environ.get("BENCH_DASHSCOPE_KEY", "")
LLM_BASE = os.environ.get("BENCH_LLM_BASE", "")
LLM_KEY = os.environ.get("BENCH_LLM_KEY", "")
LLM_MODEL = os.environ.get("BENCH_LLM_MODEL", "")

data = json.load(open(os.path.join(RAW, "02-data.json"), encoding="utf-8"))
DOCS, QS = data["docs"], data["questions"]
OUT_FILE = os.path.join(RAW, "02-contexts.json")
# --only a,b: rerun just these configurations and merge into the existing results
ONLY = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None
out = json.load(open(OUT_FILE, encoding="utf-8")) if ONLY and os.path.exists(OUT_FILE) else {"configs": {}, "imports": {}}


def timed_import(name, fn):
    t = time.perf_counter()
    fn()
    out["imports"][name] = round((time.perf_counter() - t) * 1000)


def run_config(name, build, retrieve, notes=""):
    """build() -> state; retrieve(state, question) -> [text]"""
    if ONLY and name not in ONLY:
        return
    rec = {"notes": notes, "questions": {}}
    try:
        t = time.perf_counter()
        state = build()
        rec["buildMs"] = round((time.perf_counter() - t) * 1000)
        lat = []
        for q in QS:
            t = time.perf_counter()
            texts = retrieve(state, q["question"])
            lat.append((time.perf_counter() - t) * 1000)
            rec["questions"][q["id"]] = texts
        lat.sort()
        rec["retrieveMsP50"] = round(lat[len(lat) // 2], 1)
    except Exception as e:  # a configuration that fails is a result too
        rec["error"] = f"{type(e).__name__}: {e}"[:400]
        rec["trace"] = traceback.format_exc()[-800:]
    out["configs"][name] = rec
    print(f"{name}: {'ERROR ' + rec['error'][:120] if 'error' in rec else 'ok'}", flush=True)


# ---------------- LangChain ----------------
timed_import("langchain", lambda: __import__("langchain_community.retrievers") and __import__("langchain_openai") and __import__("langchain_text_splitters") and __import__("langchain_core.vectorstores"))
from langchain_core.documents import Document  # noqa: E402
from langchain_text_splitters import RecursiveCharacterTextSplitter  # noqa: E402
from langchain_community.retrievers import BM25Retriever  # noqa: E402
from langchain_core.vectorstores import InMemoryVectorStore  # noqa: E402
from langchain_openai import OpenAIEmbeddings  # noqa: E402

LC_DOCS = [Document(page_content=d["text"], metadata={"source": d["name"]}) for d in DOCS]


def lc_splits(size=1000, overlap=200):
    # the chunk size and overlap of LangChain's RAG tutorial
    return RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap).split_documents(LC_DOCS)


run_config(
    "langchain-bm25-default",
    lambda: BM25Retriever.from_documents(lc_splits()),
    lambda r, q: [d.page_content for d in r.invoke(q)],
    "RecursiveCharacterTextSplitter(1000/200) + BM25Retriever, default k=4, default tokeniser (str.split)",
)

import jieba  # noqa: E402

jieba.setLogLevel(60)
run_config(
    "langchain-bm25-jieba",
    lambda: BM25Retriever.from_documents(lc_splits(), preprocess_func=jieba.lcut_for_search, k=3),
    lambda r, q: [d.page_content for d in r.invoke(q)],
    "same splits, jieba tokeniser, k=3",
)


class RetryingEmbeddings(OpenAIEmbeddings):
    """DashScope intermittently answers a busy backend with HTTP 400 ("Receive batching
    backend response failed"), which the OpenAI client does not retry: retry batches of 10 here."""

    def embed_documents(self, texts, chunk_size=None, **kw):
        out = []
        for i in range(0, len(texts), 10):
            for attempt in range(5):
                try:
                    out.extend(super().embed_documents(texts[i : i + 10], **kw))
                    break
                except Exception:
                    if attempt == 4:
                        raise
                    time.sleep(1.5 * (attempt + 1))
        return out


def lc_embeddings(defaults=True):
    if defaults:
        return OpenAIEmbeddings(model="text-embedding-v4", base_url=DS_BASE, api_key=DS_KEY)
    # DashScope's OpenAI-compatible endpoint wants raw strings (not tiktoken ids) and ≤10 inputs per call
    return RetryingEmbeddings(model="text-embedding-v4", base_url=DS_BASE, api_key=DS_KEY, check_embedding_ctx_length=False, chunk_size=10)


run_config(
    "langchain-dense-default",
    lambda: InMemoryVectorStore.from_documents(lc_splits(), lc_embeddings(True)).as_retriever(),
    lambda r, q: [d.page_content for d in r.invoke(q)],
    "OpenAIEmbeddings pointed at DashScope with defaults, InMemoryVectorStore, default k=4",
)
run_config(
    "langchain-dense-fixed",
    lambda: InMemoryVectorStore.from_documents(lc_splits(), lc_embeddings(False)).as_retriever(search_kwargs={"k": 3}),
    lambda r, q: [d.page_content for d in r.invoke(q)],
    "check_embedding_ctx_length=False, chunk_size=10 and a retry wrapper (all needed for DashScope), k=3",
)

# ---------------- LlamaIndex ----------------
timed_import("llamaindex", lambda: __import__("llama_index.core") and __import__("llama_index.retrievers.bm25") and __import__("llama_index.embeddings.openai_like") and __import__("llama_index.llms.openai_like"))
from llama_index.core import Document as LIDocument, Settings, VectorStoreIndex  # noqa: E402
from llama_index.core.node_parser import SentenceSplitter  # noqa: E402
from llama_index.retrievers.bm25 import BM25Retriever as LIBM25  # noqa: E402
from llama_index.embeddings.openai_like import OpenAILikeEmbedding  # noqa: E402
from llama_index.llms.openai_like import OpenAILike  # noqa: E402

Settings.embed_model = OpenAILikeEmbedding(model_name="text-embedding-v4", api_base=DS_BASE, api_key=DS_KEY, embed_batch_size=10)
Settings.llm = OpenAILike(model=LLM_MODEL, api_base=LLM_BASE.rstrip("/"), api_key=LLM_KEY, is_chat_model=True, context_window=64000, max_tokens=400, temperature=0.2)
LI_DOCS = [LIDocument(text=d["text"], metadata={"source": d["name"]}) for d in DOCS]


def li_nodes(size=None, overlap=None):
    sp = SentenceSplitter() if size is None else SentenceSplitter(chunk_size=size, chunk_overlap=overlap)
    return sp.get_nodes_from_documents(LI_DOCS)


run_config(
    "llamaindex-dense-default",
    lambda: VectorStoreIndex(li_nodes()).as_retriever(),
    lambda r, q: [n.node.get_content() for n in r.retrieve(q)],
    "SentenceSplitter defaults (1024 tokens / 200 overlap), VectorStoreIndex, default similarity_top_k=2",
)
run_config(
    "llamaindex-dense-tuned",
    lambda: VectorStoreIndex(li_nodes(400, 60)).as_retriever(similarity_top_k=3),
    lambda r, q: [n.node.get_content() for n in r.retrieve(q)],
    "SentenceSplitter(400 tokens / 60), similarity_top_k=3",
)
run_config(
    "llamaindex-bm25-default",
    lambda: LIBM25.from_defaults(nodes=li_nodes(), similarity_top_k=2),
    lambda r, q: [n.node.get_content() for n in r.retrieve(q)],
    "BM25Retriever.from_defaults (bm25s, English stemmer and tokenisation), top 2",
)

# as shipped: the query engine with LlamaIndex's own prompts, answering with the same model
shipped = {"notes": "VectorStoreIndex(default splitter).as_query_engine() with default prompts, same LLM", "answers": {}}
try:
    if ONLY and "llamaindex-query-engine" not in ONLY:
        raise StopIteration
    t = time.perf_counter()
    engine = VectorStoreIndex(li_nodes()).as_query_engine()
    shipped["buildMs"] = round((time.perf_counter() - t) * 1000)
    lat = []
    for q in QS:
        t = time.perf_counter()
        shipped["answers"][q["id"]] = str(engine.query(q["question"]))
        lat.append((time.perf_counter() - t) * 1000)
    lat.sort()
    shipped["totalMsP50"] = round(lat[len(lat) // 2])
except StopIteration:
    shipped = out.get("shipped", {}).get("llamaindex-query-engine", shipped)
except Exception as e:
    shipped["error"] = f"{type(e).__name__}: {e}"[:400]
out["shipped"] = {"llamaindex-query-engine": shipped}
print(f"llamaindex-query-engine: {'ERROR ' + shipped['error'][:120] if 'error' in shipped else 'ok'}", flush=True)

json.dump(out, open(OUT_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("imports ms:", out["imports"])
