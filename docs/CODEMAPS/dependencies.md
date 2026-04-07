<!-- Generated: 2026-04-08 | Files scanned: 1 pyproject.toml | Token estimate: ~250 -->
# Dependencies

## Runtime

| Dependency | Version | Purpose |
|-----------|---------|---------|
| requests | >=2.33.0 | HTTP client for Moltbook API |
| numpy | >=1.24.0 | Matrix operations for meditation adapter (POMDP) |

## Dev

| Dependency | Version | Purpose |
|-----------|---------|---------|
| pytest | >=7.0 | Test framework |
| pytest-cov | >=4.0 | Coverage reporting |
| responses | >=0.23.0 | HTTP mocking |

## External Services

| Service | Used By | Access |
|---------|---------|--------|
| Moltbook API | adapters/moltbook | HTTPS, Bearer auth, domain-locked |
| Ollama | core/llm | localhost:11434, model qwen3.5:9b |

## Build System

Uses **hatchling** as build backend with `uv` for dependency management.
Python >=3.9 required. Version: 1.3.0.
