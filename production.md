# Production Architecture Deep Dive

## The Core Problem at Scale

With 2 `.md` files, everything works trivially. With 500 PDFs (BGP runbooks, OSPF guides, vendor-specific manuals, SOP docs, incident post-mortems), you have three hard problems:

1. **Retrieval quality** — finding the *right* chunks out of 500,000+ vectors
2. **Context window limits** — you can't send 100 relevant chunks to the LLM
3. **Freshness** — runbooks get updated, versions change, old chunks linger

---

## Layer 1: Document Ingestion Pipeline

```
PDF/DOCX/MD
    │
    ▼
[Parser]        ← vendor-specific (pypdf, python-docx, markdownit)
    │
    ▼
[Cleaner]       ← strip headers/footers, fix encoding, normalize whitespace
    │
    ▼
[Chunker]       ← THIS IS THE MOST CRITICAL STEP
    │
    ▼
[Embedder]      ← sentence-transformers or OpenAI
    │
    ▼
[ChromaDB]      ← stores vector + metadata
```

### What chunking actually does

Current setup: `chunk_size=1000, overlap=200` — sliding window.

At 2 files this is fine. At 500 PDFs, naive chunking breaks retrieval because:

```
BAD CHUNK (cuts mid-thought):
"...the BGP session will drop if hold timer expires. To resolve
this issue, first verify the peer IP address is correct and that"
← chunk boundary here →
"the AS number matches on both sides. Use: show bgp neighbors"

These two chunks are semantically incomplete individually.
```

### Production-grade chunking strategies

| Strategy | When to use |
|---|---|
| Recursive character splitter | General prose docs (current approach) |
| Semantic chunking | Split on meaning shifts, not character count |
| Document-structure aware | Split on headers (H1/H2/H3 boundaries) |
| Sentence-window | Small chunks for retrieval, expand to surrounding sentences for context |

For network runbooks specifically, **header-based chunking** is ideal because runbooks are already structured:

```
# BGP Troubleshooting
## Symptom: Peer Down
### Verify Connectivity
...
## Symptom: Route not advertised
...
```

Each section becomes one chunk — semantically complete.

---

## Layer 2: Vector Store at Scale

### What ChromaDB actually stores

```
Collection: "network_runbooks"
┌─────────────────────────────────────────────────────────┐
│ id: "chunk_abc123"                                      │
│ embedding: [0.02, -0.14, 0.87, ...] ← 384 dimensions   │
│ document: "To clear a stuck BGP session, use: clear..."  │
│ metadata: {                                             │
│   source: "bgp_troubleshooting_v3.pdf",                 │
│   page: 14,                                             │
│   runbook_id: "uuid-...",                               │
│   tags: "bgp,cisco,ios-xe",                             │
│   chunk_index: 7,                                       │
│   doc_version: "2024-Q4"                                │
│ }                                                       │
└─────────────────────────────────────────────────────────┘
```

### How vector search works

When an engineer triggers `/diagnose` on incident: *"R1 BGP peer 10.0.0.2 in Idle state since 14:30"*:

```
Query text → embed → query vector [0.11, -0.09, 0.91, ...]
                              │
                              ▼
              ChromaDB computes cosine similarity
              against ALL stored chunk vectors
                              │
                              ▼
              Returns top-k most similar chunks
              (doesn't read text, compares vectors only)
```

**Why this scales:** Cosine similarity on vectors is O(n) but highly parallelizable. ChromaDB at 1M vectors still returns results in <100ms. At 10M+ vectors you'd move to FAISS with HNSW indexing (approximate nearest neighbor) which is O(log n).

### The retrieval quality problem at scale

With 500 docs, you might have 50,000 chunks. The query *"BGP peer Idle state"* might return:

```
Rank 1: [0.94 score] BGP peer troubleshooting - Cisco IOS-XE  ← WANT THIS
Rank 2: [0.91 score] BGP peer troubleshooting - Juniper JunOS  ← also relevant
Rank 3: [0.89 score] BGP session monitoring - general         ← relevant
Rank 4: [0.87 score] OSPF neighbor in DOWN state              ← NOT relevant (similar language)
Rank 5: [0.85 score] BGP peer configured but not connecting   ← relevant
```

Pure vector search can return semantically *similar but wrong* documents. OSPF "neighbor DOWN" and BGP "peer Idle" use similar language but are different protocols.

### Production fix — Hybrid Search

```
Query
  │
  ├── Vector search (semantic)     → top 20 chunks
  │
  └── Keyword search (BM25/TF-IDF) → top 20 chunks
         │                              │
         └──────── RRF Fusion ──────────┘
                        │
                    Reranked top 10
```

Reciprocal Rank Fusion (RRF) combines both lists. A chunk that scores well in *both* vector similarity and keyword match ranks highest. This catches the case where "BGP peer" as an exact phrase matters.

---

## Layer 3: Context Window — The Hard Limit

| Model | Context Window |
|---|---|
| llama3.2 (3B) | 128k tokens |
| Claude Sonnet 4.6 | 200k tokens |
| GPT-4o | 128k tokens |

One chunk ≈ 250 tokens. Theoretically you can send 500+ chunks. **But don't.**

**Why sending all chunks hurts quality:**

This is called the "lost in the middle" problem — LLMs pay most attention to the beginning and end of the context. Relevant information buried in the middle gets ignored.

```
Optimal context size for reasoning: 3-8 chunks
Maximum practical limit: 15-20 chunks (with reranking)
```

### Production strategy — Reranking

