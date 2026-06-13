"""Input adapters: raw files (txt / json) -> canonical Material. The worker never sees
a path or a file handle — only normalized SourceDoc objects."""
from __future__ import annotations

import json
import os
import re
import uuid

from .types import Material, SourceDoc, SourceType


def _norm(text: str) -> str:
    """Collapse runs of spaces/tabs but preserve line and sentence structure."""
    text = text.replace("\r\n", "\n")
    return re.sub(r"[ \t]+", " ", text).strip()


def _read_text(path: str) -> str:
    """Read .txt directly, or extract text from a .pdf (e.g. a Berkshire letter)."""
    if path.lower().endswith(".pdf"):
        from pypdf import PdfReader  # lazy: only needed for PDF inputs
        reader = PdfReader(path)
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    with open(path) as f:
        return f.read()


def load_earnings(path: str, source_id: str = "earnings") -> SourceDoc:
    text = _norm(_read_text(path))
    return SourceDoc(source_id, SourceType.EARNINGS, os.path.basename(path), text)


def load_podcast(path: str, source_id: str = "podcast") -> SourceDoc:
    text = _norm(_read_text(path))
    return SourceDoc(source_id, SourceType.PODCAST, os.path.basename(path), text)


def load_x_posts(path: str, source_id: str = "x") -> SourceDoc:
    """X export is a json list of {handle, text, ...}; flatten into one delimited doc."""
    with open(path) as f:
        posts = json.load(f)
    lines = [f"@{p.get('handle', 'user')}: {p['text']}" for p in posts]
    return SourceDoc(
        source_id, SourceType.X_POSTS, os.path.basename(path),
        _norm("\n".join(lines)), metadata={"count": len(posts)},
    )


_LOADERS = {
    SourceType.EARNINGS: load_earnings,
    SourceType.PODCAST: load_podcast,
    SourceType.X_POSTS: load_x_posts,
}


def build_material(ticker: str, sources: list[tuple[SourceType, str]],
                   run_id: str | None = None) -> Material:
    run_id = run_id or uuid.uuid4().hex[:12]
    docs = [_LOADERS[stype](path) for stype, path in sources]
    return Material(run_id=run_id, ticker=ticker, docs=docs)
