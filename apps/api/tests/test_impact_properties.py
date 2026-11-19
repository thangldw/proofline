"""Property tests: transitive impact equals reverse reachability on arbitrary (cyclic) graphs."""

import tempfile
from collections import deque
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from proofline.database import initialize_database, make_engine
from proofline.decision_impacts import (
    DEPENDENCY_RELATION_KINDS,
    compute_decision_impacts,
)
from proofline.decision_reviews import refresh_decision_reviews
from proofline.ingestion import ingest_source
from proofline.models import Decision, DecisionRelation
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

KINDS = ("based_on", "implements", "supersedes", "contradicts", "considered")


@st.composite
def graphs(draw):
    size = draw(st.integers(min_value=2, max_value=6))
    edges = draw(
        st.lists(
            st.tuples(
                st.integers(0, size - 1),
                st.integers(0, size - 1),
                st.sampled_from(KINDS),
            ).filter(lambda edge: edge[0] != edge[1]),  # the schema forbids self-relations
            max_size=12,
            unique_by=lambda edge: (edge[0], edge[1], edge[2]),
        )
    )
    return size, edges


def _build(session, size, edges):
    """Decision 0 is the root: it is approved, then its source changes so its review opens."""
    decisions: list[Decision] = []
    root_source = None
    for index in range(size):
        source, _ = ingest_source(
            session,
            SourceCreate(
                title=f"d{index}",
                uri=f"file:///d{index}.md",
                content=f"Decision: choice {index}.\nReason: original {index}.",
            ),
        )
        decision = session.scalar(
            select(Decision).where(
                Decision.source_version_id == source.current_version_id,
                Decision.kind == "decision",
            )
        )
        decision.status = "accepted"
        decisions.append(decision)
        if index == 0:
            root_source = source
    session.commit()
    for position, (src, tgt, kind) in enumerate(edges):
        session.add(
            DecisionRelation(
                id=f"relation-{position:03d}",
                source_decision_id=decisions[src].id,
                target_decision_id=decisions[tgt].id,
                kind=kind,
            )
        )
    session.commit()
    ingest_source(
        session,
        SourceCreate(
            title="d0",
            uri=root_source.uri,
            content="Decision: something else.\nReason: changed.",
        ),
    )
    refresh_decision_reviews(session, workspace_id=root_source.workspace_id)
    session.commit()
    return decisions, root_source.workspace_id


def _reference(size, edges):
    """Breadth-first reverse reachability from node 0 over dependency edges (target -> source)."""
    dependents: dict[int, list[int]] = {}
    for src, tgt, kind in edges:
        if kind in DEPENDENCY_RELATION_KINDS:
            dependents.setdefault(tgt, []).append(src)
    depth = {0: 0}
    queue = deque([0])
    while queue:
        node = queue.popleft()
        for nxt in dependents.get(node, ()):
            if nxt not in depth:
                depth[nxt] = depth[node] + 1
                queue.append(nxt)
    depth.pop(0)
    return depth


def _run(size, edges):
    with tempfile.TemporaryDirectory() as directory:
        engine = make_engine(f"sqlite:///{Path(directory) / 'p.db'}")
        initialize_database(engine)
        with sessionmaker(bind=engine, expire_on_commit=False)() as session:
            decisions, workspace_id = _build(session, size, edges)
            index_of = {decision.id: index for index, decision in enumerate(decisions)}
            findings = compute_decision_impacts(session, workspace_id=workspace_id)
            observed = [(index_of[item.impacted_decision_id], item) for item in findings]
        engine.dispose()
    return observed


@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(graph=graphs())
def test_impact_matches_reverse_reachability_with_shortest_depth(graph):
    size, edges = graph
    observed = _run(size, edges)

    assert {index: item.depth for index, item in observed} == _reference(size, edges)
    assert len({index for index, _ in observed}) == len(observed)
    for index, item in observed:
        assert index != 0
        assert len(item.relation_path) == item.depth == len(item.decision_path) - 1
        assert set(item.relation_kinds) <= DEPENDENCY_RELATION_KINDS


@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(graph=graphs())
def test_impact_paths_are_stable_when_relations_are_inserted_in_reverse(graph):
    size, edges = graph
    # Relation ids are positional, so reversing insertion order keeps a distinct id per edge
    # only if ids are reassigned; compare the reachability result, which must not depend on order.
    forward = {index: item.depth for index, item in _run(size, edges)}
    backward = {index: item.depth for index, item in _run(size, list(reversed(edges)))}
    assert forward == backward


WORDS = st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=3, max_size=30).map(str.strip)


@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(choice=WORDS, other=WORDS, notes_before=WORDS, notes_after=WORDS)
def test_stale_detection_distinguishes_moved_context_from_changed_quote(
    choice, other, notes_before, notes_after
):
    from proofline.decision_health import check_decision_health

    if len(choice) < 3 or choice == other or notes_before == notes_after:
        return

    def document(decision, notes):
        return f"Decision: use {decision}.\nReason: fits.\n\nNotes: {notes}."

    with tempfile.TemporaryDirectory() as directory:
        engine = make_engine(f"sqlite:///{Path(directory) / 'h.db'}")
        initialize_database(engine)
        with sessionmaker(bind=engine, expire_on_commit=False)() as session:
            source, _ = ingest_source(
                session,
                SourceCreate(
                    title="adr", uri="file:///adr.md", content=document(choice, notes_before)
                ),
            )
            decision = session.scalar(
                select(Decision).where(
                    Decision.source_version_id == source.current_version_id,
                    Decision.kind == "decision",
                )
            )
            assert decision is not None
            decision.status = "accepted"
            session.commit()
            assert check_decision_health(session) == []

            ingest_source(
                session,
                SourceCreate(title="adr", uri=source.uri, content=document(choice, notes_after)),
            )
            # The quote is still verbatim: at worst its surrounding context moved, never "changed".
            assert {item.reason for item in check_decision_health(session)} <= {"moved"}

            ingest_source(
                session,
                SourceCreate(title="adr", uri=source.uri, content=document(other, notes_after)),
            )
            findings = check_decision_health(session)
            assert decision.id in {item.decision_id for item in findings}
            assert {item.reason for item in findings} <= {"changed", "deleted"}
        engine.dispose()
