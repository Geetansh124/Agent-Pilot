# Ruflo → Agent-Pilot Integration Plan

> Mapping Ruflo's 35+ plugins and 98+ agents to Agent-Pilot's existing subsystems.
> **Goal**: Identify what we already have, what's missing, and what to integrate.

---

## Gap Analysis: What We Have vs What Ruflo Adds

| Category | Agent-Pilot (Current) | Ruflo Enhancement | Priority |
|---|---|---|---|
| **Swarm Orchestration** | Single supervisor → 4 agents | Multi-player swarms, mesh/hierarchical topologies, auto-coordination | 🔴 High |
| **Self-Learning** | Static agent logic | Agents learn from past successes, pattern recognition, self-optimization | 🔴 High |
| **Federation** | Single-machine only | Cross-machine agent communication, secure federated messaging | 🟡 Medium |
| **Knowledge Graph** | ✅ SQLite graph with BFS traversal | PageRank, delta updates, sublinear graph reasoning | 🟡 Medium |
| **RAG / Memory** | ✅ FAISS + BM25 hybrid, SQLite memory | GPU-accelerated vector search, Graph RAG, session persistence (RVF) | 🔴 High |
| **Security** | ✅ Guardrails, JWT auth, credential redaction | PII detection, advanced prompt injection blocking, vulnerability/CVE scanning | 🟡 Medium |
| **Testing** | None | Auto test generation, browser testing (Playwright), risk-scored diffs | 🔴 High |
| **Cost Tracking** | ✅ Per-thread token budgets | Budget alerts, cross-model cost comparison, spending forecasts | 🟢 Low |
| **Observability** | ✅ SQLite audit ledger | Structured tracing, distributed metrics, OpenTelemetry-compatible | 🟡 Medium |
| **Workflows** | ✅ Multi-step pipeline runner | Reusable workflow templates, background loop workers, autopilot mode | 🟡 Medium |
| **Goal Planning** | ✅ ReAct planner with reflection | Hierarchical goal decomposition, progress tracking, automated replanning | 🟡 Medium |
| **Documentation** | Manual | Auto-generated, auto-maintained documentation from code | 🟢 Low |
| **Architecture** | Ad-hoc | ADR (Architecture Decision Records), DDD scaffolding, SPARC methodology | 🟢 Low |
| **Local LLMs** | NVIDIA NIM only | Ollama, smart model routing, multi-provider fallback chains | 🟡 Medium |
| **Agent Sandbox** | Python `exec()` only | WASM sandboxes, managed cloud agents | 🟡 Medium |

---

## Phase 1: High-Priority Integrations (Immediate Impact)

### 1.1 Swarm Orchestration (`ruflo-swarm`)
**What it adds**: Instead of a single supervisor routing to 4 agents, enable true multi-agent swarms where agents self-organize, run in parallel, and coordinate dynamically.

**Integration points**:
- Extend `src/agents/shared_state.py` → Add swarm topology support (mesh, hierarchical, pipeline, fan-out)
- Extend `src/agents/supervisor.py` → Support spawning agent teams instead of single delegation
- New file: `src/agents/swarm_coordinator.py` — Manages agent pools, work distribution, result aggregation

**New capabilities**:
- Parallel agent execution (researcher + coder working simultaneously)
- Dynamic agent scaling based on task complexity
- Agent specialization discovery (which agent performs best on which tasks)

### 1.2 Self-Learning Intelligence (`ruflo-intelligence`)
**What it adds**: Agents track which tool sequences succeed and which fail, then automatically prefer successful patterns.

**Integration points**:
- Extend `src/observability/audit.py` → Tag outcomes as success/failure with performance metrics
- New file: `src/intelligence/learning_engine.py` — Pattern extraction from audit logs
- Extend `src/agents/supervisor.py` → Use learned patterns to improve routing decisions

**New capabilities**:
- Automatic tool-chain optimization
- Task completion time prediction
- Agent performance scoring and self-improvement

### 1.3 Enhanced RAG Memory (`ruflo-rag-memory` + `ruflo-agentdb`)
**What it adds**: Graph-aware retrieval, diversity ranking, semantic deduplication.

**Integration points**:
- Extend `src/rag/hybrid_retriever.py` → Add graph-hop retrieval from knowledge graph
- Extend `src/memory/memory_store.py` → Add vector-indexed memory search (not just keyword)
- New file: `src/rag/graph_rag.py` — Combine knowledge graph traversal with vector retrieval

**New capabilities**:
- Cross-document relationship discovery
- Memory deduplication and consolidation
- Semantic memory retrieval instead of keyword-only

### 1.4 Auto Test Generation (`ruflo-testgen`)
**What it adds**: Analyze code to find untested paths and automatically generate test cases.

**Integration points**:
- New file: `src/tools/test_generator.py` — Analyzes Python code AST and generates pytest tests
- Extend `src/agents/coding_agent.py` → Auto-run tests after code generation
- New agent: `src/agents/testing_agent.py` — Dedicated agent for test planning and execution

**New capabilities**:
- Coverage gap detection
- Regression test generation after code changes
- Test quality scoring

---

## Phase 2: Medium-Priority Integrations (Depth & Resilience)

### 2.1 Federation (`ruflo-federation`)
**What it adds**: Agents on different machines communicate securely over encrypted channels.

**Integration points**:
- New file: `src/federation/federation_server.py` — WebSocket-based inter-node messaging
- Extend `src/agents/shared_state.py` → Route messages to remote agent pools
- New file: `src/federation/auth.py` — Mutual TLS / token-based node authentication

