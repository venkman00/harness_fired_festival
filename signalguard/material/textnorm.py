"""Shared text normalization.

Two levels:
  - normalize_text(): light, human-readable cleanup used as the canonical form the worker
    reads (fixes unicode punctuation, joins line-break hyphenation, tidies whitespace while
    keeping paragraph structure).
  - ground_key(): aggressive, used ONLY by the grounding checkpoint — reduces text to its
    lowercase alphanumeric stream so that whitespace, punctuation, hyphenation, and PDF
    extraction artifacts cannot cause a false "ungrounded" reject. It still requires the
    source's words and numbers in order, so a paraphrase (different words) will not match.
"""
from __future__ import annotations

import re

# unicode punctuation / ligatures that PDF extraction commonly emits
_PUNCT_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "–": "-", "—": "-", "−": "-",
    "…": "...", " ": " ", " ": " ", " ": " ",
    "ﬁ": "fi", "ﬂ": "fl",
}


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n")
    for k, v in _PUNCT_MAP.items():
        text = text.replace(k, v)
    # join words split across a line break by a hyphen: "under-\nwriting" -> "underwriting"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def ground_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())
