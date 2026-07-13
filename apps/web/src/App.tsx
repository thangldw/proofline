import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  BookOpen,
  Database,
  FileSearch,
  GitBranch,
  Search,
  Settings,
  Upload,
  X,
} from "lucide-react";
import { api } from "./api";
import type {
  DecisionTimeline,
  Evidence,
  GroundedAnswer,
  IngestionJob,
  Memory,
  MemoryKind,
  ModelRun,
  ModelRunFilters,
  Overview,
  ProviderConfiguration,
  ProviderStatus,
  SearchHit,
  SearchScope,
  Source,
  SourceDeletionImpact,
  Workspace,
} from "./types";

type View = "search" | "memories" | "sources" | "model runs" | "settings";

type DeletionState = {
  source: Source;
  impact: SourceDeletionImpact | null;
  loading: boolean;
  pending: boolean;
  error: string;
};

export function App() {
  const [view, setView] = useState<View>("search");
  const [overview, setOverview] = useState<Overview>({
    sources: 0,
    chunks: 0,
    decisions: 0,
    memories: 0,
    evidence: 0,
  });
  const [sources, setSources] = useState<Source[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [jobs, setJobs] = useState<IngestionJob[]>([]);
  const [evidence, setEvidence] = useState<{
    item: Evidence;
    sourceTitle: string;
  } | null>(null);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState("");
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [nextOverview, nextSources, nextMemories, nextJobs] =
        await Promise.all([
          api.overview(),
          api.sources(),
          api.memories(),
          api.jobs(),
        ]);
      setOverview(nextOverview);
      setSources(nextSources);
      setMemories(nextMemories);
      setJobs(nextJobs);
      setError("");
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Cannot reach Proofline API",
      );
    }
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const available = await api.workspaces();
        const selected = available[0]?.id ?? "";
        setWorkspaces(available);
        setWorkspaceId(selected);
        if (selected) api.setWorkspace(selected);
        await refresh();
      } catch (reason) {
        setError(
          reason instanceof Error ? reason.message : "Cannot reach Proofline API",
        );
      }
    })();
  }, [refresh]);

  async function importFile(file: File) {
    setImporting(true);
    try {
      await api.importSource(
        file.name,
        await file.text(),
        `file://${file.name}`,
      );
      await refresh();
      setView("memories");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Import failed");
    } finally {
      setImporting(false);
    }
  }

  const failedState = (job: IngestionJob) =>
    ["failed", "dead_letter"].includes(job.state);
  const indexDegraded =
    latestJobs(jobs).some(
      (job) => Boolean(job.source_id) && failedState(job),
    ) || jobs.some((job) => !job.source_id && failedState(job));

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">P</span>
          <span>Proofline</span>
        </div>
        <div className="workspace">
          <span>LOCAL WORKSPACE</span>
          <label htmlFor="workspace-select" className="sr-only">
            Active workspace
          </label>
          <select
            id="workspace-select"
            aria-label="Active workspace"
            value={workspaceId}
            disabled={workspaces.length < 2}
            onChange={(event) => {
              const selected = event.target.value;
              api.setWorkspace(selected);
              setWorkspaceId(selected);
              setEvidence(null);
              void refresh();
            }}
          >
            {workspaces.map((workspace) => (
              <option key={workspace.id} value={workspace.id}>
                {workspace.title}
              </option>
            ))}
          </select>
        </div>
        <nav aria-label="Primary navigation">
          <Nav
            icon={<Search size={18} />}
            active={view === "search"}
            onClick={() => setView("search")}
          >
            Search
          </Nav>
          <Nav
            icon={<GitBranch size={18} />}
            active={view === "memories"}
            onClick={() => setView("memories")}
            count={overview.memories}
          >
            Memories
          </Nav>
          <Nav
            icon={<BookOpen size={18} />}
            active={view === "sources"}
            onClick={() => setView("sources")}
            count={overview.sources}
          >
            Sources
          </Nav>
          <Nav
            icon={<Activity size={18} />}
            active={view === "model runs"}
            onClick={() => setView("model runs")}
          >
            Model runs
          </Nav>
          <Nav
            icon={<Settings size={18} />}
            active={view === "settings"}
            onClick={() => setView("settings")}
          >
            Settings
          </Nav>
        </nav>
        <div className="system-status">
          <span className={error || indexDegraded ? "dot error-dot" : "dot"} />
          <div>
            <strong>
              {error
                ? "API unavailable"
                : indexDegraded
                  ? "Index degraded"
                  : "Index ready"}
            </strong>
            <span>{overview.chunks} searchable chunks</span>
          </div>
        </div>
      </aside>
      <main>
        {error && <div className="error-banner">{error}</div>}
        <header className="topbar">
          <div>
            <span className="eyebrow">EVIDENCE-FIRST MEMORY</span>
            <h1>{view[0].toUpperCase() + view.slice(1)}</h1>
          </div>
          <label className="import-button">
            <Upload size={16} />
            {importing ? "Indexing…" : "Import Markdown"}
            <input
              type="file"
              accept=".md,.txt,text/markdown,text/plain"
              disabled={importing}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void importFile(file);
              }}
            />
          </label>
        </header>
        {view === "search" && (
          <SearchView
            sources={sources}
            onEvidence={(item, sourceTitle) =>
              setEvidence({ item, sourceTitle })
            }
          />
        )}
        {view === "memories" && (
          <MemoryView
            memories={memories}
            onChanged={refresh}
            onEvidence={(item, sourceTitle) =>
              setEvidence({ item, sourceTitle })
            }
          />
        )}
        {view === "sources" && (
          <SourcesView
            sources={sources}
            jobs={jobs}
            onChanged={refresh}
            onSourceDeleted={(sourceId) =>
              setEvidence((current) =>
                current?.item.source_id === sourceId ? null : current,
              )
            }
          />
        )}
        {view === "model runs" && <ModelRunsView />}
        {view === "settings" && <SettingsView />}
      </main>
      {evidence && (
        <EvidenceDrawer {...evidence} onClose={() => setEvidence(null)} />
      )}
    </div>
  );
}

function Nav({
  icon,
  active,
  onClick,
  count,
  children,
}: {
  icon: React.ReactNode;
  active: boolean;
  onClick: () => void;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <button
      className={active ? "nav-item active" : "nav-item"}
      onClick={onClick}
    >
      {icon}
      <span>{children}</span>
      {count !== undefined && <b>{count}</b>}
    </button>
  );
}

type RunLineage = {
  current: ModelRun;
  parent: ModelRun | null;
  children: ModelRun[];
};

