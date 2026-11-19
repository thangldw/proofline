from hypothesis import assume, given, settings
from hypothesis import strategies as st
from proofline.anchors import build_evidence_anchor, resolve_evidence_anchor

WORDS = st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=0, max_size=60)
QUOTES = st.text(alphabet="ABCDEFGHJKLMNPQRSTUVWXYZ0123456789", min_size=12, max_size=40)


def _anchor(content: str, quote: str):
    start = content.index(quote)
    return build_evidence_anchor(content, start, start + len(quote))


@settings(max_examples=200, deadline=None)
@given(before=WORDS, quote=QUOTES, after=WORDS)
def test_an_untouched_document_always_resolves_unchanged(before, quote, after):
    content = f"{before}\n{quote}\n{after}"
    resolution = resolve_evidence_anchor(
        quote=quote, cited_anchor=_anchor(content, quote), current_content=content
    )
    assert resolution.state == "unchanged"
    only = resolution.candidates[0]
    assert content[only.start_offset : only.end_offset] == quote


@settings(max_examples=200, deadline=None)
@given(before=WORDS, quote=QUOTES, after=WORDS, inserted=WORDS)
def test_inserting_text_never_loses_the_quote(before, quote, after, inserted):
    original = f"{before}\n{quote}\n{after}"
    edited = f"{inserted}\n{original}"
    resolution = resolve_evidence_anchor(
        quote=quote, cited_anchor=_anchor(original, quote), current_content=edited
    )
    assert resolution.state in {"unchanged", "moved"}
    assert all(edited[c.start_offset : c.end_offset] == quote for c in resolution.candidates)


@settings(max_examples=200, deadline=None)
@given(before=WORDS, quote=QUOTES, after=WORDS)
def test_duplicating_the_quote_is_ambiguous(before, quote, after):
    original = f"{before}\n{quote}\n{after}"
    duplicated = f"{original}\n{quote}\n"
    resolution = resolve_evidence_anchor(
        quote=quote, cited_anchor=_anchor(original, quote), current_content=duplicated
    )
    assert resolution.state == "ambiguous" and len(resolution.candidates) >= 2


@settings(max_examples=200, deadline=None)
@given(before=WORDS, quote=QUOTES, after=WORDS)
def test_removing_the_quote_is_never_reported_as_unchanged_or_moved(before, quote, after):
    original = f"{before}\n{quote}\n{after}"
    removed = f"{before}\n{after}"
    assume(quote not in removed)
    resolution = resolve_evidence_anchor(
        quote=quote, cited_anchor=_anchor(original, quote), current_content=removed
    )
    assert resolution.state in {"changed", "deleted"}
    assert all(c.similarity < 1.0 for c in resolution.candidates)


@settings(max_examples=100, deadline=None)
@given(before=WORDS, quote=QUOTES, after=WORDS)
def test_anchor_resolution_is_deterministic(before, quote, after):
    content = f"{before}\n{quote}\n{after}"
    anchor = _anchor(content, quote)
    first = resolve_evidence_anchor(quote=quote, cited_anchor=anchor, current_content=content)
    second = resolve_evidence_anchor(quote=quote, cited_anchor=anchor, current_content=content)
    assert first == second
