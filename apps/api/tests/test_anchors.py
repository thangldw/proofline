import hashlib

import pytest
from proofline.anchors import build_evidence_anchor, resolve_evidence_anchor


def test_duplicate_quote_is_ambiguous_instead_of_healthy():
    cited = "# Queue\n\nUse SQLite.\n"
    anchor = build_evidence_anchor(cited, 9, 20)
    current = "# Queue\n\nUse SQLite.\n\n# Cache\n\nUse SQLite.\n"

    result = resolve_evidence_anchor(
        quote="Use SQLite.", cited_anchor=anchor, current_content=current
    )

    assert result.state == "ambiguous"
    assert [item.start_offset for item in result.candidates] == [9, 31]


def test_unique_quote_with_same_section_and_context_is_unchanged():
    content = "# Queue\n\nBefore.\nUse SQLite.\nAfter.\n"
    anchor = build_evidence_anchor(content, 17, 28)

    result = resolve_evidence_anchor(
        quote="Use SQLite.", cited_anchor=anchor, current_content=content
    )

    assert result.state == "unchanged"
    assert result.candidates[0].start_line == 4
    assert result.candidates[0].section_path == ("Queue",)


def test_unique_quote_moved_to_another_section_requires_review():
    cited = "# Queue\n\nUse SQLite.\n"
    current = "# Cache\n\nUse SQLite.\n"

    result = resolve_evidence_anchor(
        quote="Use SQLite.",
        cited_anchor=build_evidence_anchor(cited, 9, 20),
        current_content=current,
    )

    assert result.state == "moved"
    assert result.candidates[0].section_path == ("Cache",)


def test_changed_candidates_are_deterministic_and_same_section_only():
    cited = "# Queue\n\nUse SQLite for durable writes.\n"
    quote = "Use SQLite for durable writes."
    current = (
        "# Cache\n\nUse SQLite for durable writes and cache entries.\n\n"
        "# Queue\n\nUse SQLite for crash-safe durable writes.\n"
    )

    result = resolve_evidence_anchor(
        quote=quote,
        cited_anchor=build_evidence_anchor(cited, 9, 39),
        current_content=current,
    )

    assert result.state == "changed"
    assert len(result.candidates) == 1
    assert result.candidates[0].section_path == ("Queue",)
    assert result.candidates[0].start_line == 7


def test_missing_quote_and_candidate_is_deleted():
    cited = "# Queue\n\nUse SQLite.\n"

    result = resolve_evidence_anchor(
        quote="Use SQLite.",
        cited_anchor=build_evidence_anchor(cited, 9, 20),
        current_content="# Queue\n\nRequirement removed.\n",
    )

    assert result.state == "deleted"
    assert result.candidates == ()


def test_context_hashes_normalize_crlf_whitespace_and_unicode_headings():
    lf = "# Độ bền\n\nBefore value\nUse SQLite.\nAfter value\n"
    crlf = "# Độ bền\r\n\r\n  Before   value \r\nUse SQLite.\r\nAfter value\r\n"
    lf_anchor = build_evidence_anchor(lf, 23, 34)
    crlf_anchor = build_evidence_anchor(crlf, 31, 42)

    assert lf_anchor.section_path == ("Độ bền",)
    assert crlf_anchor.section_path == lf_anchor.section_path
    assert crlf_anchor.prefix_sha256 == lf_anchor.prefix_sha256
    assert crlf_anchor.suffix_sha256 == lf_anchor.suffix_sha256


def test_empty_context_uses_sha256_of_empty_bytes():
    content = "Use SQLite."

    anchor = build_evidence_anchor(content, 0, len(content))

    empty_hash = hashlib.sha256(b"").hexdigest()
    assert anchor.prefix_sha256 == empty_hash
    assert anchor.suffix_sha256 == empty_hash


@pytest.mark.parametrize("start,end", [(-1, 3), (0, 0), (3, 2), (0, 99)])
def test_invalid_anchor_offsets_fail_with_content_free_code(start, end):
    with pytest.raises(ValueError, match="^anchor_span_invalid$"):
        build_evidence_anchor("abc", start, end)