export function SettingsView() {
  const [configuration, setConfiguration] =
    useState<ProviderConfiguration | null>(null);
  const [generation, setGeneration] = useState<ProviderStatus | null>(null);
  const [embedding, setEmbedding] = useState<ProviderStatus | null>(null);
  const [reranking, setReranking] = useState<ProviderStatus | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [embeddingApiKey, setEmbeddingApiKey] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const refreshProviders = useCallback(async () => {
    const [nextConfiguration, nextGeneration, nextEmbedding, nextReranking] =
      await Promise.all([
        api.providerConfiguration(),
        api.generationProviderStatus(),
        api.embeddingProviderStatus(),
        api.rerankingProviderStatus(),
      ]);
    setConfiguration(nextConfiguration);
    setGeneration(nextGeneration);
    setEmbedding(nextEmbedding);
    setReranking(nextReranking);
  }, []);
  useEffect(() => {
    void refreshProviders().catch((reason) =>
      setMessage(errorMessage(reason, "Provider settings unavailable")),
    );
  }, [refreshProviders]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!configuration) return;
    setBusy(true);
    setMessage("");
    try {
      await api.saveProviderConfiguration({
        ai_provider: configuration.ai_provider,
        ai_base_url: configuration.ai_base_url || null,
        ai_model: configuration.ai_model || null,
        ai_api_key: apiKey || undefined,
        embedding_provider: configuration.embedding_provider,
        embedding_base_url: configuration.embedding_base_url || null,
        embedding_model: configuration.embedding_model || null,
        embedding_api_key: embeddingApiKey || undefined,
        allow_remote_ai: configuration.allow_remote_ai,
      });
      setApiKey("");
      setEmbeddingApiKey("");
      await refreshProviders();
      setMessage(
        "Provider configuration saved and capability health refreshed.",
      );
    } catch (reason) {
      setMessage(errorMessage(reason, "Provider configuration failed"));
    } finally {
      setBusy(false);
    }
  }

  if (!configuration)
    return (
      <section className="content">
        <div role="status">Loading provider settings…</div>
        {message && <div className="integrity-error">{message}</div>}
      </section>
    );
  return (
    <section className="content">
      <div className="section-heading">
        <div>
          <span className="eyebrow">LOCAL PROVIDER CONTROL</span>
          <h2>Model providers</h2>
        </div>
        <span className="mode-badge">No automatic fallback</span>
      </div>
      <form
        className="model-run-filters"
        onSubmit={(event) => void save(event)}
      >
        <label>
          Generation provider
          <select
            value={configuration.ai_provider}
            onChange={(event) =>
              setConfiguration({
                ...configuration,
                ai_provider: event.target.value,
              })
            }
          >
            <option value="disabled">Disabled</option>
            <option value="qwen">Qwen</option>
            <option value="deepseek">DeepSeek</option>
            <option value="ollama">Ollama</option>
            <option value="vllm">vLLM</option>
            <option value="openai_compatible">OpenAI-compatible</option>
          </select>
        </label>
        <label>
          Generation base URL
          <input
            value={configuration.ai_base_url ?? ""}
            onChange={(event) =>
              setConfiguration({
                ...configuration,
                ai_base_url: event.target.value,
              })
            }
          />
        </label>
        <label>
          Generation model
          <input
            value={configuration.ai_model ?? ""}
            onChange={(event) =>
              setConfiguration({
                ...configuration,
                ai_model: event.target.value,
              })
            }
          />
        </label>
        <label>
          Generation API key
          <input
            type="password"
            value={apiKey}
            placeholder={
              configuration.ai_api_key_configured
                ? "Configured; leave blank to keep"
                : "Optional"
            }
            onChange={(event) => setApiKey(event.target.value)}
          />
        </label>
        <label>
          Embedding provider
          <select
            value={configuration.embedding_provider}
            onChange={(event) =>
              setConfiguration({
                ...configuration,
                embedding_provider: event.target.value,
              })
            }
          >
            <option value="disabled">Disabled</option>
            <option value="ollama">Ollama</option>
            <option value="vllm">vLLM</option>
            <option value="openai_compatible">OpenAI-compatible</option>
          </select>
        </label>
        <label>
          Embedding base URL
          <input
            value={configuration.embedding_base_url ?? ""}
            onChange={(event) =>
              setConfiguration({
                ...configuration,
                embedding_base_url: event.target.value,
              })
            }
          />
        </label>
        <label>
          Embedding model
          <input
            value={configuration.embedding_model ?? ""}
            onChange={(event) =>
              setConfiguration({
                ...configuration,
                embedding_model: event.target.value,
              })
            }
          />
        </label>
        <label>
          Embedding API key
          <input
            type="password"
            value={embeddingApiKey}
            placeholder={
              configuration.embedding_api_key_configured
                ? "Configured; leave blank to keep"
                : "Optional"
            }
            onChange={(event) => setEmbeddingApiKey(event.target.value)}
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={configuration.allow_remote_ai}
            onChange={(event) =>
              setConfiguration({
                ...configuration,
                allow_remote_ai: event.target.checked,
              })
            }
          />{" "}
          Allow explicit remote model egress
        </label>
        <button disabled={busy}>
          {busy ? "Saving…" : "Save and check health"}
        </button>
      </form>
      <div className="metrics">
        <Metric value={generation?.mode ?? "unchecked"} label="Generation" />
        <Metric value={embedding?.mode ?? "unchecked"} label="Embedding" />
        <Metric value={reranking?.mode ?? "unchecked"} label="Reranking" />
      </div>
      {(generation?.mode === "degraded" || embedding?.mode === "degraded") && (
        <div className="degraded-banner" role="status">
          Provider degraded. Deterministic ingestion and lexical retrieval
          remain available.
        </div>
      )}
      {message && <div role="status">{message}</div>}
    </section>
  );
}

