from __future__ import annotations

import re

from .schemas import NoteLinkRead, NoteTagRead

WIKI_LINK = re.compile(r"\[\[([^\]\n]{1,200})\]\]")
TAG = re.compile(r"(?<![\w#])#([\w-]{1,64})", re.UNICODE)


def _line_at(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def parse_note_tags(content: str) -> list[NoteTagRead]:
    return [
        NoteTagRead(
            name=match.group(1),
            start_offset=match.start(),
            end_offset=match.end(),
            start_line=_line_at(content, match.start()),
            end_line=_line_at(content, match.end()),
        )
        for match in TAG.finditer(content)
    ]


def parse_note_links(content: str) -> list[NoteLinkRead]:
    links: list[NoteLinkRead] = []
    for match in WIKI_LINK.finditer(content):
        target = match.group(1).strip()
        if not target:
            continue
        links.append(
            NoteLinkRead(
                target_title=target,
                quote=match.group(0),
                start_offset=match.start(),
                end_offset=match.end(),
                start_line=_line_at(content, match.start()),
                end_line=_line_at(content, match.end()),
            )
        )
    return links