### 2.2 Graph Intelligence (`ruflo-graph-intelligence`)
**What it adds**: PageRank on knowledge graph, delta updates, complexity-aware query execution.

**Integration points**:
- Extend `src/graph/knowledge_graph.py` → Add PageRank scoring for node importance
- Add incremental graph updates (delta indexing instead of full recomputation)
- Complexity estimation before graph traversal to prevent expensive queries

### 2.3 Advanced Security (`ruflo-security-audit` + `ruflo-aidefence`)
**What it adds**: CVE scanning, PII detection beyond regex, adversarial prompt detection.

**Integration points**:
- Extend `src/security/guardrails.py` → ML-based prompt injection detection
- New file: `src/security/pii_detector.py` — Named entity recognition for PII
- New file: `src/security/vulnerability_scanner.py` — Dependency and code vulnerability checks

### 2.4 Autopilot Mode (`ruflo-autopilot`)
**What it adds**: Agents run autonomously in a loop, picking up tasks, executing, and reporting.

**Integration points**:
- Extend `src/automation/scheduler.py` → Support autonomous task discovery
- New file: `src/agent/autopilot.py` — Continuous loop: observe → plan → act → reflect
- Extend `src/agent/planner.py` → Auto-generate plans from high-level goals

### 2.5 Multi-Provider LLM Routing (`ruflo-ruvllm`)
**What it adds**: Route to Ollama, OpenAI, Anthropic, or NVIDIA based on task type and cost.

**Integration points**:
- New file: `src/llm/router.py` — Smart model selection based on task complexity
- Extend `src/observability/cost.py` → Per-model cost comparison and automatic fallback
- Support local model inference via Ollama for privacy-sensitive tasks

### 2.6 Structured Observability (`ruflo-observability`)
**What it adds**: OpenTelemetry-compatible tracing, distributed spans across agent calls.

**Integration points**:
- Extend `src/observability/audit.py` → Add trace IDs and span hierarchy
- New file: `src/observability/tracing.py` — OpenTelemetry-compatible trace export
- Dashboard endpoint for real-time agent pipeline visualization

---

## Phase 3: Low-Priority Integrations (Polish & Methodology)

### 3.1 Browser Testing (`ruflo-browser`)
- Playwright integration for end-to-end testing of generated web apps

### 3.2 Documentation Generation (`ruflo-docs`)
- Auto-generate API docs, architecture diagrams, and changelogs from code

### 3.3 Architecture Decision Records (`ruflo-adr`)
- Track every design decision with rationale, status, and consequences

### 3.4 SPARC Methodology (`ruflo-sparc`)
- 5-phase development: Specify → Pseudocode → Architect → Refine → Complete

### 3.5 Domain-Driven Design (`ruflo-ddd`)
- Scaffold bounded contexts, aggregates, and domain events

### 3.6 Migration Management (`ruflo-migrations`)
- Safe database schema change tracking and rollback

---

## New Agent Roster (After Integration)

| # | Agent | Role | Source |
|---|---|---|---|
| 1 | Supervisor | Intent classification + delegation | ✅ Existing |
| 2 | Researcher | Document RAG + web search | ✅ Existing |
| 3 | Coder | Code generation + execution | ✅ Existing |
| 4 | Data Analyst | Tabular analysis + SQL | ✅ Existing |
| 5 | **Testing Agent** | Auto test generation + execution | 🆕 Phase 1 |
| 6 | **Learning Agent** | Pattern extraction + optimization | 🆕 Phase 1 |
| 7 | **Swarm Coordinator** | Multi-agent orchestration | 🆕 Phase 1 |
| 8 | **Security Auditor** | CVE scanning + PII detection | 🆕 Phase 2 |
| 9 | **Autopilot Agent** | Autonomous task loop | 🆕 Phase 2 |
| 10 | **Documentation Agent** | Auto-doc generation | 🆕 Phase 3 |
| 11 | **Architecture Agent** | ADR + DDD scaffolding | 🆕 Phase 3 |

---

## Implementation Order

```
Week 1-2: Phase 1.1 (Swarm) + Phase 1.2 (Self-Learning)
Week 3-4: Phase 1.3 (Enhanced RAG) + Phase 1.4 (Test Generation)
Week 5-6: Phase 2.1 (Federation) + Phase 2.2 (Graph Intelligence)
Week 7-8: Phase 2.3 (Security) + Phase 2.4 (Autopilot) + Phase 2.5 (LLM Router)
Week 9+:  Phase 3 (Polish — docs, ADR, SPARC, browser testing)
```

---

## Files to Create

```
src/agents/swarm_coordinator.py      # Phase 1.1
src/agents/testing_agent.py          # Phase 1.4
src/intelligence/learning_engine.py  # Phase 1.2
src/rag/graph_rag.py                 # Phase 1.3
src/tools/test_generator.py          # Phase 1.4
src/federation/federation_server.py  # Phase 2.1
src/federation/auth.py               # Phase 2.1
src/security/pii_detector.py         # Phase 2.3
src/security/vulnerability_scanner.py # Phase 2.3
src/agent/autopilot.py               # Phase 2.4
src/llm/router.py                    # Phase 2.5
src/observability/tracing.py         # Phase 2.6
```

---

## References

- [Ruflo GitHub](https://github.com/ruvnet/ruflo)
- [Ruflo Explained (14-chapter guide)](https://github.com/ruvnet/ruflo/blob/main/docs/ruflo-explained.md)
- [RuVector Agentic DB](https://github.com/ruvnet/ruvector)
