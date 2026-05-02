# Presentation Speaking Script
## AI-Powered Network Runbook Platform — MSAI 699 Capstone
**Target duration: 7–8 minutes**

---

## SLIDE 1 — Title (0:00–0:30)

Good [morning/afternoon]. My name is Ambika Kulkarni, and today I'm presenting my MSAI 699 capstone project: an AI-Powered Network Runbook Platform — a system that uses Retrieval-Augmented Generation, multi-agent AI orchestration, and network digital twin technology to automate incident diagnosis for Network Operations Center engineers.

---

## SLIDE 2 — The Problem (0:30–1:15)

Let me start with the problem this platform solves.

When a network outage happens — a BGP session drops, an OSPF adjacency is lost — the clock is running. Every minute of downtime has real business cost. But the knowledge engineers need to diagnose the issue is scattered across hundreds of PDF runbooks, team wikis, and tribal knowledge. A skilled engineer can spend 30 to 90 minutes just searching before they execute a single remediation command.

The problem is made worse in multi-vendor environments. A BGP session showing "Idle Admin" on a Cisco IOS-XR device requires a completely different remediation path than the same state on a Juniper JunOS device. Traditional search tools can't surface that distinction.

The core question this project asks is: can AI reduce time-to-diagnosis from hours to seconds?

---

## SLIDE 3 — Solution Overview (1:15–2:00)

The answer is yes — and here's how the system works at a high level.

When an incident comes in, the system simultaneously does three things: it searches the runbook knowledge base using semantic retrieval, it collects CLI evidence from the affected device, and it loads topology context about that device's neighbors from the digital twin.

All of that context feeds into a multi-agent pipeline — starting with an Investigation Agent that assembles the context, through an Analysis Agent that uses an LLM to reason over the evidence, and finally to a Report Agent that produces a structured root cause analysis with step-by-step remediation guidance.

The whole thing runs as a background task, returning results in under 35 seconds.

---

## SLIDE 4 — System Architecture (2:00–2:45)

The platform is a full-stack production system. The backend is built on FastAPI with fully async database operations via SQLAlchemy 2.0 and PostgreSQL. Long-running LLM jobs run in the background via Celery and Redis, so the API never blocks.

Runbook embeddings are stored in ChromaDB, a vector database optimized for semantic search. The entire system is containerized — six Docker services that can be stood up with a single command.

One important design decision: the LLM layer is completely provider-agnostic. A single environment variable switches between OpenAI, Anthropic, and local Ollama models — with zero code changes. That decision turned out to be critical, and I'll show you why in the benchmark results.

---

## SLIDE 5 — RAG Pipeline (2:45–3:20)

The RAG pipeline is what gives the system its knowledge. Runbooks are ingested as text chunks of about 1,000 characters with 200-character overlap, and each chunk is stored with rich metadata — the vendor it covers, the protocols it references, and its source document.

What makes retrieval effective here is the hybrid approach. Pure vector search finds semantically similar content, but network diagnosis often requires exact keyword precision. The phrase "Idle Admin" is semantically adjacent to other BGP idle states, but they have completely different root causes. By combining BM25 keyword scoring with vector similarity, and fusing the results using Reciprocal Rank Fusion, the system gets the best of both worlds.

---

## SLIDE 6 — Multi-Agent Orchestration (3:20–4:00)

The multi-agent pipeline is the core of the system. Rather than a hardcoded linear pipeline, I built a dynamic orchestrator that routes incidents to specialist agents based on what it learns.

After the base Analysis Agent produces an initial result, the orchestrator evaluates three things in priority order: if confidence is below 0.6, it routes to the Second Opinion Agent for a deeper investigation — essentially a self-healing loop. If the incident involves BGP, it routes to the BGP Specialist Agent, which has deep knowledge of BGP finite state machine behavior. And if the device is Juniper, it routes to the JunOS Specialist.

Every single routing decision is stored in the incident record, so there's a complete audit trail of how the system reasoned.

---

## SLIDE 7 — Digital Twin (4:00–4:30)

The network digital twin is built on NetworkX and represents the topology as a directed graph parsed from a YAML definition.

In the demo environment, we have a 5-node multi-vendor lab — three Cisco CSR1000v routers and two Juniper vMX routers, connected in a 3-tier core-distribution-access design.

When a BGP incident comes in for R1-CORE, the Investigation Agent doesn't just look at R1 — it also loads CLI evidence for R1's direct neighbors, R2 and R3, because a BGP failure is often caused by something on the far end of the session.

---

