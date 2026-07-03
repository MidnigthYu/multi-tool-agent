# Module 4: RAG Local Knowledge Base

## Overview

Dual-tool RAG pipeline: multi-format document parsing → semantic chunking → vector storage → retrieval. Fully integrated with the existing LangGraph ReAct agent via function-based ToolRegistry.

## Architecture (4 layers, unidirectional)

```
Route Layer (core/agent_graph.py)
    LLM decides index_documents vs knowledge_search
    ↑ calls
Tool Layer (tools/document_indexer.py + tools/knowledge_search.py)
    Async functions, Pydantic schemas, ToolRegistry auto-registration
    ↑ calls
Business Facade (storage/chroma_store.py)
    Embedding dispatch + batch indexing + similarity search
    ↑ composes (does not replace)
Storage Layer (storage/chroma_client.py — existing singleton)
    ChromaDB connection, collection CRUD, degradation → in-memory
```

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| ChromaStore vs ChromaClient | Composition, not replacement | ChromaClient is the single DB connection shared with memory modules |
| index_documents + knowledge_search | Two separate tools | LLM can decide to index OR search independently; no wasted re-indexing per query |
| Embedding client | OpenAI text-embedding-ada-002 | Already in tech stack; 1536-dim; abstracted behind `_embed()` for future swap |
| Chunking strategy | Paragraph-first + fixed-width fallback | Preserves semantic units; 200-char overlap prevents boundary loss |
| Error handling | All caught at tool layer, str return only | Never propagate exceptions to LangGraph; infrastructure errors don't trigger reflection |

## Files Changed

| File | Operation |
|------|-----------|
| `config/settings.py` | +3 RAG_ fields |
| `config/constants.py` | RAG_ cache entries |
| `config/error_codes.py` | +6 codes (E0311-E0313, all marked no-reflection) |
| `tools/document_parser.py` | **New** — parser + chunker |
| `storage/chroma_store.py` | **New** — business facade |
| `tools/document_indexer.py` | **New** — index tool |
| `tools/knowledge_search.py` | **New** — search tool |
| `tools/__init__.py` | +4 exports |
| `core/agent_graph.py` | +2 registrations in get_agent() |

## Degradation Panorama

| Scenario | Degradation | Error Code |
|----------|-------------|------------|
| Empty knowledge base | `[知识库无匹配]` | (none — normal path) |
| Embedding API unavailable | `[知识库降级]` | (none — returns zero vectors) |
| ChromaDB PersistentClient fails | Falls back to in-memory | E0311 |
| ChromaDB query timeout | `[知识库降级]` | E0313 |
| Document parse failure | Skip that file, report in summary | E0303-E0305 |
| Total file size exceeds 50MB | Batch rejected upfront | (none — size pre-check) |

## Quality Gates

- ruff format --check: PASS (70 files)
- ruff check: PASS (0 errors)
- mypy --strict: PASS (40 source files)
- pytest: 306 passed (0 failures)
- coverage: 91% (≥90% threshold)
