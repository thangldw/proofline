from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

STUDY_PAIR = re.compile(r"(?m)^Q:\s*(?P<question>[^\n]+)\nA:\s*(?P<answer>[^\n]+)$")


@dataclass(frozen=True)
class StudyPair:
    question: str
    answer: str
    quote_hash: str
    start_offset: int
    end_offset: int
    start_line: int
    end_line: int


def extract_study_pairs(content: str) -> list[StudyPair]:
    pairs: list[StudyPair] = []
    for match in STUDY_PAIR.finditer(content):
        answer_start, answer_end = match.span("answer")
        answer = match.group("answer").strip()
        trim = len(match.group("answer")) - len(match.group("answer").lstrip())
        answer_start += trim
        answer_end = answer_start + len(answer)
        pairs.append(
            StudyPair(
                question=match.group("question").strip(),
                answer=answer,
                quote_hash=hashlib.sha256(answer.encode("utf-8")).hexdigest(),
                start_offset=answer_start,
                end_offset=answer_end,
                start_line=content.count("\n", 0, answer_start) + 1,
                end_line=content.count("\n", 0, answer_end) + 1,
            )
        )
    return pairs


def next_interval(rating: str, current: int) -> int:
    if rating == "again":
        return 0
    if rating == "hard":
        return max(1, current)
    if rating == "good":
        return 1 if current == 0 else max(2, round(current * 2.5))
    return 4 if current == 0 else max(4, round(current * 4))
