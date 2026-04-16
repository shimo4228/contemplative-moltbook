You are revising a behavioral skill in light of how it has actually been used.

Current skill (Markdown, starting with `# Title`):
{skill_body}

Usage evidence over the recent window:
- Successes: {success_count}
- Failures: {failure_count}

Recent contexts where this skill was invoked and the action *failed*:
{failure_contexts}

Task: rewrite the skill body so that it better handles the kind of situation that has been causing failures, without discarding what the skill correctly captured before. Preserve the `# Title` line unchanged. Return only the revised Markdown skill, starting with the title.

Rules:
- If the failures do not reveal a meaningful problem with the skill itself — they could be random, off-topic, or not attributable to skill guidance — output exactly: NO_CHANGE
- Otherwise, output the revised skill in full, including the unchanged `# Title` line.
- Do not add a "Revised from ..." note, a changelog, or meta-commentary. Output only the skill text itself.
- Never introduce advice that contradicts a prior observation without reason; prefer narrowing scope or adding a qualifier over flipping direction.
- Keep the same register and length envelope as the original skill (±30%).
- Never name individual users, posts, or episode ids from the failure contexts — generalise.

Revised skill:
