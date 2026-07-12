import { useCallback, useEffect, useRef, useState } from "react";
import { BookOpen, Database, FileSearch, GitBranch, Search, Upload, X } from "lucide-react";
import { api } from "./api";
import type { Evidence, GroundedAnswer, IngestionJob, Memory, MemoryKind, Overview, SearchHit, Source, SourceDeletionImpact } from "./types";

type View = "search" | "memories" | "sources";

type DeletionState = {
  source: Source;
  impact: SourceDeletionImpact | null;
  loading: boolean;
  pending: boolean;
  error: string;
};

export function App() {
  const [view, setView] = useState<View>("search");
  const [overview, setOverview] = useState<Overview>({ sources: 0, chunks: 0, decisions: 0, memories: 0, evidence: 0 });
  const [sources, setSources] = useState<Source[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [jobs, setJobs] = useState<IngestionJob[]>([]);
  const [evidence, setEvidence] = useState<{ item: Evidence; sourceTitle: string } | null>(null);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [nextOverview, nextSources, nextMemories, nextJobs] = await Promise.all([
        api.overview(), api.sources(), api.memories(), api.jobs(),
      ]);
      setOverview(nextOverview); setSources(nextSources); setMemories(nextMemories); setJobs(nextJobs); setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Cannot reach Proofline API"); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  async function importFile(file: File) {
    setImporting(true);
    try { await api.importSource(file.name, await file.text(), `file://${file.name}`); await refresh(); setView("memories"); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Import failed"); }
    finally { setImporting(false); }
  }

  const failedState = (job: IngestionJob) => ["failed", "dead_letter"].includes(job.state);
  const indexDegraded = latestJobs(jobs).some(job => Boolean(job.source_id) && failedState(job))
    || jobs.some(job => !job.source_id && failedState(job));

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">P</span><span>Proofline</span></div>
      <div className="workspace"><span>LOCAL WORKSPACE</span><strong>Engineering memory</strong></div>
      <nav aria-label="Primary navigation">
        <Nav icon={<Search size={18}/>} active={view === "search"} onClick={() => setView("search")}>Search</Nav>
        <Nav icon={<GitBranch size={18}/>} active={view === "memories"} onClick={() => setView("memories")} count={overview.memories}>Memories</Nav>
        <Nav icon={<BookOpen size={18}/>} active={view === "sources"} onClick={() => setView("sources")} count={overview.sources}>Sources</Nav>
      </nav>
      <div className="system-status"><span className={error || indexDegraded ? "dot error-dot" : "dot"}/><div><strong>{error ? "API unavailable" : indexDegraded ? "Index degraded" : "Index ready"}</strong><span>{overview.chunks} searchable chunks</span></div></div>
    </aside>
    <main>
      {error && <div className="error-banner">{error}</div>}
      <header className="topbar"><div><span className="eyebrow">EVIDENCE-FIRST MEMORY</span><h1>{view[0].toUpperCase() + view.slice(1)}</h1></div>
        <label className="import-button"><Upload size={16}/>{importing ? "Indexing…" : "Import Markdown"}<input type="file" accept=".md,.txt,text/markdown,text/plain" disabled={importing} onChange={(event) => { const file = event.target.files?.[0]; if (file) void importFile(file); }}/></label>
      </header>
      {view === "search" && (
        <SearchView onEvidence={(item, sourceTitle) => setEvidence({item, sourceTitle})}/>
      )}
      {view === "memories" && (
        <MemoryView
          memories={memories}
          onChanged={refresh}
          onEvidence={(item, sourceTitle) => setEvidence({item, sourceTitle})}
        />
      )}
      {view === "sources" && (
        <SourcesView
          sources={sources}
          jobs={jobs}
          onChanged={refresh}
          onSourceDeleted={(sourceId) => setEvidence(current =>
            current?.item.source_id === sourceId ? null : current)}
        />
      )}
    </main>
    {evidence && <EvidenceDrawer {...evidence} onClose={() => setEvidence(null)}/>} 
  </div>;
}

function Nav({icon, active, onClick, count, children}: {icon: React.ReactNode; active: boolean; onClick: () => void; count?: number; children: React.ReactNode}) {
  return <button className={active ? "nav-item active" : "nav-item"} onClick={onClick}>{icon}<span>{children}</span>{count !== undefined && <b>{count}</b>}</button>;
}

export function SearchView({onEvidence}: {onEvidence: (item: Evidence, title: string) => void}) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [answer, setAnswer] = useState<GroundedAnswer | null>(null);
  const [searched, setSearched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [answerError, setAnswerError] = useState("");
  async function run(event: React.FormEvent) {
    event.preventDefault();
    if (query.trim().length < 2) return;
    setBusy(true);
    setSearchError("");
    setAnswerError("");
    setAnswer(null);
    setHits([]);
    setSearched(false);
    try {
      const searchRequest = api.search(query).then(
        nextHits => {
          setHits(nextHits);
          setSearched(true);
        },
        reason => {
          setSearchError(errorMessage(reason, "Search failed"));
          setSearched(true);
        },
      );
      const answerRequest = api.answer(query).then(
        nextAnswer => {
          setAnswer(nextAnswer);
          if (nextAnswer.status === "provider_unavailable") {
            setAnswerError("Answer generation is unavailable. Showing raw retrieval results.");
          }
        },
        reason => {
          setAnswerError(
            `${errorMessage(reason, "Answer generation failed")}. Showing raw retrieval results.`,
          );
        },
      );
      await Promise.allSettled([searchRequest, answerRequest]);
    } finally {
      setBusy(false);
    }
  }
  function openCitation(citation: GroundedAnswer["citations"][number]) {
    onEvidence({
      id: citation.evidence_id,
      source_id: citation.source_id,
      source_version_id: citation.source_version_id,
      quote: citation.content,
      start_offset: citation.start_offset,
      end_offset: citation.end_offset,
      start_line: citation.start_line,
      end_line: citation.end_line,
    }, citation.source_title);
  }
  const citationById = new Map(answer?.citations.map(citation => [citation.evidence_id, citation]));
  const unresolvedEvidenceIds = answer
    ? [...new Set(answer.statements.flatMap(statement => statement.evidence_ids))]
      .filter(evidenceId => !citationById.has(evidenceId))
    : [];
  const integrityFailed = unresolvedEvidenceIds.length > 0;
  return <section className="content search-view">
    <form className="search-box" onSubmit={run}><FileSearch/><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search why a system was built this way…" aria-label="Search engineering memory"/><button disabled={busy}>{busy ? "Searching" : "Search"}</button></form>
    {!searched && <div className="hero-empty"><div className="line-art">↳</div><h2>Follow every claim back to its source.</h2><p>Search technical decisions, rationale, and implementation context. Proofline returns inspectable evidence—not an uncited answer.</p></div>}
    {answerError && <div className="degraded-banner" role="status">{answerError}</div>}
    {searchError && <div className="error-banner inline-error" role="alert">{searchError}</div>}
    {answer && <article className="result-card answer-card"><div className="decision-top"><span className={`mode-badge${integrityFailed ? " integrity-failed" : ""}`}>{integrityFailed ? "integrity failure" : answer.status.replaceAll("_", " ")}</span>{answer.model_run_id && <span>Run {answer.model_run_id.slice(0, 8)}</span>}</div><h2>{integrityFailed ? "Answer citation integrity failed" : "Evidence-backed answer"}</h2>{integrityFailed && <div className="integrity-error" role="alert">Citation integrity failed: {unresolvedEvidenceIds.length} referenced evidence {unresolvedEvidenceIds.length === 1 ? "ID is" : "IDs are"} unavailable.</div>}{!integrityFailed && <><p>{answer.answer}</p><div className="answer-statements">{answer.statements.map((statement, index) => {
      const statementCitations = [...new Set(statement.evidence_ids)].flatMap(evidenceId => {
        const citation = citationById.get(evidenceId);
        return citation ? [citation] : [];
      });
      return <article className="answer-statement" aria-label={`Answer statement: ${statement.kind}`} key={`${statement.kind}-${index}`}><div><span className={`statement-kind ${statement.kind}`}>{statement.kind}</span><p>{statement.text}</p></div>{statementCitations.length > 0 && <footer>{statementCitations.map(citation => <button key={citation.evidence_id} onClick={() => openCitation(citation)}>{citation.source_title} · L{citation.start_line}–{citation.end_line}</button>)}</footer>}</article>;
    })}</div></>}</article>}
    {searched && <div className="results"><div className="section-heading"><div><span className="eyebrow">RAW RETRIEVAL</span><h2>{hits.length} evidence matches</h2></div><span className="mode-badge">{hits.some(hit => hit.retrieval_channels.includes("semantic")) ? "Hybrid · RRF" : "Lexical · FTS5"}</span></div>
      {hits.length === 0 ? <div className="empty-card">Insufficient evidence. Try another phrase or import a source.</div> : hits.map(hit => <article className="result-card" key={hit.chunk_id}><div className="result-meta"><span>{hit.source_title}</span><button onClick={() => onEvidence({id: hit.chunk_id, source_id: hit.source_id, source_version_id: hit.source_version_id, quote: hit.content, start_offset: hit.start_offset, end_offset: hit.end_offset, start_line: hit.start_line, end_line: hit.end_line}, hit.source_title)}>Lines {hit.start_line}–{hit.end_line}</button></div><p>{hit.content}</p></article>)}</div>}
  </section>;
}

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof Error && reason.message ? reason.message : fallback;
}

