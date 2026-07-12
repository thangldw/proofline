import { useCallback, useEffect, useState } from "react";
import { BookOpen, Database, FileSearch, GitBranch, Search, Upload, X } from "lucide-react";
import { api } from "./api";
import type { Decision, Evidence, Overview, SearchHit, Source } from "./types";

type View = "search" | "decisions" | "sources";

export function App() {
  const [view, setView] = useState<View>("search");
  const [overview, setOverview] = useState<Overview>({ sources: 0, chunks: 0, decisions: 0, evidence: 0 });
  const [sources, setSources] = useState<Source[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [evidence, setEvidence] = useState<{ item: Evidence; sourceTitle: string } | null>(null);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [nextOverview, nextSources, nextDecisions] = await Promise.all([
        api.overview(), api.sources(), api.decisions(),
      ]);
      setOverview(nextOverview); setSources(nextSources); setDecisions(nextDecisions); setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Cannot reach Proofline API"); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  async function importFile(file: File) {
    setImporting(true);
    try { await api.importSource(file.name, await file.text(), `file://${file.name}`); await refresh(); setView("decisions"); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Import failed"); }
    finally { setImporting(false); }
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">P</span><span>Proofline</span></div>
      <div className="workspace"><span>LOCAL WORKSPACE</span><strong>Engineering memory</strong></div>
      <nav aria-label="Primary navigation">
        <Nav icon={<Search size={18}/>} active={view === "search"} onClick={() => setView("search")}>Search</Nav>
        <Nav icon={<GitBranch size={18}/>} active={view === "decisions"} onClick={() => setView("decisions")} count={overview.decisions}>Decisions</Nav>
        <Nav icon={<BookOpen size={18}/>} active={view === "sources"} onClick={() => setView("sources")} count={overview.sources}>Sources</Nav>
      </nav>
      <div className="system-status"><span className={error ? "dot error-dot" : "dot"}/><div><strong>{error ? "API unavailable" : "Index ready"}</strong><span>{overview.chunks} searchable chunks</span></div></div>
    </aside>
    <main>
      {error && <div className="error-banner">{error}</div>}
      <header className="topbar"><div><span className="eyebrow">EVIDENCE-FIRST MEMORY</span><h1>{view[0].toUpperCase() + view.slice(1)}</h1></div>
        <label className="import-button"><Upload size={16}/>{importing ? "Indexing…" : "Import Markdown"}<input type="file" accept=".md,.txt,text/markdown,text/plain" disabled={importing} onChange={(event) => { const file = event.target.files?.[0]; if (file) void importFile(file); }}/></label>
      </header>
      {view === "search" && <SearchView onEvidence={(item, sourceTitle) => setEvidence({item, sourceTitle})}/>} 
      {view === "decisions" && <DecisionView decisions={decisions} onEvidence={(item, sourceTitle) => setEvidence({item, sourceTitle})}/>} 
      {view === "sources" && <SourcesView sources={sources}/>} 
    </main>
    {evidence && <EvidenceDrawer {...evidence} onClose={() => setEvidence(null)}/>} 
  </div>;
}

function Nav({icon, active, onClick, count, children}: {icon: React.ReactNode; active: boolean; onClick: () => void; count?: number; children: React.ReactNode}) {
  return <button className={active ? "nav-item active" : "nav-item"} onClick={onClick}>{icon}<span>{children}</span>{count !== undefined && <b>{count}</b>}</button>;
}

function SearchView({onEvidence}: {onEvidence: (item: Evidence, title: string) => void}) {
  const [query, setQuery] = useState(""); const [hits, setHits] = useState<SearchHit[]>([]); const [searched, setSearched] = useState(false); const [busy, setBusy] = useState(false);
  async function run(event: React.FormEvent) { event.preventDefault(); if (query.trim().length < 2) return; setBusy(true); try { setHits(await api.search(query)); setSearched(true); } finally { setBusy(false); } }
  return <section className="content search-view">
    <form className="search-box" onSubmit={run}><FileSearch/><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search why a system was built this way…" aria-label="Search engineering memory"/><button disabled={busy}>{busy ? "Searching" : "Search"}</button></form>
    {!searched && <div className="hero-empty"><div className="line-art">↳</div><h2>Follow every claim back to its source.</h2><p>Search technical decisions, rationale, and implementation context. Proofline returns inspectable evidence—not an uncited answer.</p></div>}
    {searched && <div className="results"><div className="section-heading"><div><span className="eyebrow">RAW RETRIEVAL</span><h2>{hits.length} evidence matches</h2></div><span className="mode-badge">Lexical · FTS5</span></div>
      {hits.length === 0 ? <div className="empty-card">Insufficient evidence. Try another phrase or import a source.</div> : hits.map(hit => <article className="result-card" key={hit.chunk_id}><div className="result-meta"><span>{hit.source_title}</span><button onClick={() => onEvidence({id: hit.chunk_id, source_id: hit.source_id, quote: hit.content, start_offset: hit.start_offset, end_offset: hit.end_offset, start_line: hit.start_line, end_line: hit.end_line}, hit.source_title)}>Lines {hit.start_line}–{hit.end_line}</button></div><p>{hit.content}</p></article>)}</div>}
  </section>;
}

function DecisionView({decisions, onEvidence}: {decisions: Decision[]; onEvidence: (item: Evidence, title: string) => void}) {
  return <section className="content"><div className="section-heading"><div><span className="eyebrow">DECISION REGISTRY</span><h2>Recorded technical choices</h2></div><span className="mode-badge">{decisions.length} extracted</span></div>
    {decisions.length === 0 ? <div className="empty-card">No decisions yet. Import a Markdown ADR containing a “Decision:” or “Quyết định:” section.</div> : <div className="decision-grid">{decisions.map(decision => <article className="decision-card" key={decision.id}><div className="decision-top"><span className={`status ${decision.status}`}>{decision.status}</span><span>{Math.round(decision.confidence * 100)}% · {decision.extraction_method}</span></div><h3>{decision.statement}</h3>{decision.rationale && <p>{decision.rationale}</p>}<footer><span>{decision.source_title}</span>{decision.evidence.map(item => <button key={item.id} onClick={() => onEvidence(item, decision.source_title)}>View proof · L{item.start_line}–{item.end_line}</button>)}</footer></article>)}</div>}
  </section>;
}

function SourcesView({sources}: {sources: Source[]}) {
  return <section className="content"><div className="metrics"><Metric value={sources.length} label="Sources detected"/><Metric value={sources.reduce((n,s) => n+s.chunk_count,0)} label="Searchable chunks"/><Metric value={sources.reduce((n,s) => n+s.decision_count,0)} label="Decisions found"/></div><div className="source-table"><div className="table-row table-head"><span>Source</span><span>Type</span><span>Objects</span><span>Health</span></div>{sources.map(source => <div className="table-row" key={source.id}><span><strong>{source.title}</strong><small>{source.uri ?? "Local import"}</small></span><span>{source.kind}</span><span>{source.chunk_count} chunks · {source.decision_count} decisions</span><span className="ready"><i/>Ready</span></div>)}</div></section>;
}

function Metric({value,label}: {value: number; label: string}) { return <div className="metric"><strong>{value}</strong><span>{label}</span></div>; }

function EvidenceDrawer({item, sourceTitle, onClose}: {item: Evidence; sourceTitle: string; onClose: () => void}) {
  const [sourceContent, setSourceContent] = useState("");
  useEffect(() => { void api.source(item.source_id).then(source => setSourceContent(source.content)); }, [item.source_id]);
  const quote = item.quote || sourceContent.slice(item.start_offset, item.end_offset);
  return <aside className="drawer"><header><div><span className="eyebrow">EXACT EVIDENCE</span><h2>{sourceTitle}</h2></div><button aria-label="Close evidence" onClick={onClose}><X/></button></header><div className="locator">Lines {item.start_line}–{item.end_line} <span>·</span> offsets {item.start_offset}:{item.end_offset}</div><blockquote>{quote}</blockquote><div className="integrity"><Database size={16}/><span><strong>Source-backed span</strong>This quote is stored with its exact source offsets.</span></div></aside>;
}