export function ModelRunsView() {
  const [runs, setRuns] = useState<ModelRun[]>([]);
  const [status, setStatus] = useState("");
  const [operation, setOperation] = useState("");
  const [providerId, setProviderId] = useState("");
  const [parentRunId, setParentRunId] = useState("");
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [lineage, setLineage] = useState<RunLineage | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");

  const loadRuns = useCallback(async (filters: ModelRunFilters = {}) => {
    setLoading(true);
    setListError("");
    try {
      setRuns(await api.modelRuns({ ...filters, limit: 100 }));
    } catch (reason) {
      setListError(
        errorMessage(reason, "Model-run diagnostics are unavailable"),
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  async function openRun(runId: string) {
    setDetailLoading(true);
    setDetailError("");
    try {
      const current = await api.modelRun(runId);
      const [parent, children] = await Promise.all([
        current.parent_run_id
          ? api.modelRun(current.parent_run_id)
          : Promise.resolve(null),
        api.modelRuns({ parentRunId: current.id, limit: 100 }),
      ]);
      setLineage({ current, parent, children });
    } catch (reason) {
      setDetailError(errorMessage(reason, "Model-run detail is unavailable"));
    } finally {
      setDetailLoading(false);
    }
  }

  function applyFilters(event: React.FormEvent) {
    event.preventDefault();
    setLineage(null);
    void loadRuns({
      status: status.trim() || undefined,
      operation: operation.trim() || undefined,
      providerId: providerId.trim() || undefined,
      parentRunId: parentRunId.trim() || undefined,
    });
  }

  function clearFilters() {
    setStatus("");
    setOperation("");
    setProviderId("");
    setParentRunId("");
    setLineage(null);
    void loadRuns();
  }

  return (
    <section
      className="content model-runs-view"
      aria-labelledby="model-runs-heading"
    >
      <div className="section-heading">
        <div>
          <span className="eyebrow">SAFE MODEL DIAGNOSTICS</span>
          <h2 id="model-runs-heading">Model runs</h2>
        </div>
        <span className="mode-badge">Metadata only</span>
      </div>
      <p className="diagnostic-intro">
        Inspect provider, operation, validation, timing, and repair lineage.
        Source text, prompts, model output, and credentials are never displayed.
      </p>
      <form className="model-run-filters" onSubmit={applyFilters}>
        <label>
          Status
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="">Any status</option>
            <option value="running">Running</option>
            <option value="succeeded">Succeeded</option>
            <option value="failed">Failed</option>
          </select>
        </label>
        <label>
          Operation
          <input
            value={operation}
            onChange={(event) => setOperation(event.target.value)}
            placeholder="generate or embed"
          />
        </label>
        <label>
          Provider
          <input
            value={providerId}
            onChange={(event) => setProviderId(event.target.value)}
            placeholder="provider ID"
          />
        </label>
        <label>
          Parent run
          <input
            value={parentRunId}
            onChange={(event) => setParentRunId(event.target.value)}
            placeholder="parent run ID"
          />
        </label>
        <div>
          <button type="submit" disabled={loading}>
            Apply filters
          </button>
          <button type="button" onClick={clearFilters} disabled={loading}>
            Clear
          </button>
        </div>
      </form>
      {loading && (
        <div className="diagnostic-state" role="status">
          Loading safe model-run metadata…
        </div>
      )}
      {listError && (
        <div className="integrity-error" role="alert">
          {listError}
        </div>
      )}
      {!loading && !listError && runs.length === 0 && (
        <div className="empty-card" role="status">
          No model runs match these filters.
        </div>
      )}
      {!loading && !listError && runs.length > 0 && (
        <div className="model-run-layout">
          <div className="model-run-list" aria-label="Model runs">
            {runs.map((run) => (
              <button
                className={
                  lineage?.current.id === run.id
                    ? "model-run-row selected"
                    : "model-run-row"
                }
                key={run.id}
                onClick={() => void openRun(run.id)}
                aria-label={`Open model run ${run.id}`}
                aria-pressed={lineage?.current.id === run.id}
              >
                <span>
                  <strong>{run.operation}</strong>
                  <code>{run.id}</code>
                </span>
                <span>
                  {run.provider_id}
                  <small>{run.model_id}</small>
                </span>
                <span className={`run-status ${run.status}`}>{run.status}</span>
                <time dateTime={run.created_at}>
                  {formatRunTime(run.created_at)}
                </time>
              </button>
            ))}
          </div>
          <aside className="model-run-detail" aria-live="polite">
            {detailLoading && (
              <div className="diagnostic-state" role="status">
                Loading model-run detail and lineage…
              </div>
            )}
            {detailError && (
              <div className="integrity-error" role="alert">
                {detailError}
              </div>
            )}
            {!detailLoading && !detailError && !lineage && (
              <div className="diagnostic-state">
                Select a run to inspect safe details and repair lineage.
              </div>
            )}
            {!detailLoading && !detailError && lineage && (
              <ModelRunDetail lineage={lineage} onOpen={openRun} />
            )}
          </aside>
        </div>
      )}
    </section>
  );
}

function ModelRunDetail({
  lineage,
  onOpen,
}: {
  lineage: RunLineage;
  onOpen: (runId: string) => Promise<void>;
}) {
  const run = lineage.current;
  return (
    <article>
      <div className="decision-top">
        <span className={`run-status ${run.status}`}>{run.status}</span>
        <span>Attempt {run.attempt_number}</span>
      </div>
      <h3>
        {run.operation} · {run.provider_id}
      </h3>
      <code className="run-id">{run.id}</code>
      <dl className="run-metadata">
        <div>
          <dt>Model</dt>
          <dd>{run.model_id}</dd>
        </div>
        <div>
          <dt>Template</dt>
          <dd>{run.template_version}</dd>
        </div>
        <div>
          <dt>Validation</dt>
          <dd>{run.validation_status ?? "not recorded"}</dd>
        </div>
        <div>
          <dt>Latency</dt>
          <dd>
            {run.latency_ms === null ? "not recorded" : `${run.latency_ms} ms`}
          </dd>
        </div>
        <div>
          <dt>Prompt tokens</dt>
          <dd>{run.prompt_tokens ?? "not recorded"}</dd>
        </div>
        <div>
          <dt>Completion tokens</dt>
          <dd>{run.completion_tokens ?? "not recorded"}</dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>{formatRunTime(run.created_at)}</dd>
        </div>
        <div>
          <dt>Finished</dt>
          <dd>
            {run.finished_at ? formatRunTime(run.finished_at) : "not finished"}
          </dd>
        </div>
        <div>
          <dt>Error code</dt>
          <dd>{run.error_code ?? "none"}</dd>
        </div>
        <div>
          <dt>Repair reason</dt>
          <dd>{run.repair_reason ?? "none"}</dd>
        </div>
      </dl>
      <section className="run-lineage" aria-labelledby="run-lineage-heading">
        <h4 id="run-lineage-heading">Repair lineage</h4>
        {lineage.parent ? (
          <button onClick={() => void onOpen(lineage.parent!.id)}>
            <span>Parent</span>
            <code>{lineage.parent.id}</code>
            <small>
              {lineage.parent.status} · attempt {lineage.parent.attempt_number}
            </small>
          </button>
        ) : (
          <p>No parent repair run.</p>
        )}
        <div className="lineage-current">
          <span>Current</span>
          <code>{run.id}</code>
          <small>
            {run.status} · attempt {run.attempt_number}
          </small>
        </div>
        {lineage.children.length > 0 ? (
          lineage.children.map((child) => (
            <button key={child.id} onClick={() => void onOpen(child.id)}>
              <span>Child repair</span>
              <code>{child.id}</code>
              <small>
                {child.status} · attempt {child.attempt_number}
              </small>
            </button>
          ))
        ) : (
          <p>No child repair runs.</p>
        )}
      </section>
    </article>
  );
}

function formatRunTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "not recorded" : date.toLocaleString();
}

export function SearchView({
  onEvidence,
  sources = [],
}: {
  onEvidence: (item: Evidence, title: string) => void;
  sources?: Source[];
}) {
  const [query, setQuery] = useState("");
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([]);
  const [ingestedFrom, setIngestedFrom] = useState("");
  const [ingestedBefore, setIngestedBefore] = useState("");
  const [rerank, setRerank] = useState(false);
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [answer, setAnswer] = useState<GroundedAnswer | null>(null);
  const [searched, setSearched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [answerError, setAnswerError] = useState("");
  async function run(event: React.FormEvent) {
    event.preventDefault();
    if (query.trim().length < 2) return;
    const scope = buildSearchScope(
      selectedSourceIds,
      ingestedFrom,
      ingestedBefore,
    );
    if (rerank) scope.rerank = true;
    if (
      scope.ingestedFrom &&
      scope.ingestedBefore &&
      scope.ingestedFrom >= scope.ingestedBefore
    ) {
      setSearchError("Indexed from must be earlier than indexed before.");
      return;
    }
    setBusy(true);
    setSearchError("");
    setAnswerError("");
    setAnswer(null);
    setHits([]);
    setSearched(false);
    try {
      const searchRequest = api.search(query, scope).then(
        (nextHits) => {
          setHits(nextHits);
          setSearched(true);
        },
        (reason) => {
          setSearchError(errorMessage(reason, "Search failed"));
          setSearched(true);
        },
      );
      const answerRequest = api.answer(query, scope).then(
        (nextAnswer) => {
          setAnswer(nextAnswer);
          if (nextAnswer.status === "provider_unavailable") {
            setAnswerError(
              "Answer generation is unavailable. Showing raw retrieval results.",
            );
          }
        },
        (reason) => {
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
    onEvidence(
      {
        id: citation.evidence_id,
        source_id: citation.source_id,
        source_version_id: citation.source_version_id,
        quote: citation.content,
        start_offset: citation.start_offset,
        end_offset: citation.end_offset,
        start_line: citation.start_line,
        end_line: citation.end_line,
      },
      citation.source_title,
    );
  }
  const citationById = new Map(
    answer?.citations.map((citation) => [citation.evidence_id, citation]),
  );
  const unresolvedEvidenceIds = answer
    ? [
        ...new Set(
          answer.statements.flatMap((statement) => statement.evidence_ids),
        ),
      ].filter((evidenceId) => !citationById.has(evidenceId))
    : [];
  const integrityFailed = unresolvedEvidenceIds.length > 0;
  const contextBudgetExclusions = answer?.exclusions ?? [];
  const selectedSources = selectedSourceIds.flatMap((sourceId) => {
    const source = sources.find((item) => item.id === sourceId);
    return source ? [source] : [];
  });
  const hasActiveScope =
    selectedSources.length > 0 ||
    Boolean(ingestedFrom) ||
    Boolean(ingestedBefore) ||
    rerank;
  function toggleSource(sourceId: string) {
    setSelectedSourceIds((current) =>
      current.includes(sourceId)
        ? current.filter((item) => item !== sourceId)
        : [...current, sourceId],
    );
  }
  return (
    <section className="content search-view">
      <form className="search-box" onSubmit={run}>
        <FileSearch />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search why a system was built this way…"
          aria-label="Search engineering memory"
        />
        <button disabled={busy}>{busy ? "Searching" : "Search"}</button>
      </form>
      <details className="search-scope">
        <summary>
          Search scope
          {hasActiveScope
            ? ` · ${activeScopeCount(selectedSources.length, ingestedFrom, ingestedBefore)} active`
            : " · all indexed sources"}
        </summary>
        <div className="scope-controls">
          <fieldset>
            <legend>Indexed sources</legend>
            {sources.length === 0 ? (
              <p>No indexed sources are available.</p>
            ) : (
              <div className="source-scope-options">
                {sources.map((source) => (
                  <label key={source.id}>
                    <input
                      type="checkbox"
                      checked={selectedSourceIds.includes(source.id)}
                      onChange={() => toggleSource(source.id)}
                    />
                    <span>{source.title}</span>
                  </label>
                ))}
              </div>
            )}
          </fieldset>
          <fieldset className="time-scope">
            <legend>Ingestion / indexed time</legend>
            <label>
              Indexed from
              <input
                type="datetime-local"
                value={ingestedFrom}
                onChange={(event) => setIngestedFrom(event.target.value)}
              />
            </label>
            <label>
              Indexed before
              <input
                type="datetime-local"
                value={ingestedBefore}
                onChange={(event) => setIngestedBefore(event.target.value)}
              />
            </label>
            <small>
              This filters when a source version was indexed, not when its
              events or decisions occurred.
            </small>
          </fieldset>
          <label>
            <input
              type="checkbox"
              checked={rerank}
              onChange={(event) => setRerank(event.target.checked)}
            />
            Optional local reranking
          </label>
          <button
            type="button"
            disabled={!hasActiveScope}
            onClick={() => {
              setSelectedSourceIds([]);
              setIngestedFrom("");
              setIngestedBefore("");
              setRerank(false);
            }}
          >
            Clear scope
          </button>
        </div>
      </details>
      <div
        className={`scope-summary${hasActiveScope ? " active" : ""}`}
        aria-label="Active search scope"
      >
        <strong>{hasActiveScope ? "Scoped search" : "Workspace search"}</strong>
        <span>
          {selectedSources.length > 0
            ? selectedSources.map((source) => source.title).join(", ")
            : "All indexed sources"}
        </span>
        <span>{formatTimeScope(ingestedFrom, ingestedBefore)}</span>
      </div>
      {!searched && (
        <div className="hero-empty">
          <div className="line-art">↳</div>
          <h2>Follow every claim back to its source.</h2>
          <p>
            Search technical decisions, rationale, and implementation context.
            Proofline returns inspectable evidence—not an uncited answer.
          </p>
        </div>
      )}
      {answerError && (
        <div className="degraded-banner" role="status">
          {answerError}
        </div>
      )}
      {searchError && (
        <div className="error-banner inline-error" role="alert">
          {searchError}
        </div>
      )}
      {contextBudgetExclusions.length > 0 && (
        <div
          className="context-budget-notice"
          role="status"
          aria-label="Context budget notice"
        >
          <strong>
            {contextBudgetExclusions.length} retrieved{" "}
            {contextBudgetExclusions.length === 1 ? "span was" : "spans were"}{" "}
            excluded by the context budget.
          </strong>
          <span>
            Evidence IDs:{" "}
            {contextBudgetExclusions.map((exclusion) => (
              <code title={exclusion.evidence_id} key={exclusion.evidence_id}>
                {exclusion.evidence_id.slice(0, 8)}
              </code>
            ))}
          </span>
        </div>
      )}
      {answer && (
        <article className="result-card answer-card">
          <div className="decision-top">
            <span
              className={`mode-badge${integrityFailed ? " integrity-failed" : ""}`}
            >
              {integrityFailed
                ? "integrity failure"
                : answer.status.replaceAll("_", " ")}
            </span>
            {answer.model_run_id && (
              <span>Run {answer.model_run_id.slice(0, 8)}</span>
            )}
          </div>
          <h2>
            {integrityFailed
              ? "Answer citation integrity failed"
              : "Evidence-backed answer"}
          </h2>
          {integrityFailed && (
            <div className="integrity-error" role="alert">
              Citation integrity failed: {unresolvedEvidenceIds.length}{" "}
              referenced evidence{" "}
              {unresolvedEvidenceIds.length === 1 ? "ID is" : "IDs are"}{" "}
              unavailable.
            </div>
          )}
          {!integrityFailed && (
            <>
              <p>{answer.answer}</p>
              <div className="answer-statements">
                {answer.statements.map((statement, index) => {
                  const statementCitations = [
                    ...new Set(statement.evidence_ids),
                  ].flatMap((evidenceId) => {
                    const citation = citationById.get(evidenceId);
                    return citation ? [citation] : [];
                  });
                  return (
                    <article
                      className="answer-statement"
                      aria-label={`Answer statement: ${statement.kind}`}
                      key={`${statement.kind}-${index}`}
                    >
                      <div>
                        <span className={`statement-kind ${statement.kind}`}>
                          {statement.kind}
                        </span>
                        <span className="text-muted">
                          {statement.support_status ?? "supported"}
                        </span>
                        <p>{statement.text}</p>
                      </div>
                      {statementCitations.length > 0 && (
                        <footer>
                          {statementCitations.map((citation) => (
                            <button
                              key={citation.evidence_id}
                              onClick={() => openCitation(citation)}
                            >
                              {citation.source_title} · L{citation.start_line}–
                              {citation.end_line}
                            </button>
                          ))}
                        </footer>
                      )}
                    </article>
                  );
                })}
              </div>
            </>
          )}
        </article>
      )}
      {searched && (
        <div className="results">
          <div className="section-heading">
            <div>
              <span className="eyebrow">RAW RETRIEVAL</span>
              <h2>{hits.length} evidence matches</h2>
            </div>
            <span className="mode-badge">
              {hits.some((hit) => hit.retrieval_channels.includes("semantic"))
                ? "Hybrid · RRF"
                : "Lexical · FTS5"}
            </span>
          </div>
          {hits.length === 0 ? (
            <div className="empty-card">
              Insufficient evidence. Try another phrase or import a source.
            </div>
          ) : (
            hits.map((hit) => (
              <SearchHitCard
                hit={hit}
                onEvidence={onEvidence}
                key={hit.chunk_id}
              />
            ))
          )}
        </div>
      )}
    </section>
  );
}

function buildSearchScope(
  sourceIds: string[],
  ingestedFrom: string,
  ingestedBefore: string,
): SearchScope {
  return {
    sourceIds,
    ingestedFrom: localDateTimeToIso(ingestedFrom),
    ingestedBefore: localDateTimeToIso(ingestedBefore),
  };
}

function localDateTimeToIso(value: string): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

function activeScopeCount(
  sourceCount: number,
  ingestedFrom: string,
  ingestedBefore: string,
): number {
  return (
    sourceCount +
    Number(Boolean(ingestedFrom)) +
    Number(Boolean(ingestedBefore))
  );
}

function formatTimeScope(ingestedFrom: string, ingestedBefore: string): string {
  if (ingestedFrom && ingestedBefore)
    return `Indexed from ${ingestedFrom} until before ${ingestedBefore}`;
  if (ingestedFrom) return `Indexed from ${ingestedFrom}`;
  if (ingestedBefore) return `Indexed before ${ingestedBefore}`;
  return "Any ingestion time";
}

function SearchHitCard({
  hit,
  onEvidence,
}: {
  hit: SearchHit;
  onEvidence: (item: Evidence, title: string) => void;
}) {
  return (
    <article className="result-card">
      <div className="result-meta">
        <span>{hit.source_title}</span>
        <button
          onClick={() =>
            onEvidence(
              {
                id: hit.chunk_id,
                source_id: hit.source_id,
                source_version_id: hit.source_version_id,
                quote: hit.content,
                start_offset: hit.start_offset,
                end_offset: hit.end_offset,
                start_line: hit.start_line,
                end_line: hit.end_line,
              },
              hit.source_title,
            )
          }
        >
          Lines {hit.start_line}–{hit.end_line}
        </button>
      </div>
      <p>{hit.content}</p>
      <details className="retrieval-debug">
        <summary>Why this result?</summary>
        <dl>
          <div>
            <dt>Channels</dt>
            <dd>{hit.retrieval_channels.join(" + ")}</dd>
          </div>
          {hit.lexical_rank !== null && (
            <div>
              <dt>Lexical rank</dt>
              <dd>#{hit.lexical_rank}</dd>
            </div>
          )}
          {hit.semantic_rank !== null && (
            <div>
              <dt>Semantic rank</dt>
              <dd>#{hit.semantic_rank}</dd>
            </div>
          )}
          {hit.semantic_score !== null && (
            <div>
              <dt>Semantic score</dt>
              <dd>{hit.semantic_score.toFixed(4)}</dd>
            </div>
          )}
          {hit.fused_score !== null && (
            <div>
              <dt>RRF score</dt>
              <dd>{hit.fused_score.toFixed(4)}</dd>
            </div>
          )}
          <div>
            <dt>Source version</dt>
            <dd>
              <code title={hit.source_version_id}>
                {hit.source_version_id.slice(0, 8)}
              </code>
            </dd>
          </div>
          <div>
            <dt>Exact location</dt>
            <dd>
              Lines {hit.start_line}–{hit.end_line} · offsets {hit.start_offset}
              :{hit.end_offset}
            </dd>
          </div>
        </dl>
      </details>
    </article>
  );
}

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof Error && reason.message ? reason.message : fallback;
}

function latestJobs(jobs: IngestionJob[]): IngestionJob[] {
  const ordered = [...jobs].sort((left, right) =>
    right.updated_at.localeCompare(left.updated_at),
  );
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

const memoryKinds: MemoryKind[] = [
  "decision",
  "assumption",
  "constraint",
  "alternative",
];
const memoryStatuses = [
  "candidate",
  "active",
  "accepted",
  "rejected",
  "obsolete",
] as const;
type MemoryStatus = (typeof memoryStatuses)[number];

export function MemoryView({
  memories,
  onEvidence,
  onChanged,
}: {
  memories: Memory[];
  onEvidence: (item: Evidence, title: string) => void;
  onChanged: () => Promise<void>;
}) {
  const [kindFilter, setKindFilter] = useState<MemoryKind | "all">("all");
  const [statusFilter, setStatusFilter] = useState<MemoryStatus | "all">("all");
  const filtered = memories.filter(
    (memory) =>
      (kindFilter === "all" || memory.kind === kindFilter) &&
      (statusFilter === "all" || memory.status === statusFilter),
  );
  return (
    <section className="content">
      <div className="section-heading">
        <div>
          <span className="eyebrow">MEMORY REGISTRY</span>
          <h2>Reviewable engineering context</h2>
        </div>
        <span className="mode-badge">
          {filtered.length} of {memories.length}
        </span>
      </div>
      <div className="registry-filters">
        <fieldset>
          <legend>Kind</legend>
          <button
            aria-pressed={kindFilter === "all"}
            onClick={() => setKindFilter("all")}
          >
            All
          </button>
          {memoryKinds.map((kind) => (
            <button
              key={kind}
              aria-pressed={kindFilter === kind}
              onClick={() => setKindFilter(kind)}
            >
              {kind[0].toUpperCase() + kind.slice(1)}s
            </button>
          ))}
        </fieldset>
        <fieldset>
          <legend>Status</legend>
          <button
            aria-pressed={statusFilter === "all"}
            onClick={() => setStatusFilter("all")}
          >
            All
          </button>
          {memoryStatuses.map((status) => (
            <button
              key={status}
              aria-pressed={statusFilter === status}
              onClick={() => setStatusFilter(status)}
            >
              {status}
            </button>
          ))}
        </fieldset>
      </div>
      {filtered.length === 0 ? (
        <div className="empty-card">
          No memories match these filters. Import an ADR or change the selected
          kind and status.
        </div>
      ) : (
        <div className="decision-grid">
          {filtered.map((memory) => (
            <MemoryCard
              memory={memory}
              onEvidence={onEvidence}
              onChanged={onChanged}
              key={memory.id}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function MemoryCard({
  memory,
  onEvidence,
  onChanged,
}: {
  memory: Memory;
  onEvidence: (item: Evidence, title: string) => void;
  onChanged: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [statement, setStatement] = useState(memory.statement);
  const [rationale, setRationale] = useState(memory.rationale ?? "");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [timeline, setTimeline] = useState<DecisionTimeline | null>(null);
  const [timelineLoading, setTimelineLoading] = useState(false);
  async function toggleTimeline() {
    if (timeline) {
      setTimeline(null);
      return;
    }
    setTimelineLoading(true);
    try {
      setTimeline(await api.decisionTimeline(memory.id));
    } catch (reason) {
      setError(errorMessage(reason, "Decision timeline failed"));
    } finally {
      setTimelineLoading(false);
    }
  }
  function beginEdit() {
    setStatement(memory.statement);
    setRationale(memory.rationale ?? "");
    setError("");
    setEditing(true);
  }
  function cancelEdit() {
    if (pending) return;
    setStatement(memory.statement);
    setRationale(memory.rationale ?? "");
    setError("");
    setEditing(false);
  }
  function saveCorrection(event: React.FormEvent) {
    event.preventDefault();
    const normalizedStatement = statement.trim();
    if (!normalizedStatement) {
      setError("Statement is required.");
      return;
    }
    setPending(true);
    setError("");
    try {
      const update = api.updateMemory(memory.id, {
        statement: normalizedStatement,
        rationale: rationale.trim() || null,
      });
      void update
        .then(
          async () => {
            await onChanged();
            setEditing(false);
          },
          (reason) => {
            setError(errorMessage(reason, "Memory correction failed"));
          },
        )
        .catch((reason) => {
          setError(errorMessage(reason, "Memory correction failed"));
        })
        .finally(() => {
          setPending(false);
        });
    } catch (reason) {
      setError(errorMessage(reason, "Memory correction failed"));
      setPending(false);
    }
  }
  async function changeStatus(status: MemoryStatus) {
    if (status === memory.status || pending) return;
    setPending(true);
    setError("");
    try {
      await api.updateMemory(memory.id, { status });
      await onChanged();
    } catch (reason) {
      setError(errorMessage(reason, "Memory review failed"));
    } finally {
      setPending(false);
    }
  }
  return (
    <article
      className="decision-card memory-card"
      aria-label={`${memory.kind} memory: ${memory.statement}`}
    >
      <div className="decision-top">
        <span className="memory-labels">
          <span
            className={`memory-kind ${memory.kind}`}
            aria-label={`Memory kind: ${memory.kind}`}
          >
            {memory.kind}
          </span>
          <span className={`status ${memory.status}`}>{memory.status}</span>
        </span>
        <span>
          {Math.round(memory.confidence * 100)}% · {memory.extraction_method}
        </span>
      </div>
      {editing ? (
        <form
          className="memory-edit-form"
          aria-label={`Edit ${memory.kind} memory`}
          onSubmit={(event) => void saveCorrection(event)}
        >
          <label>
            Statement
            <textarea
              value={statement}
              aria-invalid={!statement.trim() && Boolean(error)}
              onChange={(event) => setStatement(event.target.value)}
            />
          </label>
          <label>
            Rationale
            <textarea
              value={rationale}
              onChange={(event) => setRationale(event.target.value)}
            />
          </label>
          <div className="edit-actions">
            <button type="button" disabled={pending} onClick={cancelEdit}>
              Cancel
            </button>
            <button type="submit" disabled={pending}>
              {pending ? "Saving…" : "Save correction"}
            </button>
          </div>
        </form>
      ) : (
        <>
          <h3>{memory.statement}</h3>
          {memory.rationale && <p>{memory.rationale}</p>}
        </>
      )}
      {memory.kind === "decision" && (
        <div className="decision-timeline-controls">
          <button
            type="button"
            disabled={timelineLoading}
            onClick={() => void toggleTimeline()}
          >
            {timelineLoading
              ? "Loading timeline…"
              : timeline
                ? "Hide timeline"
                : "View timeline"}
          </button>
          {timeline && (
            <div
              className="decision-timeline"
              aria-label={`Timeline for ${memory.statement}`}
            >
              <span>
                Valid {timeline.decision.valid_from ?? "from ingestion"} →{" "}
                {timeline.decision.valid_to ?? "current"}
              </span>
              {[...timeline.incoming, ...timeline.outgoing].map((relation) => (
                <small key={relation.id}>
                  {relation.kind} · {relation.valid_from ?? relation.created_at}
                </small>
              ))}
            </div>
          )}
        </div>
      )}
      <div className="governance-actions">
        <label>
          Status
          <select
            aria-label={`Status for ${memory.kind}: ${memory.statement}`}
            value={memory.status}
            disabled={pending || editing}
            onChange={(event) =>
              void changeStatus(event.target.value as MemoryStatus)
            }
          >
            {memoryStatuses.map((status) => (
              <option value={status} key={status}>
                {status}
              </option>
            ))}
          </select>
        </label>
        <button
          disabled={pending || editing}
          onClick={beginEdit}
          aria-label={`Edit ${memory.kind}: ${memory.statement}`}
        >
          Edit
        </button>
      </div>
      {error && (
        <div className="action-error" role="alert">
          {error}
        </div>
      )}
      <footer>
        <span>{memory.source_title}</span>
        {memory.evidence.map((item) => (
          <button
            key={item.id}
            onClick={() => onEvidence(item, memory.source_title)}
          >
            View proof · L{item.start_line}–{item.end_line}
          </button>
        ))}
      </footer>
    </article>
  );
}

export function SourcesView({
  sources,
  jobs,
  onChanged,
  onSourceDeleted,
}: {
  sources: Source[];
  jobs: IngestionJob[];
  onChanged: () => Promise<void>;
  onSourceDeleted?: (sourceId: string) => void;
}) {
  const [extractingSourceId, setExtractingSourceId] = useState<string | null>(
    null,
  );
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [extractionErrors, setExtractionErrors] = useState<
    Record<string, string>
  >({});
  const [retryErrors, setRetryErrors] = useState<Record<string, string>>({});
  const [deletion, setDeletion] = useState<DeletionState | null>(null);
  const deleteTriggerRef = useRef<HTMLElement | null>(null);
  const jobsBySource = new Map(
    latestJobs(jobs).flatMap((job) =>
      job.source_id ? [[job.source_id, job] as const] : [],
    ),
  );
  const orphanFailures = [...jobs]
    .filter(
      (job) => !job.source_id && ["failed", "dead_letter"].includes(job.state),
    )
    .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
    .slice(0, 5);
  async function extract(sourceId: string) {
    setExtractingSourceId(sourceId);
    setExtractionErrors((current) => ({ ...current, [sourceId]: "" }));
    try {
      await api.extractMemories(sourceId);
      await onChanged();
    } catch (reason) {
      setExtractionErrors((current) => ({
        ...current,
        [sourceId]: errorMessage(reason, "AI memory extraction failed"),
      }));
    } finally {
      setExtractingSourceId(null);
    }
  }
  async function retry(job: IngestionJob) {
    setRetryingJobId(job.id);
    setRetryErrors((current) => ({ ...current, [job.id]: "" }));
    try {
      await api.retryJob(job.id);
      await onChanged();
    } catch (reason) {
      setRetryErrors((current) => ({
        ...current,
        [job.id]: errorMessage(reason, "Ingestion retry failed"),
      }));
    } finally {
      setRetryingJobId(null);
    }
  }
  async function openDeletion(source: Source) {
    deleteTriggerRef.current = document.activeElement as HTMLElement | null;
    setDeletion({
      source,
      impact: null,
      loading: true,
      pending: false,
      error: "",
    });
    try {
      const impact = await api.deletionImpact(source.id);
      setDeletion((current) =>
        current?.source.id === source.id
          ? { ...current, impact, loading: false }
          : current,
      );
    } catch (reason) {
      setDeletion((current) =>
        current?.source.id === source.id
          ? {
              ...current,
              loading: false,
              error: errorMessage(reason, "Deletion preview failed"),
            }
          : current,
      );
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
    setDeletion((current) =>
      current ? { ...current, pending: true, error: "" } : current,
    );
    try {
      await api.deleteSource(sourceId);
      onSourceDeleted?.(sourceId);
      await onChanged();
      const trigger = deleteTriggerRef.current;
      setDeletion(null);
      queueMicrotask(() => trigger?.focus());
    } catch (reason) {
      setDeletion((current) =>
        current?.source.id === sourceId
          ? {
              ...current,
              pending: false,
              error: errorMessage(reason, "Source deletion failed"),
            }
          : current,
      );
    }
  }
  return (
    <section className="content">
      <div className="metrics">
        <Metric value={sources.length} label="Sources detected" />
        <Metric
          value={sources.reduce((n, s) => n + s.chunk_count, 0)}
          label="Searchable chunks"
        />
        <Metric
          value={sources.reduce((n, s) => n + s.memory_count, 0)}
          label="Memories found"
        />
      </div>
      {orphanFailures.length > 0 && (
        <section
          className="recent-failures"
          aria-labelledby="recent-ingestion-failures"
        >
          <div className="section-heading">
            <div>
              <span className="eyebrow">PIPELINE DIAGNOSTICS</span>
              <h2 id="recent-ingestion-failures">Recent ingestion failures</h2>
            </div>
            <span className="mode-badge">{orphanFailures.length} orphaned</span>
          </div>
          <div className="failure-list">
            {orphanFailures.map((job) => (
              <article className={`failure-card ${job.state}`} key={job.id}>
                <div className="failure-summary">
                  <strong>Job {job.id.slice(0, 8)}</strong>
                  <span>
                    {job.state} · {job.stage}
                  </span>
                </div>
                <div className="failure-metadata">
                  <span>
                    Attempt {job.attempts}/{job.max_attempts}
                  </span>
                  <span>Started {job.started_at ?? "not recorded"}</span>
                  <span>Finished {job.finished_at ?? "not recorded"}</span>
                </div>
                {job.error_code && <code>{job.error_code}</code>}
                {job.error_detail && <p>{job.error_detail}</p>}
                {job.state === "failed" && job.retryable && (
                  <button
                    disabled={retryingJobId === job.id}
                    onClick={() => void retry(job)}
                    aria-label={`Retry ingestion job ${job.id.slice(0, 8)}`}
                  >
                    {retryingJobId === job.id ? "Retrying…" : "Retry"}
                  </button>
                )}
                {retryErrors[job.id] && (
                  <small className="action-error" role="alert">
                    {retryErrors[job.id]}
                  </small>
                )}
              </article>
            ))}
          </div>
        </section>
      )}
      <div className="source-table source-diagnostics">
        <div className="table-row table-head">
          <span>Source</span>
          <span>Type</span>
          <span>Objects</span>
          <span>Health</span>
          <span>Actions</span>
        </div>
        {sources.map((source) => {
          const job = jobsBySource.get(source.id);
          const extractionError = extractionErrors[source.id];
          return (
            <div className="table-row" key={source.id}>
              <span>
                <strong>{source.title}</strong>
                <small>{source.uri ?? "Local import"}</small>
              </span>
              <span>{source.kind}</span>
              <span>
                {source.chunk_count} chunks · {source.memory_count} memories
              </span>
              <span className={`job-health ${job?.state ?? source.status}`}>
                <strong>
                  {job ? `${job.state} · ${job.stage}` : source.status}
                </strong>
                <small>
                  {job
                    ? `Attempt ${job.attempts}/${job.max_attempts} · ${job.retryable ? "Retryable" : "Not retryable"}`
                    : "No ingestion job recorded"}
                </small>
                {job?.error_code && (
                  <small className="job-error-code">{job.error_code}</small>
                )}
                {job?.error_detail && (
                  <small className="job-error-detail">{job.error_detail}</small>
                )}
              </span>
              <span className="source-actions">
                {job?.state === "failed" && job.retryable && (
                  <button
                    disabled={retryingJobId === job.id}
                    onClick={() => void retry(job)}
                    aria-label={`Retry ingestion for ${source.title}`}
                  >
                    {retryingJobId === job.id ? "Retrying…" : "Retry ingestion"}
                  </button>
                )}
                <button
                  disabled={
                    extractingSourceId === source.id ||
                    retryingJobId === job?.id
                  }
                  onClick={() => void extract(source.id)}
                  aria-label={`Extract AI memories from ${source.title}`}
                >
                  {extractingSourceId === source.id
                    ? "Extracting…"
                    : "Extract AI memories"}
                </button>
                <button
                  className="danger-action"
                  onClick={() => void openDeletion(source)}
                  aria-label={`Delete ${source.title}`}
                >
                  Delete
                </button>
                {job && retryErrors[job.id] && (
                  <small className="action-error" role="alert">
                    {retryErrors[job.id]}
                  </small>
                )}
                {extractionError && (
                  <small className="action-error" role="alert">
                    {extractionError}
                  </small>
                )}
              </span>
            </div>
          );
        })}
      </div>
      {deletion && (
        <DeletionDialog
          state={deletion}
          onCancel={closeDeletion}
          onConfirm={() => void confirmDeletion()}
        />
      )}
    </section>
  );
}

function DeletionDialog({
  state,
  onCancel,
  onConfirm,
}: {
  state: DeletionState;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!state.pending) cancelRef.current?.focus();
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !state.pending) onCancel();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onCancel, state.pending]);
  const impactCounts = state.impact
    ? ([
        ["Versions", state.impact.versions],
        ["Chunks", state.impact.chunks],
        ["Embeddings", state.impact.embeddings],
        ["Vector index rows", state.impact.vector_index_rows ?? 0],
        ["Memories", state.impact.memories],
        ["Decisions", state.impact.decisions],
        ["Evidence", state.impact.evidence],
        ["Decision relations", state.impact.decision_relations ?? 0],
        ["Jobs detached", state.impact.ingestion_jobs_to_detach],
        ["Audit events", state.impact.audit_events_to_delete],
        ["FTS rows", state.impact.fts_rows],
      ] as const)
    : [];
  return (
    <div className="dialog-backdrop">
      <section
        className="deletion-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="deletion-dialog-title"
      >
        <span className="eyebrow">DELETION IMPACT</span>
        <h2 id="deletion-dialog-title">Delete {state.source.title}?</h2>
        <p>This permanently removes the source and its derived local data.</p>
        {state.loading && <div role="status">Loading deletion impact…</div>}
        {state.error && (
          <div className="integrity-error" role="alert">
            {state.error}
          </div>
        )}
        {state.impact && (
          <>
            <div className="deletion-identity">
              <span>Current version</span>
              <code>{state.impact.current_version_id ?? "none"}</code>
            </div>
            <dl className="impact-counts">
              {impactCounts.map(([label, count]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{count}</dd>
                </div>
              ))}
            </dl>
          </>
        )}
        <footer>
          <button ref={cancelRef} disabled={state.pending} onClick={onCancel}>
            Cancel
          </button>
          <button
            className="confirm-delete"
            disabled={!state.impact || state.pending}
            onClick={onConfirm}
          >
            {state.pending ? "Deleting…" : "Delete permanently"}
          </button>
        </footer>
      </section>
    </div>
  );
}

function Metric({ value, label }: { value: number | string; label: string }) {
  return (
    <div className="metric">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function EvidenceDrawer({
  item,
  sourceTitle,
  onClose,
}: {
  item: Evidence;
  sourceTitle: string;
  onClose: () => void;
}) {
  const [sourceContent, setSourceContent] = useState("");
  useEffect(() => {
    void api
      .sourceVersion(item.source_id, item.source_version_id)
      .then((version) => setSourceContent(version.content));
  }, [item.source_id, item.source_version_id]);
  const quote =
    item.quote || sourceContent.slice(item.start_offset, item.end_offset);
  return (
    <aside className="drawer">
      <header>
        <div>
          <span className="eyebrow">EXACT EVIDENCE</span>
          <h2>{sourceTitle}</h2>
        </div>
        <button aria-label="Close evidence" onClick={onClose}>
          <X />
        </button>
      </header>
      <div className="locator">
        Lines {item.start_line}–{item.end_line} <span>·</span> offsets{" "}
        {item.start_offset}:{item.end_offset}
      </div>
      <blockquote>{quote}</blockquote>
      <div className="integrity">
        <Database size={16} />
        <span>
          <strong>Source-backed span</strong>This quote is stored with its exact
          source offsets.
        </span>
      </div>
    </aside>
  );
}