function latestJobs(jobs: IngestionJob[]): IngestionJob[] {
  const ordered = [...jobs].sort((left, right) => right.updated_at.localeCompare(left.updated_at));
  const bySource = new Map<string, IngestionJob>();
  let orphan: IngestionJob | null = null;
  for (const job of ordered) {
    if (job.source_id) {
      if (!bySource.has(job.source_id)) bySource.set(job.source_id, job);
    } else if (!orphan) {
      orphan = job;
    }
  }
  return orphan ? [...bySource.values(), orphan] : [...bySource.values()];
}

const memoryKinds: MemoryKind[] = ["decision", "assumption", "constraint", "alternative"];
const memoryStatuses = ["candidate", "active", "accepted", "rejected", "obsolete"] as const;
type MemoryStatus = typeof memoryStatuses[number];

export function MemoryView({memories, onEvidence, onChanged}: {memories: Memory[]; onEvidence: (item: Evidence, title: string) => void; onChanged: () => Promise<void>}) {
  const [kindFilter, setKindFilter] = useState<MemoryKind | "all">("all");
  const [statusFilter, setStatusFilter] = useState<MemoryStatus | "all">("all");
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [reviewErrors, setReviewErrors] = useState<Record<string, string>>({});
  const filtered = memories.filter(memory =>
    (kindFilter === "all" || memory.kind === kindFilter)
    && (statusFilter === "all" || memory.status === statusFilter));
  async function setStatus(memory: Memory, status: "accepted" | "rejected" | "obsolete") {
    setReviewingId(memory.id);
    setReviewErrors(current => ({ ...current, [memory.id]: "" }));
    try {
      await api.updateMemory(memory.id, { status });
      await onChanged();
    } catch (reason) {
      setReviewErrors(current => ({
        ...current,
        [memory.id]: errorMessage(reason, "Memory review failed"),
      }));
    } finally {
      setReviewingId(null);
    }
  }
  return <section className="content"><div className="section-heading"><div><span className="eyebrow">MEMORY REGISTRY</span><h2>Reviewable engineering context</h2></div><span className="mode-badge">{filtered.length} of {memories.length}</span></div><div className="registry-filters"><fieldset><legend>Kind</legend><button aria-pressed={kindFilter === "all"} onClick={() => setKindFilter("all")}>All</button>{memoryKinds.map(kind => <button key={kind} aria-pressed={kindFilter === kind} onClick={() => setKindFilter(kind)}>{kind[0].toUpperCase() + kind.slice(1)}s</button>)}</fieldset><fieldset><legend>Status</legend><button aria-pressed={statusFilter === "all"} onClick={() => setStatusFilter("all")}>All</button>{memoryStatuses.map(status => <button key={status} aria-pressed={statusFilter === status} onClick={() => setStatusFilter(status)}>{status}</button>)}</fieldset></div>
    {filtered.length === 0 ? <div className="empty-card">No memories match these filters. Import an ADR or change the selected kind and status.</div> : <div className="decision-grid">{filtered.map(memory => <article className="decision-card memory-card" aria-label={`${memory.kind} memory: ${memory.statement}`} key={memory.id}><div className="decision-top"><span className="memory-labels"><span className={`memory-kind ${memory.kind}`} aria-label={`Memory kind: ${memory.kind}`}>{memory.kind}</span><span className={`status ${memory.status}`}>{memory.status}</span></span><span>{Math.round(memory.confidence * 100)}% · {memory.extraction_method}</span></div><h3>{memory.statement}</h3>{memory.rationale && <p>{memory.rationale}</p>}<div className="review-actions"><button disabled={reviewingId === memory.id} onClick={() => void setStatus(memory, "accepted")} aria-label={`Accept ${memory.kind}: ${memory.statement}`}>Accept</button><button disabled={reviewingId === memory.id} onClick={() => void setStatus(memory, "rejected")} aria-label={`Reject ${memory.kind}: ${memory.statement}`}>Reject</button><button disabled={reviewingId === memory.id} onClick={() => void setStatus(memory, "obsolete")} aria-label={`Mark obsolete ${memory.kind}: ${memory.statement}`}>Mark obsolete</button></div>{reviewErrors[memory.id] && <div className="action-error" role="alert">{reviewErrors[memory.id]}</div>}<footer><span>{memory.source_title}</span>{memory.evidence.map(item => <button key={item.id} onClick={() => onEvidence(item, memory.source_title)}>View proof · L{item.start_line}–{item.end_line}</button>)}</footer></article>)}</div>}
  </section>;
}

