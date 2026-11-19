import proofline.cli as cli_module
from proofline.cli import main
from proofline.decision_graph import build_graph, render_dot, render_mermaid
from proofline.ingestion import ingest_source
from proofline.models import Decision, DecisionRelation
from proofline.schemas import SourceCreate
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def _approve(session, title, content, uri):
    source, _ = ingest_source(session, SourceCreate(title=title, uri=uri, content=content))
    decision = session.scalar(
        select(Decision).where(Decision.source_version_id == source.current_version_id)
    )
    decision.status = "accepted"
    session.commit()
    return decision


def _seed(session):
    one = _approve(session, "a", 'Decision: Use "SQLite" <fast> for the queue.', "file:///1.md")
    two = _approve(session, "b", "Decision: Use NATS for the queue.", "file:///2.md")
    three = _approve(session, "c", "Decision: Adopt quarterly planning.", "file:///3.md")
    session.add(
        DecisionRelation(source_decision_id=two.id, target_decision_id=one.id, kind="based_on")
    )
    session.commit()
    return one, two, three


def test_graph_has_relation_and_conflict_edges_and_skips_isolated(session):
    one, two, three = _seed(session)
    graph = build_graph(session)
    assert {n.id for n in graph.nodes} == {one.id, two.id}
    assert [e.kind for e in graph.edges] == ["based_on"]
    assert three.id in {n.id for n in build_graph(session, include_isolated=True).nodes}


def test_mermaid_and_dot_escape_labels(session):
    _seed(session)
    graph = build_graph(session)
    mermaid = render_mermaid(graph)
    assert mermaid.startswith("graph LR") and "-->|based_on|" in mermaid
    assert '"SQLite"' not in mermaid and "<fast>" not in mermaid and "#quot;" in mermaid
    dot = render_dot(graph)
    assert dot.startswith("digraph decisions {") and '\\"SQLite\\"' in dot


def test_no_titles_uses_short_ids(session):
    one, _, _ = _seed(session)
    mermaid = render_mermaid(build_graph(session, include_titles=False))
    assert one.id[:8] in mermaid and "SQLite" not in mermaid


def test_cli_graph(session, monkeypatch, capsys):
    _seed(session)
    monkeypatch.setattr(
        cli_module, "SessionLocal", sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    )
    main(["graph", "--format", "dot", "--no-titles"])
    assert "digraph" in capsys.readouterr().out
    main(["graph"])
    assert "graph LR" in capsys.readouterr().out
