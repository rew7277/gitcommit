from config import settings

SYSTEM_PROMPT = """You are a senior API architect and security engineer.
Analyze the provided git diff and respond ONLY in the exact Markdown format below.
Be precise. Do not add any text outside of these sections.

## 📋 Summary
(2-3 sentences max describing what changed)

## 🔌 API Changes
(List each change as: `METHOD /path` — description. Write "None detected" if no API changes)

## ⚠️ Breaking Changes
(List anything that would break existing consumers. Write "None" if clean)

## 🔒 Security Concerns
(Auth issues, exposed secrets, injection risks, missing validation. Write "None" if clean)

## 🐛 Bugs & Issues
(Logic errors, missing error handling, edge cases. Write "None" if clean)

## 💡 Suggestions
(Performance, naming, best practices — keep to 3 most important)

## 📊 Risk Score
(Write ONLY one of: LOW / MEDIUM / HIGH — based on breaking changes + security issues)"""


def _chunk_diff(diff: str, max_chars: int = 12000) -> list[str]:
    """Split large diffs into per-file chunks to stay within context limits."""
    files = diff.split("\ndiff --git ")
    chunks, current = [], ""
    for f in files:
        block = f if f.startswith("diff --git ") else "diff --git " + f
        if len(current) + len(block) > max_chars:
            if current:
                chunks.append(current)
            current = block
        else:
            current += "\n" + block
    if current:
        chunks.append(current)
    return chunks or [diff]


async def _call_anthropic(diff_chunk: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Git Diff:\n```\n{diff_chunk}\n```"}],
    )
    return msg.content[0].text


async def _call_openai(diff_chunk: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model="gpt-4.1",
        max_tokens=2000,
        temperature=0.1,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Git Diff:\n```\n{diff_chunk}\n```"},
        ],
    )
    return resp.choices[0].message.content


async def generate_review(diff: str) -> dict:
    """
    Returns:
        raw_review   str   Full Markdown review
        summary      str   Extracted summary
        api_changes  str   Extracted API changes section
        breaking     bool  True if breaking changes detected
        security     bool  True if security issues detected
        risk         str   LOW | MEDIUM | HIGH
    """
    if not diff.strip():
        return {
            "raw_review": "No diff content to review.",
            "summary": "Empty diff.",
            "api_changes": "None detected",
            "breaking": False,
            "security": False,
            "risk": "LOW",
        }

    chunks = _chunk_diff(diff)
    parts = []
    for chunk in chunks:
        if settings.AI_PROVIDER == "openai":
            result = await _call_openai(chunk)
        else:
            result = await _call_anthropic(chunk)
        parts.append(result)

    raw = "\n\n---\n\n".join(parts)

    # Parse key fields from the structured response
    def extract_section(text: str, heading: str) -> str:
        lines = text.split("\n")
        capture, out = False, []
        for line in lines:
            if line.startswith(f"## {heading}"):
                capture = True
                continue
            if capture and line.startswith("## "):
                break
            if capture:
                out.append(line)
        return "\n".join(out).strip() or "None"

    summary      = extract_section(raw, "📋 Summary")
    api_changes  = extract_section(raw, "🔌 API Changes")
    breaking_txt = extract_section(raw, "⚠️ Breaking Changes").lower()
    security_txt = extract_section(raw, "🔒 Security Concerns").lower()
    risk_txt     = extract_section(raw, "📊 Risk Score").strip().upper()

    breaking = "none" not in breaking_txt and len(breaking_txt) > 4
    security = "none" not in security_txt and len(security_txt) > 4
    risk     = risk_txt if risk_txt in ("LOW", "MEDIUM", "HIGH") else "MEDIUM"

    return {
        "raw_review": raw,
        "summary": summary,
        "api_changes": api_changes,
        "breaking": breaking,
        "security": security,
        "risk": risk,
    }


def format_pr_comment(review: dict, repo_name: str, pr_number: int) -> str:
    risk_emoji = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}.get(review["risk"], "⚪")
    flags = []
    if review["breaking"]:
        flags.append("⚠️ **Breaking Changes Detected**")
    if review["security"]:
        flags.append("🔒 **Security Issues Found**")
    flag_block = "\n".join(flags) + "\n\n" if flags else ""

    return f"""## 🤖 AI Code Review — `{repo_name}` PR #{pr_number}

{flag_block}{review["raw_review"]}

---
*Risk: {risk_emoji} {review["risk"]} · Powered by [AI API Reviewer](https://github.com)*"""