export function SourcesView({sources, jobs, onChanged, onSourceDeleted}: {sources: Source[]; jobs: IngestionJob[]; onChanged: () => Promise<void>; onSourceDeleted?: (sourceId: string) => void}) {
  const [extractingSourceId, setExtractingSourceId] = useState<string | null>(null);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [extractionErrors, setExtractionErrors] = useState<Record<string, string>>({});
  const [retryErrors, setRetryErrors] = useState<Record<string, string>>({});
  const [deletion, setDeletion] = useState<DeletionState | null>(null);
  const deleteTriggerRef = useRef<HTMLElement | null>(null);
  const jobsBySource = new Map(
    latestJobs(jobs).flatMap(job => job.source_id ? [[job.source_id, job] as const] : []),
  );
  const orphanFailures = [...jobs]
    .filter(job => !job.source_id && ["failed", "dead_letter"].includes(job.state))
    .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
    .slice(0, 5);
  async function extract(sourceId: string) {
    setExtractingSourceId(sourceId);
    setExtractionErrors(current => ({ ...current, [sourceId]: "" }));
    try {
      await api.extractMemories(sourceId);
      await onChanged();
    } catch (reason) {
      setExtractionErrors(current => ({
        ...current,
        [sourceId]: errorMessage(reason, "AI memory extraction failed"),
      }));
    } finally {
      setExtractingSourceId(null);
    }
  }
  async function retry(job: IngestionJob) {
    setRetryingJobId(job.id);
    setRetryErrors(current => ({ ...current, [job.id]: "" }));
    try {
      await api.retryJob(job.id);
      await onChanged();
    } catch (reason) {
      setRetryErrors(current => ({
        ...current,
        [job.id]: errorMessage(reason, "Ingestion retry failed"),
      }));
    } finally {
      setRetryingJobId(null);
    }
  }
  async function openDeletion(source: Source) {
    deleteTriggerRef.current = document.activeElement as HTMLElement | null;
    setDeletion({ source, impact: null, loading: true, pending: false, error: "" });
    try {
      const impact = await api.deletionImpact(source.id);
      setDeletion(current => current?.source.id === source.id
        ? { ...current, impact, loading: false }
        : current);
    } catch (reason) {
      setDeletion(current => current?.source.id === source.id
        ? { ...current, loading: false, error: errorMessage(reason, "Deletion preview failed") }
        : current);
    }
  }
  function closeDeletion() {
    if (deletion?.pending) return;
    const trigger = deleteTriggerRef.current;
    setDeletion(null);
    queueMicrotask(() => trigger?.focus());
  }
  async function confirmDeletion() {
    if (!deletion?.impact || deletion.pending) return;
    const sourceId = deletion.source.id;
    setDeletion(current => current ? { ...current, pending: true, error: "" } : current);
    try {
      await api.deleteSource(sourceId);
      onSourceDeleted?.(sourceId);
      await onChanged();
      const trigger = deleteTriggerRef.current;
      setDeletion(null);
      queueMicrotask(() => trigger?.focus());
    } catch (reason) {
      setDeletion(current => current?.source.id === sourceId
        ? { ...current, pending: false, error: errorMessage(reason, "Source deletion failed") }
        : current);
    }
  }
  return <section className="content"><div className="metrics"><Metric value={sources.length} label="Sources detected"/><Metric value={sources.reduce((n,s) => n+s.chunk_count,0)} label="Searchable chunks"/><Metric value={sources.reduce((n,s) => n+s.memory_count,0)} label="Memories found"/></div>{orphanFailures.length > 0 && <section className="recent-failures" aria-labelledby="recent-ingestion-failures"><div className="section-heading"><div><span className="eyebrow">PIPELINE DIAGNOSTICS</span><h2 id="recent-ingestion-failures">Recent ingestion failures</h2></div><span className="mode-badge">{orphanFailures.length} orphaned</span></div><div className="failure-list">{orphanFailures.map(job => <article className={`failure-card ${job.state}`} key={job.id}><div className="failure-summary"><strong>Job {job.id.slice(0, 8)}</strong><span>{job.state} · {job.stage}</span></div><div className="failure-metadata"><span>Attempt {job.attempts}/{job.max_attempts}</span><span>Started {job.started_at ?? "not recorded"}</span><span>Finished {job.finished_at ?? "not recorded"}</span></div>{job.error_code && <code>{job.error_code}</code>}{job.error_detail && <p>{job.error_detail}</p>}{job.state === "failed" && job.retryable && <button disabled={retryingJobId === job.id} onClick={() => void retry(job)} aria-label={`Retry ingestion job ${job.id.slice(0, 8)}`}>{retryingJobId === job.id ? "Retrying…" : "Retry"}</button>}{retryErrors[job.id] && <small className="action-error" role="alert">{retryErrors[job.id]}</small>}</article>)}</div></section>}<div className="source-table source-diagnostics"><div className="table-row table-head"><span>Source</span><span>Type</span><span>Objects</span><span>Health</span><span>Actions</span></div>{sources.map(source => {
    const job = jobsBySource.get(source.id);
    const extractionError = extractionErrors[source.id];
    return <div className="table-row" key={source.id}><span><strong>{source.title}</strong><small>{source.uri ?? "Local import"}</small></span><span>{source.kind}</span><span>{source.chunk_count} chunks · {source.memory_count} memories</span><span className={`job-health ${job?.state ?? source.status}`}><strong>{job ? `${job.state} · ${job.stage}` : source.status}</strong><small>{job ? `Attempt ${job.attempts}/${job.max_attempts} · ${job.retryable ? "Retryable" : "Not retryable"}` : "No ingestion job recorded"}</small>{job?.error_code && <small className="job-error-code">{job.error_code}</small>}{job?.error_detail && <small className="job-error-detail">{job.error_detail}</small>}</span><span className="source-actions">{job?.state === "failed" && job.retryable && <button disabled={retryingJobId === job.id} onClick={() => void retry(job)} aria-label={`Retry ingestion for ${source.title}`}>{retryingJobId === job.id ? "Retrying…" : "Retry ingestion"}</button>}<button disabled={extractingSourceId === source.id || retryingJobId === job?.id} onClick={() => void extract(source.id)} aria-label={`Extract AI memories from ${source.title}`}>{extractingSourceId === source.id ? "Extracting…" : "Extract AI memories"}</button><button className="danger-action" onClick={() => void openDeletion(source)} aria-label={`Delete ${source.title}`}>Delete</button>{job && retryErrors[job.id] && <small className="action-error" role="alert">{retryErrors[job.id]}</small>}{extractionError && <small className="action-error" role="alert">{extractionError}</small>}</span></div>;
  })}</div>{deletion && <DeletionDialog state={deletion} onCancel={closeDeletion} onConfirm={() => void confirmDeletion()}/>}</section>;
}

