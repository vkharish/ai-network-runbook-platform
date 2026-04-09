# LLM Performance Benchmark: Ollama llama3.2 vs Anthropic claude-haiku

> Measured on: AI-Powered Network Runbook Platform — MSAI 699 Capstone
> Test device: Cisco IOS-XR xrd-1 (DevNet Always-On Sandbox)
> Date: March 2026

---

## Summary

| Metric | Ollama llama3.2 (3B) | Anthropic claude-haiku-4-5 | Improvement |
|--------|---------------------|---------------------------|-------------|
| **Diagnosis time** | 75–100 min | 26–33 sec | **~180× faster** |
| **Root cause accuracy** | "Root cause undetermined." | Precise, device-specific | Qualitative leap |
| **Confidence score** | Always 0.5 | 0.75–0.92 | Meaningful signal |
| **CLI interpretation** | Failed | Correct | ✅ |
| **BGP state analysis** | Failed | Correct | ✅ |
| **Runbook citation** | Generic | Source-specific | ✅ |
| **Cost per diagnosis** | ~$0 (local) | ~$0.004 | Negligible |

---

## Test Scenario 1: BGP Admin Shutdown

**Setup:** `neighbor 2.2.2.2 shutdown` committed on xrd-1. CLI output shows `Idle (Admin)` state.

### Ollama llama3.2 result
```
root_cause: "Root cause undetermined."
confidence: 0.5
time: ~90 minutes (5 LLM calls × ~18 min each)
```

### Anthropic claude-haiku result
```
root_cause: "BGP neighbor 2.2.2.2 is administratively shut down,
             preventing session establishment."
confidence: 0.88
time: 26.2 seconds
hypothesis: "The BGP session to peer 2.2.2.2 (AS 1) is stuck in
             'Idle (Admin)' state, indicating the neighbor has been
             manually disabled via administrative command..."
```

**Analysis:** Haiku correctly identified `Idle (Admin)` = admin shutdown and distinguished it from reachability or authentication failures. llama3.2 could not parse the structured IOS-XR CLI output.

---

## Test Scenario 2: BGP 0 Prefixes Received

**Setup:** BGP session established but peer advertising 0 prefixes. `St/PfxRcd = 0`.

### Ollama llama3.2 result
```
root_cause: "Root cause undetermined."
confidence: 0.5
time: ~95 minutes
```

### Anthropic claude-haiku result
```
root_cause: "BGP session to peer 2.2.2.2 is established but receiving
             0 prefixes, indicating a route policy filtering issue or
             the peer has no routes to advertise."
confidence: 0.82
time: 32.7 seconds
hypothesis: "The BGP neighbor 2.2.2.2 (AS 1) shows Established state
             with 5d00h uptime and 7241 messages exchanged in both
             directions, but the 'St/PfxRcd' column shows 0 prefixes
             received. This indicates either: (1) an inbound route-map
             or prefix-list is filtering all received prefixes, (2) the
             peer has no routes to advertise, or (3) a route policy is
             rejecting all advertisements..."
```

**Analysis:** Haiku correctly identified the session as healthy at TCP/keepalive level but diagnosed the routing/policy issue. Provided 3 specific candidate root causes.

---

## Test Scenario 3: OSPF False Alarm

**Setup:** Incident titled "OSPF down on xrd-1" — but OSPF was actually healthy.

### Anthropic claude-haiku result
```
root_cause: "OSPF process is running and has established one full
             adjacency with neighbor 3.3.3.3, but the incident title
             'ospf down on xrd-1' is misleading — OSPF is operationally
             UP with 4 routes in the RIB."
confidence: 0.91
time: 33.5 seconds
verdict: "False alarm — recommend closing ticket and reviewing
          monitoring alert thresholds."
```

**Analysis:** Haiku not only diagnosed the protocol state correctly but identified the incident itself as a false alarm — demonstrating genuine reasoning capability beyond pattern matching.

---

## Pipeline Timing Breakdown (Anthropic)

| Stage | Time |
|-------|------|
| Device SSH + CLI collection (6 commands) | ~7 sec |
| RAG embedding + hybrid search + rerank | ~1 sec |
| AnalysisAgent LLM call | ~8 sec |
| BGP/SecondOpinion specialist (if triggered) | ~8 sec |
| ReportAgent LLM call | ~8 sec |
| DB persist | <1 sec |
| **Total** | **~26–33 sec** |

---

## Pipeline Timing Breakdown (Ollama llama3.2 on MacBook Pro M1)

| Stage | Time |
|-------|------|
| Device SSH + CLI collection | ~7 sec |
| RAG embedding + hybrid search + rerank | ~1 sec |
| AnalysisAgent LLM call (×3 iterations) | ~54 min |
| SecondOpinion (×2) | ~36 min |
| BGPSpecialist | ~18 min |
| ReportAgent | ~18 min |
| **Total** | **~126 min** |

---

## Why llama3.2 Fails on This Task

1. **Model size**: 3B parameters is insufficient for structured CLI reasoning
2. **Context window**: IOS-XR CLI output (show interfaces, show logging) can be 10,000+ tokens — llama3.2 struggles with long context
3. **Domain knowledge**: Network protocol state machines (BGP FSM, OSPF adjacency states) require deep domain-specific fine-tuning
4. **JSON reliability**: llama3.2 frequently outputs malformed JSON, triggering the graceful fallback path

## Why claude-haiku Succeeds

1. **200k context window**: Full CLI output, runbook chunks, and topology context fit comfortably
2. **Strong instruction following**: Reliably returns structured JSON with all required fields
3. **Domain knowledge**: Pre-trained on extensive networking documentation
4. **Reasoning**: Can distinguish `Idle (Admin)` from `Idle` — a subtle but critical difference

---

## Cost Analysis (Anthropic claude-haiku-4-5)

| Item | Tokens | Cost |
|------|--------|------|
| Input per diagnosis | ~3,000 | $0.0024 |
| Output per diagnosis | ~500 | $0.002 |
| **Total per diagnosis** | ~3,500 | **~$0.004** |
| 1,000 diagnoses | 3.5M | **~$4.00** |

$5 in Anthropic credits ≈ 1,250+ full diagnosis runs.

---

## Conclusion

For production NOC use, a capable cloud LLM (Anthropic claude-haiku or equivalent) is not optional — it is the difference between a working platform and an unusable one. The architecture, RAG pipeline, agent routing, and CLI collection all function correctly with both providers; only the LLM intelligence layer differs.

The platform is designed LLM-agnostic (`LLM_PROVIDER` env var) so operators can switch between Anthropic, OpenAI, or Ollama without code changes.
