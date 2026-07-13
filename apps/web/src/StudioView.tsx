import { useEffect, useMemo, useState } from "react";
import {
  AudioLines,
  BarChart3,
  ChevronLeft,
  ChevronRight,
  FileText,
  Layers3,
  Network,
  Play,
  Presentation,
  SquareStack,
  Table2,
  Trash2,
  Video,
} from "lucide-react";
import { api } from "./api";
import type {
  Source,
  StudioArtifact,
  StudioCitation,
  StudioItem,
  StudioKind,
} from "./types";

const tools: Array<{
  kind: StudioKind;
  label: string;
  description: string;
  tone: string;
  icon: typeof AudioLines;
}> = [
  { kind: "audio_overview", label: "Audio overview", description: "Listen to a grounded narration", tone: "blue", icon: AudioLines },
  { kind: "presentation", label: "Presentation", description: "Turn evidence into slides", tone: "sand", icon: Presentation },
  { kind: "video_overview", label: "Video overview", description: "Preview an evidence storyboard", tone: "green", icon: Video },
  { kind: "mind_map", label: "Mind map", description: "Explore the source as branches", tone: "purple", icon: Network },
  { kind: "report", label: "Report", description: "Build a structured source brief", tone: "gold", icon: FileText },
  { kind: "flashcards", label: "Flashcards", description: "Review grounded concepts", tone: "coral", icon: Layers3 },
  { kind: "quiz", label: "Quiz", description: "Check source comprehension", tone: "cyan", icon: SquareStack },
  { kind: "infographic", label: "Infographic", description: "Scan key facts and metrics", tone: "magenta", icon: BarChart3 },
  { kind: "data_table", label: "Data table", description: "Inspect evidence row by row", tone: "indigo", icon: Table2 },
];

export function StudioView({
  artifacts,
  sources,
  onChanged,
}: {
  artifacts: StudioArtifact[];
  sources: Source[];
  onChanged: () => Promise<void>;
}) {
  const [sourceId, setSourceId] = useState(sources[0]?.id ?? "");
  const [selectedId, setSelectedId] = useState<string | null>(artifacts[0]?.id ?? null);
  const [busy, setBusy] = useState<StudioKind | null>(null);
  const [message, setMessage] = useState("");
  const selected = artifacts.find((artifact) => artifact.id === selectedId) ?? null;

  useEffect(() => {
    if (!sourceId && sources[0]) setSourceId(sources[0].id);
  }, [sourceId, sources]);

  useEffect(() => {
    if (selectedId && artifacts.some((artifact) => artifact.id === selectedId)) return;
    setSelectedId(artifacts[0]?.id ?? null);
  }, [artifacts, selectedId]);

  async function generate(kind: StudioKind) {
    if (!sourceId) return;
    setBusy(kind);
    setMessage("");
    try {
      const artifact = await api.createStudioArtifact(sourceId, kind);
      setSelectedId(artifact.id);
      setMessage(`${artifact.title} is ready with ${artifact.citations.length} exact citations.`);
      await onChanged();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Could not create Studio artifact");
    } finally {
      setBusy(null);
    }
  }

  async function remove(artifact: StudioArtifact) {
    await api.deleteStudioArtifact(artifact.id);
    setSelectedId(null);
    setMessage(`${artifact.title} deleted.`);
    await onChanged();
  }

  return (
    <section className="content studio-view" aria-label="Evidence-backed Studio">
      <div className="studio-intro">
        <div>
          <span className="eyebrow">EVIDENCE STUDIO</span>
          <h2>Turn sources into learning artifacts</h2>
          <p>Every generated section points to an immutable source version and exact source lines.</p>
        </div>
        <label className="studio-source" htmlFor="studio-source">
          Source
          <select id="studio-source" value={sourceId} onChange={(event) => setSourceId(event.target.value)}>
            {sources.map((source) => <option key={source.id} value={source.id}>{source.title}</option>)}
          </select>
        </label>
      </div>

      <div className="studio-grid">
        {tools.map(({ kind, label, description, tone, icon: Icon }) => (
          <button
            className={`studio-tool studio-tool-${tone}`}
            key={kind}
            type="button"
            disabled={!sourceId || busy !== null}
            onClick={() => void generate(kind)}
            aria-label={`Create ${label}`}
          >
            <span className="studio-tool-copy">
              <Icon size={23} strokeWidth={1.9} />
              <strong>{busy === kind ? "Creating…" : label}</strong>
              <small>{description}</small>
            </span>
            <span className="studio-tool-arrow" aria-hidden="true"><ChevronRight size={22} /></span>
          </button>
        ))}
      </div>

      {message && <p className="studio-message" role="status">{message}</p>}

      {artifacts.length > 0 && (
        <div className="studio-library" aria-label="Saved Studio artifacts">
          <span className="eyebrow">SAVED IN THIS WORKSPACE</span>
          <div>
            {artifacts.map((artifact) => (
              <button
                type="button"
                key={artifact.id}
                className={artifact.id === selectedId ? "active" : ""}
                onClick={() => setSelectedId(artifact.id)}
              >
                <strong>{artifact.title}</strong>
                <small>{artifact.citations.length} citations · {artifact.generation_method}</small>
              </button>
            ))}
          </div>
        </div>
      )}

      {selected && <ArtifactPreview artifact={selected} onDelete={() => void remove(selected)} />}
      {!selected && artifacts.length === 0 && (
        <div className="empty-card studio-empty">Choose a source and create your first Studio artifact.</div>
      )}
    </section>
  );
}

