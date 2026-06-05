"""Essay Extractor: Paul Graham's old-style essay HTML -> cleaned {title, text}.

A deep, pure module. All of the messy cleanup (font tags, table layout, <br>
paragraph breaks, nav chrome, a title repeated at the top of the body) lives
behind one function so the crawler's HTTP/file/loop logic stays a thin shell.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class Essay:
    title: str
    text: str
    url: str | None = None


def extract_essay(html: str, url: str | None = None) -> Essay:
    """Extract a cleaned title and body text from a single essay's HTML."""
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    if soup.title and soup.title.get_text(strip=True):
        title = soup.title.get_text(strip=True)

    # Drop non-content nodes entirely.
    for tag in soup(["script", "style"]):
        tag.decompose()

    # Turn line breaks into newlines so paragraph structure survives get_text.
    for br in soup.find_all("br"):
        br.replace_with("\n")

    # Paul Graham's body text sits in the largest <font> block; nav/footers are
    # in their own smaller font blocks. Fall back to <body> if there are none.
    block = None
    fonts = soup.find_all("font")
    if fonts:
        block = max(fonts, key=lambda f: len(f.get_text()))
    if block is None or len(block.get_text(strip=True)) < 40:
        block = soup.body or soup

    text = _normalize(block.get_text("\n"), title)
    return Essay(title=title, text=text, url=url)


def _normalize(raw: str, title: str) -> str:
    # Strip each line; keep at most one blank line between paragraphs.
    lines = [ln.strip() for ln in raw.split("\n")]
    out: list[str] = []
    pending_blank = False
    for line in lines:
        if line:
            if pending_blank and out:
                out.append("")
            out.append(line)
            pending_blank = False
        elif out:
            pending_blank = True

    text = "\n".join(out).strip()

    # Drop the title if PG repeated it as the first line of the body.
    if title and text.startswith(title):
        text = text[len(title):].lstrip("\n ").strip()

    # Collapse any run of 3+ newlines down to a paragraph break.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text