## SLIDE 8 — Benchmark Results (4:30–5:20)

Now for the results — and this is where the architecture decision to be LLM-agnostic really paid off.

I ran the same three test scenarios against two provider configurations: a local Ollama llama3.2 model running on my MacBook, and Anthropic's claude-haiku-4-5.

The difference was dramatic. With llama3.2, the mean diagnosis time was 75 to 100 minutes — because the 3-billion parameter model is too small to reason over structured CLI output, and it frequently produced malformed JSON that triggered retry loops. Root cause was consistently "undetermined." Confidence was always 0.5 — the floor value.

With Claude Haiku: 26 to 33 seconds, precise device-specific root causes, and confidence scores between 0.75 and 0.92 that actually carried signal. And the cost was $0.004 per diagnosis — meaning $5 in API credits covers over 1,200 full diagnosis runs.

---

## SLIDE 9 — Live Test Scenarios (5:20–6:00)

Three scenarios were tested against a live Cisco IOS-XR device on the DevNet Always-On Sandbox.

In the first, I applied an administrative BGP shutdown. The system correctly identified "Idle Admin" as an admin shutdown rather than a reachability problem — in 26 seconds with 0.88 confidence.

In the second, the BGP session was established but receiving zero prefixes. The system produced three candidate root causes — a route-map filter, an empty peer RIB, or a route-policy rejection — correctly diagnosing a policy issue while noting the TCP session itself was healthy.

The third scenario was the most interesting: I created an incident titled "OSPF down" when OSPF was actually healthy. The system not only diagnosed OSPF as operational — it identified the incident as a false alarm and recommended reviewing the monitoring alert threshold. That's genuine reasoning, not pattern matching.

---

## SLIDE 10 — Challenges (6:00–6:35)

The most significant technical challenges fell into three categories.

LLM non-determinism: early testing showed models would wrap JSON in Markdown fences or produce partial output. The fix was a three-layer defense — strip fences, catch parse errors, and fall back to a structured result with confidence 0.4, which automatically triggers a re-investigation.

A dependency compatibility break: bcrypt 5.0 introduced API changes that passlib 1.7.4 doesn't handle. 17 tests were failing. The fix was to bypass passlib entirely and call bcrypt directly.

And the reranker output contract: when flashrank isn't installed, the fallback path wasn't attaching the rerank_score key. A three-line fix made the output consistent regardless of whether the optional library is installed.

---

## SLIDE 11 — Test Results (6:35–6:55)

After addressing those issues, the test suite went from 29 passing and 20 failing to 49 out of 49 passing.

The test architecture doesn't require any external services — it uses an in-memory SQLite database, a stub LLM client that returns deterministic canned responses, and monkeypatched ChromaDB calls. This means the full test suite can run anywhere in under 10 seconds.

---

## SLIDE 12 — Future Work (6:55–7:20)

Three near-term enhancements stand out.

Streaming diagnosis output via server-sent events — so engineers can see the investigation phase start populating immediately rather than waiting 30 seconds for a complete result.

A feedback loop where engineer acceptance or rejection of AI recommendations trains a preference model over time.

And multi-incident correlation — grouping co-occurring alerts by topology proximity and time window to diagnose a fiber cut as one causal event rather than dozens of noisy alerts.

---

## SLIDE 13 — Conclusion (7:20–8:00)

To close: the most important finding of this project is that LLM selection is a first-order architecture decision. The gap between a small local model and a frontier cloud model on structured protocol reasoning isn't marginal — it's the difference between a system that works and one that doesn't.

The platform delivers on its design goals: LLM-agnostic, vendor-agnostic, async-first, auditable, and fully tested. With diagnosis times of 26 to 33 seconds versus the 30 to 90 minutes of manual search, the platform provides a meaningful acceleration for NOC engineers during the moments when speed matters most.

Thank you. I'm happy to take questions.

---

## Tips for Recording

- **Pace:** ~110 words/minute. The script runs ~950 words = ~8.5 minutes. Trim slide 4 or 7 if you need to hit 7 minutes.
- **Navigation:** Use arrow keys (← →) to advance slides in PRESENTATION.html.
- **Screen recording:** Open PRESENTATION.html in Chrome full-screen (F11), record with QuickTime (Mac) or OBS.
- **Slide timing guide:**
  - Slides 1–3: ~2 min (intro + problem + solution)
  - Slides 4–7: ~2.5 min (architecture deep dive)
  - Slides 8–9: ~1.5 min (results — spend time here)
  - Slides 10–13: ~2 min (challenges + tests + conclusion)