function ArtifactPreview({ artifact, onDelete }: { artifact: StudioArtifact; onDelete: () => void }) {
  const [active, setActive] = useState(0);
  const [citation, setCitation] = useState<StudioCitation | null>(null);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [revealed, setRevealed] = useState<Record<number, boolean>>({});
  const items = artifact.content.items;
  const paged = ["slides", "storyboard"].includes(artifact.content.format);
  const visibleItems = paged ? items.slice(active, active + 1) : items;

  useEffect(() => {
    setActive(0);
    setCitation(null);
    setAnswers({});
    setRevealed({});
  }, [artifact.id]);

  const narration = useMemo(
    () => [artifact.title, artifact.content.summary, ...items.map((item) => item.body)].join(". "),
    [artifact, items],
  );

  function cite(item: StudioItem) {
    setCitation(artifact.citations.find((candidate) => candidate.ordinal === item.citation) ?? null);
  }

  function speak() {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(narration));
  }

  return (
    <article className={`studio-preview studio-format-${artifact.content.format}`}>
      <header>
        <div>
          <span className="eyebrow">{artifact.kind.replaceAll("_", " ").toUpperCase()} · READY</span>
          <h2>{artifact.title}</h2>
          <p>{artifact.content.summary}</p>
        </div>
        <div className="studio-preview-actions">
          {artifact.kind === "audio_overview" && (
            <button type="button" onClick={speak}><Play size={15} /> Play narration</button>
          )}
          <button className="studio-delete" type="button" onClick={onDelete} aria-label={`Delete ${artifact.title}`}>
            <Trash2 size={16} />
          </button>
        </div>
      </header>

      {artifact.content.format === "table" ? (
        <div className="studio-data-table" role="table" aria-label={artifact.title}>
          <div className="studio-data-row studio-data-head" role="row">
            {artifact.content.columns?.map((column) => <strong role="columnheader" key={column}>{column}</strong>)}
          </div>
          {items.map((item) => (
            <button className="studio-data-row" role="row" type="button" key={item.citation} onClick={() => cite(item)}>
              {item.cells?.map((cell) => <span role="cell" key={cell}>{cell}</span>)}
            </button>
          ))}
        </div>
      ) : artifact.content.format === "branches" ? (
        <div className="mind-map-view">
          <strong>{artifact.source_title}</strong>
          <ul>{items.map((item) => <li key={item.citation}><button type="button" onClick={() => cite(item)}>{item.title}</button></li>)}</ul>
        </div>
      ) : (
        <div className="studio-preview-items">
          {visibleItems.map((item, index) => {
            const itemIndex = paged ? active : index;
            return (
              <section className="studio-preview-item" key={`${item.citation}-${item.title}`}>
                <span className="studio-item-number">{String(itemIndex + 1).padStart(2, "0")}</span>
                <h3>{item.title}</h3>
                {artifact.content.format === "quiz" && item.options ? (
                  <div className="quiz-options">
                    {item.options.map((option) => (
                      <button
                        type="button"
                        className={answers[itemIndex] === option ? "selected" : ""}
                        key={option}
                        onClick={() => setAnswers((current) => ({ ...current, [itemIndex]: option }))}
                      >
                        {option}
                      </button>
                    ))}
                    {answers[itemIndex] && <strong>{answers[itemIndex] === item.answer ? "Correct — supported by the cited span." : "Try again and inspect the evidence."}</strong>}
                  </div>
                ) : artifact.content.format === "flashcards" ? (
                  <button className="flashcard-answer" type="button" onClick={() => setRevealed((current) => ({ ...current, [itemIndex]: !current[itemIndex] }))}>
                    {revealed[itemIndex] ? item.answer : "Reveal grounded answer"}
                  </button>
                ) : (
                  <p>{item.body}</p>
                )}
                <button className="citation-link" type="button" onClick={() => cite(item)}>
                  Evidence {item.citation + 1}
                </button>
              </section>
            );
          })}
        </div>
      )}

      {paged && items.length > 1 && (
        <div className="studio-pager">
          <button type="button" aria-label="Previous item" disabled={active === 0} onClick={() => setActive((value) => value - 1)}><ChevronLeft size={18} /></button>
          <span>{active + 1} / {items.length}</span>
          <button type="button" aria-label="Next item" disabled={active === items.length - 1} onClick={() => setActive((value) => value + 1)}><ChevronRight size={18} /></button>
        </div>
      )}

      {citation && (
        <aside className="studio-citation" aria-label="Exact Studio evidence">
          <div>
            <span className="eyebrow">EXACT EVIDENCE · L{citation.start_line}–{citation.end_line}</span>
            <strong>{citation.source_title}</strong>
            <small>Immutable version {citation.source_version_id.slice(0, 8)}</small>
          </div>
          <blockquote>{citation.quote}</blockquote>
          <button type="button" onClick={() => setCitation(null)}>Close evidence</button>
        </aside>
      )}
    </article>
  );
}
