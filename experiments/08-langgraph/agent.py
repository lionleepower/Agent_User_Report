"""
Experiment 08: an agentic RAG loop in LangGraph, following the structure of the
official "agentic RAG" tutorial: the model decides whether to call the
retriever tool, a grader checks the retrieved passages, an unhelpful result
triggers a question rewrite and another retrieval (at most 2 rounds), then the
answer is generated with the same strict "material only" rule as every other
experiment.

Retriever: LangChain dense retrieval on DashScope embeddings (the "fixed"
configuration of experiment 02), top 5. Model: deepseek-chat for every node.
Questions: the 48 labelled M-tier questions, clean and with simulated ASR
noise (experiment 03), to see whether rewriting helps noisy questions.

  npx electron tools/retrieval-bench/with-keys.cjs --profile <userData> --run \
    "%LOCALAPPDATA%/llm-bench/experiments/venv/Scripts/python.exe" experiments/08-langgraph/agent.py

Reads <BENCH_DIR>/experiments/02-data.json and experiments/03-asr-noise/noisy.jsonl;
writes <BENCH_DIR>/experiments/08-answers.json (judged by run.ts).
"""
import json
import os
import socket
import sys
import time
from typing import Literal

_getaddrinfo = socket.getaddrinfo
socket.getaddrinfo = lambda host, port, family=0, *a, **k: _getaddrinfo(host, port, socket.AF_INET, *a, **k)

from langchain_core.callbacks import BaseCallbackHandler  # noqa: E402
from langchain_core.documents import Document  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langchain_core.vectorstores import InMemoryVectorStore  # noqa: E402
from langchain_openai import ChatOpenAI, OpenAIEmbeddings  # noqa: E402
from langchain_text_splitters import RecursiveCharacterTextSplitter  # noqa: E402
from langgraph.graph import END, START, MessagesState, StateGraph  # noqa: E402
from langgraph.prebuilt import ToolNode, tools_condition  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

BENCH = os.environ.get("BENCH_DIR") or os.path.join(os.environ["LOCALAPPDATA"], "llm-bench")
RAW = os.path.join(BENCH, "experiments")
HERE = os.path.dirname(os.path.abspath(__file__))
DS_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
RULES = "你是我的面试助手，面试官刚问了我一个技术问题。只根据【参考资料】回答，口语化、简洁，不超过150字；资料里没有答案时，只回答“资料中没有相关内容”，不要用常识补充。"
MAX_ROUNDS = 2

data = json.load(open(os.path.join(RAW, "02-data.json"), encoding="utf-8"))
noisy = {r["id"]: r["asr"] for r in map(json.loads, open(os.path.join(HERE, "..", "03-asr-noise", "noisy.jsonl"), encoding="utf-8"))}


class RetryingEmbeddings(OpenAIEmbeddings):
    """DashScope reports a busy backend as HTTP 400; retry batches of 10 (see experiment 02)."""

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


class Usage:
    """counted explicitly at every model call site (callbacks miss calls made inside conditional edges)"""

    def __init__(self):
        self.reset()

    def reset(self):
        self.calls = self.prompt = self.hit = self.out = 0
        self.sites = {}

    def add(self, msg, site="?"):
        self.calls += 1
        self.sites[site] = self.sites.get(site, 0) + 1
        u = getattr(msg, "usage_metadata", None) or {}
        self.prompt += u.get("input_tokens", 0)
        self.out += u.get("output_tokens", 0)
        self.hit += (u.get("input_token_details") or {}).get("cache_read", 0)
        return msg


USAGE = Usage()


class CallCounter(BaseCallbackHandler):
    """model calls and token usage per question (DeepSeek reports cache hits)"""

    def __init__(self):
        self.calls = 0
        self.prompt = 0
        self.hit = 0
        self.out = 0

    def on_chat_model_start(self, *a, **k):
        self.calls += 1

    def on_llm_end(self, response, **k):
        for gens in response.generations:
            for g in gens:
                u = getattr(getattr(g, "message", None), "usage_metadata", None) or {}
                self.prompt += u.get("input_tokens", 0)
                self.out += u.get("output_tokens", 0)
                self.hit += (u.get("input_token_details") or {}).get("cache_read", 0)


t = time.perf_counter()
splits = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200).split_documents([Document(page_content=d["text"], metadata={"source": d["name"]}) for d in data["docs"]])
emb = RetryingEmbeddings(model="text-embedding-v4", base_url=DS_BASE, api_key=os.environ["BENCH_DASHSCOPE_KEY"], check_embedding_ctx_length=False, chunk_size=10)
retriever = InMemoryVectorStore.from_documents(splits, emb).as_retriever(search_kwargs={"k": 5})
build_ms = round((time.perf_counter() - t) * 1000)


@tool
def retrieve_notes(query: str) -> str:
    """在我的备考笔记里检索与问题相关的资料段落。"""
    return "\n\n".join(f"[{i + 1}] {d.page_content}" for i, d in enumerate(retriever.invoke(query)))