function DeletionDialog({state, onCancel, onConfirm}: {state: DeletionState; onCancel: () => void; onConfirm: () => void}) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!state.pending) cancelRef.current?.focus();
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !state.pending) onCancel();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onCancel, state.pending]);
  const impactCounts = state.impact ? [
    ["Versions", state.impact.versions],
    ["Chunks", state.impact.chunks],
    ["Embeddings", state.impact.embeddings],
    ["Memories", state.impact.memories],
    ["Decisions", state.impact.decisions],
    ["Evidence", state.impact.evidence],
    ["Jobs detached", state.impact.ingestion_jobs_to_detach],
    ["Audit events", state.impact.audit_events_to_delete],
    ["FTS rows", state.impact.fts_rows],
  ] as const : [];
  return <div className="dialog-backdrop"><section className="deletion-dialog" role="dialog" aria-modal="true" aria-labelledby="deletion-dialog-title"><span className="eyebrow">DELETION IMPACT</span><h2 id="deletion-dialog-title">Delete {state.source.title}?</h2><p>This permanently removes the source and its derived local data.</p>{state.loading && <div role="status">Loading deletion impact…</div>}{state.error && <div className="integrity-error" role="alert">{state.error}</div>}{state.impact && <><div className="deletion-identity"><span>Current version</span><code>{state.impact.current_version_id ?? "none"}</code></div><dl className="impact-counts">{impactCounts.map(([label, count]) => <div key={label}><dt>{label}</dt><dd>{count}</dd></div>)}</dl></>}<footer><button ref={cancelRef} disabled={state.pending} onClick={onCancel}>Cancel</button><button className="confirm-delete" disabled={!state.impact || state.pending} onClick={onConfirm}>{state.pending ? "Deleting…" : "Delete permanently"}</button></footer></section></div>;
}

function Metric({value,label}: {value: number; label: string}) { return <div className="metric"><strong>{value}</strong><span>{label}</span></div>; }

function EvidenceDrawer({item, sourceTitle, onClose}: {item: Evidence; sourceTitle: string; onClose: () => void}) {
  const [sourceContent, setSourceContent] = useState("");
  useEffect(() => { void api.sourceVersion(item.source_id, item.source_version_id).then(version => setSourceContent(version.content)); }, [item.source_id, item.source_version_id]);
  const quote = item.quote || sourceContent.slice(item.start_offset, item.end_offset);
  return <aside className="drawer"><header><div><span className="eyebrow">EXACT EVIDENCE</span><h2>{sourceTitle}</h2></div><button aria-label="Close evidence" onClick={onClose}><X/></button></header><div className="locator">Lines {item.start_line}–{item.end_line} <span>·</span> offsets {item.start_offset}:{item.end_offset}</div><blockquote>{quote}</blockquote><div className="integrity"><Database size={16}/><span><strong>Source-backed span</strong>This quote is stored with its exact source offsets.</span></div></aside>;
}
