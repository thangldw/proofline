from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

StudioKind = Literal[
    "audio_overview",
    "presentation",
    "video_overview",
    "mind_map",
    "report",
    "flashcards",
    "quiz",
    "infographic",
    "data_table",
]

STUDIO_KINDS: tuple[StudioKind, ...] = (
    "audio_overview",
    "presentation",
    "video_overview",
    "mind_map",
    "report",
    "flashcards",
    "quiz",
    "infographic",
    "data_table",
)


@dataclass(frozen=True)
class StudioSpan:
    text: str
    start_offset: int
    end_offset: int
    start_line: int
    end_line: int

    @property
    def quote_hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StudioDraft:
    title: str
    content: dict
    citations: list[StudioSpan]


BLOCK = re.compile(r"(?ms)(?:^|\n)(?P<block>[^\n][\s\S]*?)(?=\n\s*\n|\Z)")


def source_spans(content: str, *, limit: int = 8) -> list[StudioSpan]:
    spans: list[StudioSpan] = []
    for match in BLOCK.finditer(content):
        raw = match.group("block")
        cleaned = raw.strip()
        if not cleaned:
            continue
        leading = len(raw) - len(raw.lstrip())
        start = match.start("block") + leading
        end = start + len(cleaned)
        spans.append(
            StudioSpan(
                text=cleaned,
                start_offset=start,
                end_offset=end,
                start_line=content.count("\n", 0, start) + 1,
                end_line=content.count("\n", 0, end) + 1,
            )
        )
        if len(spans) >= limit:
            break
    return spans


def _plain(text: str, limit: int = 280) -> str:
    text = re.sub(r"(?m)^#{1,6}\s+", "", text)
    text = re.sub(r"(?m)^[-*+]\s+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else f"{text[: limit - 1].rstrip()}…"


def _label(span: StudioSpan, index: int) -> str:
    first = _plain(span.text, 90)
    return first.split(". ", 1)[0] or f"Evidence {index + 1}"


def _base_items(spans: list[StudioSpan]) -> list[dict]:
    return [
        {
            "title": _label(span, index),
            "body": _plain(span.text),
            "citation": index,
        }
        for index, span in enumerate(spans)
    ]


def build_studio_draft(kind: StudioKind, source_title: str, content: str) -> StudioDraft:
    if kind not in STUDIO_KINDS:
        raise ValueError(f"Unsupported Studio artifact kind: {kind}")
    spans = source_spans(content)
    if not spans:
        raise ValueError("The source does not contain any usable evidence blocks")
    items = _base_items(spans)
    summary = " ".join(item["body"] for item in items[:4])

    if kind == "audio_overview":
        artifact = {
            "format": "narration",
            "summary": summary,
            "items": [
                {**item, "title": f"Chapter {index + 1}: {item['title']}"}
                for index, item in enumerate(items[:5])
            ],
        }
        title = f"Audio overview · {source_title}"
    elif kind == "presentation":
        artifact = {
            "format": "slides",
            "summary": f"Evidence-backed presentation for {source_title}",
            "items": [
                {**item, "title": f"Slide {index + 1} · {item['title']}"}
                for index, item in enumerate(items[:7])
            ],
        }
        title = f"Presentation · {source_title}"
    elif kind == "video_overview":
        artifact = {
            "format": "storyboard",
            "summary": summary,
            "items": [
                {**item, "title": f"Scene {index + 1} · {item['title']}"}
                for index, item in enumerate(items[:6])
            ],
        }
        title = f"Video storyboard · {source_title}"
    elif kind == "mind_map":
        artifact = {
            "format": "branches",
            "summary": source_title,
            "items": items[:8],
        }
        title = f"Mind map · {source_title}"
    elif kind == "report":
        artifact = {"format": "report", "summary": summary, "items": items[:8]}
        title = f"Report · {source_title}"
    elif kind == "flashcards":
        artifact = {
            "format": "flashcards",
            "summary": f"{len(items[:8])} evidence-backed review cards",
            "items": [
                {
                    **item,
                    "title": f"What does the source say about “{item['title']}”?",
                    "answer": item["body"],
                }
                for item in items[:8]
            ],
        }
        title = f"Flashcards · {source_title}"
    elif kind == "quiz":
        answers = [item["body"] for item in items[:4]]
        artifact = {
            "format": "quiz",
            "summary": f"{len(answers)} source-grounded questions",
            "items": [
                {
                    **item,
                    "title": f"Which statement is supported by “{item['title']}”?",
                    "options": [
                        item["body"],
                        *[answer for answer in answers if answer != item["body"]],
                    ][:4],
                    "answer": item["body"],
                }
                for item in items[:4]
            ],
        }
        title = f"Quiz · {source_title}"
    elif kind == "infographic":
        artifact = {
            "format": "highlights",
            "summary": f"{len(items)} evidence blocks · {len(content)} characters",
            "items": items[:6],
        }
        title = f"Infographic · {source_title}"
    else:
        artifact = {
            "format": "table",
            "summary": f"{len(items)} evidence rows",
            "columns": ["Topic", "Evidence", "Source lines"],
            "items": [
                {
                    **item,
                    "cells": [item["title"], item["body"], f"L{span.start_line}–{span.end_line}"],
                }
                for item, span in zip(items[:8], spans[:8], strict=True)
            ],
        }
        title = f"Data table · {source_title}"

    used = max((item["citation"] for item in artifact["items"]), default=-1) + 1
    return StudioDraft(title=title, content=artifact, citations=spans[:used])