llm = ChatOpenAI(model="deepseek-chat", base_url=os.environ["BENCH_LLM_BASE"], api_key=os.environ["BENCH_LLM_KEY"], temperature=0.2, max_tokens=400, stream_usage=True)


class Grade(BaseModel):
    binary_score: Literal["yes", "no"] = Field(description="资料是否与问题相关：yes 或 no")


def generate_query_or_respond(state: MessagesState):
    return {"messages": [USAGE.add(llm.bind_tools([retrieve_notes]).invoke(state["messages"]), "decide")]}


def last_step_context(msgs) -> str:
    """every passage of the last retrieval step (the model may send several queries at once)"""
    last_ai = max(i for i, m in enumerate(msgs) if getattr(m, "type", "") == "ai" and getattr(m, "tool_calls", None))
    return "\n\n".join(m.content for m in msgs[last_ai + 1 :] if getattr(m, "type", "") == "tool")


def grade_documents(state: MessagesState) -> Literal["generate_answer", "rewrite_question"]:
    question = state["messages"][0].content
    context = last_step_context(state["messages"])
    # retrieval STEPS, not tool messages: the model often sends two queries in one step (parallel tool calls)
    rounds = sum(1 for m in state["messages"] if getattr(m, "type", "") == "ai" and getattr(m, "tool_calls", None))
    if rounds >= MAX_ROUNDS:
        return "generate_answer"
    res = llm.with_structured_output(Grade, method="function_calling", include_raw=True).invoke(
        [HumanMessage(content=f"判断检索到的资料是否与问题相关。\n问题：{question}\n资料：\n{context}\n相关就回答 yes，否则 no。")]
    )
    USAGE.add(res["raw"], "grade")
    grade = res["parsed"]
    return "generate_answer" if grade is not None and grade.binary_score == "yes" else "rewrite_question"


def rewrite_question(state: MessagesState):
    question = state["messages"][0].content
    better = USAGE.add(site="rewrite", msg=llm.invoke([HumanMessage(content=f"这个问题来自语音识别，可能有错字或口语。把它改写成一个清楚、适合检索的技术问题，只输出改写后的问题：\n{question}")]))
    return {"messages": [HumanMessage(content=better.content)]}


def generate_answer(state: MessagesState):
    question = state["messages"][0].content
    context = last_step_context(state["messages"])
    return {"messages": [USAGE.add(llm.invoke([("system", RULES), ("user", f"【参考资料】\n{context}\n【参考资料结束】\n\n面试官问：{question}")]), "answer")]}


g = StateGraph(MessagesState)
g.add_node(generate_query_or_respond)
g.add_node("retrieve", ToolNode([retrieve_notes]))
g.add_node(rewrite_question)
g.add_node(generate_answer)
g.add_edge(START, "generate_query_or_respond")
g.add_conditional_edges("generate_query_or_respond", tools_condition, {"tools": "retrieve", END: END})
g.add_conditional_edges("retrieve", grade_documents)
g.add_edge("generate_answer", END)
g.add_edge("rewrite_question", "generate_query_or_respond")
graph = g.compile()

out = {"buildMs": build_ms, "records": []}
LIMIT = int(os.environ.get("AGENT_LIMIT", "0"))  # debugging: first N questions per variant
OUT = os.path.join(RAW, "08-answers.json" if not LIMIT else "08-answers-debug.json")
for variant in ("clean", "asr"):
    for q in data["questions"][: LIMIT or None]:
        text = q["question"] if variant == "clean" else noisy.get(q["id"])
        if not text:
            continue
        USAGE.reset()
        nodes = {"retrieve": 0, "rewrite_question": 0}
        t0 = time.perf_counter()
        first_answer = None
        answer = ""
        try:
            for mode, payload in graph.stream({"messages": [HumanMessage(content=text)]}, stream_mode=["messages", "updates"], config={"recursion_limit": 20}):
                if mode == "updates":
                    for node in payload or {}:
                        if node in nodes:
                            nodes[node] += 1
                    continue
                chunk, meta = payload
                node = meta.get("langgraph_node")
                if node in ("generate_answer", "generate_query_or_respond") and getattr(chunk, "content", "") and not getattr(chunk, "tool_call_chunks", None):
                    if first_answer is None:
                        first_answer = time.perf_counter() - t0
                    answer += chunk.content
            err = None
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:200]
        out["records"].append({
            "id": q["id"], "variant": variant, "answer": answer, "error": err,
            "llmCalls": USAGE.calls, "callSites": dict(USAGE.sites), "retrievals": nodes["retrieve"], "rewrites": nodes["rewrite_question"],
            "promptTokens": USAGE.prompt, "cacheHitTokens": USAGE.hit, "outputTokens": USAGE.out,
            "firstAnswerMs": round(first_answer * 1000) if first_answer else -1,
            "totalMs": round((time.perf_counter() - t0) * 1000),
        })
        print(f"\r{variant} {len(out['records'])}", end="", flush=True)
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\ndone")
