"""A/B test: compare two distill prompts on the same episode logs."""

import json
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from contemplative_agent.core.llm import generate
from contemplative_agent.core.memory import EpisodeLog
from contemplative_agent.core.distill import _summarize_record

PROMPT_A = """\
You are a social media agent on Moltbook. The following are YOUR OWN activity logs from today. Reflect on your actions and extract behavioral patterns you want to remember.

## What to Extract

Look for these categories in the episode logs:

1. **Engagement tactics** — what kind of comments/replies got meaningful responses vs ignored
2. **Topic selection** — which topics led to deep threads vs dead ends
3. **Social dynamics** — following/unfollowing decisions that improved or hurt feed quality
4. **Failure patterns** — repeated mistakes, wasted actions, rate limit hits

## How to Write a Pattern

Each pattern must include:
- **What happened**: the specific situation or behavior observed
- **Why it matters**: the outcome (positive or negative)
- **What to do next time**: the concrete action to take or avoid

Bad example: "Engage more deeply with other agents"
Good example: "Replying with a specific quote from the other agent's post gets more follow-up replies than generic agreement. When commenting, always reference a concrete point from the post rather than restating the overall theme."

Bad example: "Be more selective about topics"
Good example: "Posts about memory architecture consistently get deeper threads than posts about general AI ethics. This is likely because memory architecture is a concrete technical topic where agents can share specific implementation details, while AI ethics tends to produce abstract agreement without new information."

## Output

Reply with bullet points, one per line, starting with "- ".
Write as much as needed to fully capture the pattern — do not truncate or abbreviate.

Your activity logs:
{episodes}"""

PROMPT_B = """\
You are a social media agent on Moltbook. Extract behavioral patterns from YOUR OWN activity logs below. For each pattern, describe:
1. What happened (specific situation)
2. Why it mattered (outcome)
3. What to do next time (concrete action)

Focus on: engagement tactics, topic selection, social dynamics, failure patterns.

**Example pattern:**
"Replies that quote specific points from other posts get more follow-up replies than generic agreement. Always reference a concrete detail rather than restating the overall theme."

Output: bullet points, one per line, starting with "- ". Be complete—don't abbreviate.

Activity logs:
{episodes}"""


def load_episodes(log_path: Path, limit: int = 50) -> str:
    """Load and summarize episode records."""
    records = EpisodeLog.read_file(log_path)[:limit]
    lines = []
    for r in records:
        record_type = r.get("type", "unknown")
        data = r.get("data", {})
        ts = r.get("ts", "")
        summary = _summarize_record(record_type, data)
        if summary:
            lines.append(f"[{ts[:16]}] {record_type}: {summary}")
    return "\n".join(lines)


def main():
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    log_path = Path.home() / ".config/moltbook/logs/2026-03-18.jsonl"
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        sys.exit(1)

    episodes = load_episodes(log_path)
    print(f"Loaded {len(episodes.splitlines())} episode lines")
    print(f"Runs: {runs}\n")

    stats = {"A": [], "B": []}

    for run in range(1, runs + 1):
        print(f"--- Run {run}/{runs} ---")
        for label, key, prompt_template in [
            ("A (current)", "A", PROMPT_A),
            ("B (haiku)", "B", PROMPT_B),
        ]:
            prompt = prompt_template.format(episodes=episodes)
            result = generate(prompt, max_length=4000)
            if result is None:
                print(f"  {label}: LLM returned None")
                continue
            patterns = [l.strip() for l in result.splitlines() if l.strip().startswith("- ")]
            count = len(patterns)
            length = len(result)
            stats[key].append({"count": count, "length": length})
            print(f"  {label}: {count} patterns, {length} chars")
        print()

    # Summary
    print(f"{'='*60}")
    print("  Summary")
    print(f"{'='*60}")
    for key in ["A", "B"]:
        counts = [s["count"] for s in stats[key]]
        lengths = [s["length"] for s in stats[key]]
        if counts:
            print(f"  Prompt {key}:")
            print(f"    Patterns: {counts} avg={sum(counts)/len(counts):.1f}")
            print(f"    Output chars: avg={sum(lengths)/len(lengths):.0f}")


if __name__ == "__main__":
    main()
