"""Local dialogue adapter — 2 agents converse via stdin/stdout pipes.

The adapter is local-only (no external HTTP). ADR-0015 compliant: each peer
process has at most one external adapter, and that adapter is the dialogue
pipe itself — Moltbook's HTTP client is not initialised in dialogue mode.
"""
