<!-- Generated: 2026-03-08 | Files scanned: 2 pyproject.toml | Token estimate: ~250 -->
# Dependencies

## Moltbook Agent

| Dependency | Version | Purpose |
|-----------|---------|---------|
| requests | >=2.28.0 | HTTP client for Moltbook API |
| pytest | >=7.0 (dev) | Test framework |
| pytest-cov | >=4.0 (dev) | Coverage reporting |
| responses | >=0.23.0 (dev) | HTTP mocking |

## IPD Benchmark

| Dependency | Version | Purpose |
|-----------|---------|---------|
| requests | >=2.28.0 | Ollama REST API |
| pytest | >=7.0 (dev) | Test framework |
| pytest-cov | >=4.0 (dev) | Coverage reporting |

## External Services

| Service | Used By | Access |
|---------|---------|--------|
| Moltbook API | moltbook-agent | HTTPS, Bearer auth, domain-locked |
| Ollama | both | localhost:11434, model qwen3.5:9b |

## Build System

Both packages use **hatchling** as build backend with `uv` for dependency management.
