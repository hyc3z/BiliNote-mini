"""从笔记 Markdown 中提取“省流”段落，供扩展弹窗快速展示。"""

import re


def _strip_markdown(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_`>#]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_quick_take(markdown: str, limit: int = 900) -> str:
    if not markdown:
        return ""

    lines = markdown.splitlines()
    start = None
    prefix = ""
    for index, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^#{1,4}\s*省流\s*$", stripped):
            start = index
            break
        match = re.match(r"^\*\*省流\s*[:：]?\*\*\s*(.*)$", stripped)
        if match:
            start = index
            prefix = match.group(1)
            break
        match = re.match(r"^省流\s*[:：]\s*(.*)$", stripped)
        if match:
            start = index
            prefix = match.group(1)
            break

    if start is None:
        match = re.search(r"省流\s*[:：]\s*([^\n]+(?:\n(?!##)[^\n]+)*)", markdown[:4000])
        if not match:
            return ""
        body = match.group(1)
    else:
        parts = [prefix] if prefix else []
        for line in lines[start + 1 :]:
            if re.match(r"^#{1,4}\s+", line.strip()):
                break
            parts.append(line)
        body = "\n".join(parts)

    text = _strip_markdown(body)
    return text[:limit]