```
ChromaDB returns top 20 chunks
         │
         ▼
Cross-encoder reranker (e.g., ms-marco-MiniLM)
  - Takes query + each chunk as pair
  - Scores relevance (0-1) for that specific query
  - Much more accurate than vector similarity alone
         │
         ▼
Top 5 chunks sent to LLM
```

Cross-encoders are slower (evaluate each pair) but far more accurate. Run them on the shortlist, not all 50,000 chunks.

---

## Layer 4: The Agent Pipeline in Depth

### InvestigationAgent

```python
incident = await db.get(incident_id)

# Build a rich query — not just the title
query = f"""
Incident: {incident.title}
Description: {incident.description}
Severity: {incident.severity}
Affected device: {incident.affected_device}
"""

# Multi-query retrieval — one query misses things
queries = [
    f"{incident.title}",                     # exact symptom
    f"{protocol} troubleshooting",           # protocol-level
    f"{vendor} {protocol} configuration",    # vendor-specific
]
# Run all 3, merge results, deduplicate
chunks = await rag.multi_query_retrieve(queries, top_k=5)

# Load CLI context (Week 4: real device, right now: simulator)
cli_output = load_simulator_outputs(incident.affected_device)

return InvestigationContext(
    incident=incident,
    runbook_chunks=chunks,       # 5-10 chunks
    cli_output=cli_output,
    citations=[c.source for c in chunks]
)
```

### AnalysisAgent — the LLM reasoning step

```
System prompt:
"You are a senior NOC engineer. Analyze the following network incident
using the runbook knowledge and CLI output provided. Be specific about
commands and their output."

User message:
[Incident details]
[5 runbook chunks with source citations]
[CLI show outputs]

→ LLM returns: root cause hypothesis, confidence level, evidence
```

Quality of this step depends on:
1. Retrieval quality (did we send the right chunks?)
2. Prompt engineering (did we frame the question correctly?)
3. Model capability (llama3.2 vs Claude Sonnet)

### ReportAgent

```
Input: root cause + evidence + citations

Output (stored as JSONB in incident.ai_report):
{
  "summary": "BGP session between R1 and R2 is in Idle state...",
  "root_cause": "Hold timer expiry due to network congestion...",
  "confidence": 0.87,
  "evidence": [
    {"source": "bgp_troubleshooting_v3.pdf", "page": 14, "relevance": 0.94},
    {"source": "cisco_ios_xe_bgp.pdf", "page": 7, "relevance": 0.91}
  ],
  "steps": [
    "1. Verify BGP peer connectivity: ping 10.0.0.2 source loopback0",
    "2. Check hold timer: show bgp neighbors 10.0.0.2 | i Hold",
    "3. ..."
  ],
  "commands": ["show bgp neighbors", "show bgp summary", "debug bgp events"],
  "escalation": "If session does not establish within 5 minutes, escalate to Tier 3"
}
```

---

## Production Concerns

### 1. Staleness — runbooks get updated

```
Current design: upload → chunk → embed → ChromaDB (forever)

Problem: bgp_troubleshooting_v2.pdf gets superseded by v3.
         Old chunks still exist and get retrieved.

Fix: version tagging + soft delete
  - metadata: { doc_version: "2024-Q4", superseded_by: "uuid-v3" }
  - Filter: exclude superseded chunks at query time
  - Or: delete all chunks for old runbook_id when new version uploaded
```

### 2. Multivendor confusion

Topology has Cisco IOS-XE and Juniper JunOS. "Clear BGP session" is different on each:

```
Cisco:   clear ip bgp 10.0.0.2 soft
Juniper: clear bgp neighbor 10.0.0.2
```

If the retriever returns both, the LLM might mix them up.

**Fix:** Tag chunks with vendor at ingest time, filter by device vendor at retrieval time.

```python
# InvestigationAgent knows incident.affected_device = "R1-CORE" (Cisco)
chunks = await rag.retrieve(query, filters={"vendor": "cisco"})
```

### 3. LLM hallucination on specific commands

Even with good retrieval, LLMs sometimes generate plausible-sounding but wrong commands. Dangerous in a NOC context.

**Fix (Week 4):** Command allow-listing. `command_executor.py` only runs pre-approved commands. Any command the LLM suggests that isn't in the allowlist gets flagged.

### 4. Latency

```
embed query:         ~50ms
ChromaDB search:    ~100ms
reranker:           ~200ms  (if added)
LLM inference:      2-90s   ← bottleneck
DB write:           ~50ms

Total: 3-90 seconds
```

- llama3.2 locally = 60-90s
- Claude Haiku = 2-5s
- GPT-4o = 5-15s

**For production:** Run diagnosis as Celery task (already designed this way). Frontend polls or uses WebSocket. Engineer is notified when report is ready.

---

## What the Current Architecture Gets Right

1. **Celery for ingestion** — uploading 100 PDFs doesn't block the API
2. **ChromaDB as vector store** — swappable, has metadata filtering
3. **Chunking with overlap** — context preserved across chunk boundaries
4. **JSONB for ai_report** — flexible schema, queryable, no migrations needed
5. **LLM-agnostic design** — switch from llama3.2 to Claude without changing agent code

---

## Gaps to Address for True Production

| Gap | Fix | When |
|---|---|---|
| Naive vector-only search | Add BM25 hybrid + RRF | Week 3/5 |
| No reranking | Cross-encoder on shortlist | Week 5 |
| Single query per retrieval | Multi-query expansion | Week 3 |
| No chunk versioning | Metadata + supersede logic | Week 5 |
| No vendor filtering | Tag at ingest, filter at query | Week 3 |
| LLM command hallucination | Command allow-list | Week 4 |
| No feedback loop | Engineer marks report correct/wrong → retrain | Post-capstone |
