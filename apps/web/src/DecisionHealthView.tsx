import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { DecisionReviewDetail } from "./DecisionReviewDetail";
import type {
  DecisionAnchorState,
  DecisionHealthOverview,
  DecisionImpact,
  DecisionImpactSummary,
  DecisionReview,
  DecisionReviewDetail as DecisionReviewDetailData,
  DecisionReviewFilters,
  DecisionReviewState,
} from "./types";
import "./decision-health.css";

type Props = {
  overview: DecisionHealthOverview;
  workspaceId: string;
  onOverviewChanged: () => Promise<void>;
};

function message(reason: unknown) {
  return reason instanceof Error ? reason.message : "Decision health unavailable";
}

function titleCase(value: string) {
  return `${value[0]?.toUpperCase() ?? ""}${value.slice(1)}`;
}

export function DecisionHealthView({ overview, workspaceId, onOverviewChanged }: Props) {
  const [reviews, setReviews] = useState<DecisionReview[]>([]);
  const [state, setState] = useState<DecisionReviewState | "">("");
  const [anchorState, setAnchorState] = useState<DecisionAnchorState | "">("");
  const [severity, setSeverity] = useState<"warning" | "error" | "">("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DecisionReviewDetailData | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [pending, setPending] = useState(false);
  const [impacts, setImpacts] = useState<DecisionImpact[]>([]);
  const [impactSummary, setImpactSummary] = useState<DecisionImpactSummary | null>(null);
  const [impactLoading, setImpactLoading] = useState(true);
  const [impactError, setImpactError] = useState("");

  const filters: DecisionReviewFilters = {
    ...(state ? { state } : {}),
    ...(anchorState ? { anchorState } : {}),
    ...(severity ? { severity } : {}),
    limit: 100,
  };

  const loadReviews = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    try {
      setReviews(await api.decisionReviews(filters));
      setError("");
    } catch (reason) {
      setError(message(reason));
    } finally {
      setLoading(false);
    }
  }, [workspaceId, state, anchorState, severity]);

  const loadImpacts = useCallback(async () => {
    if (!workspaceId) return;
    setImpactLoading(true);
    try {
      const [nextImpacts, nextSummary] = await Promise.all([
        api.decisionImpacts(),
        api.decisionImpactSummary(),
      ]);
      setImpacts(nextImpacts);
      setImpactSummary(nextSummary);
      setImpactError("");
    } catch (reason) {
      setImpactError(message(reason));
    } finally {
      setImpactLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    setSelectedId(null);
    setDetail(null);
    void loadReviews();
  }, [loadReviews, workspaceId]);

  useEffect(() => {
    void loadImpacts();
  }, [loadImpacts, workspaceId]);

  async function openReview(id: string) {
    setSelectedId(id);
    setDetail(null);
    setDetailLoading(true);
    setDetailError("");
    try {
      setDetail(await api.decisionReview(id));
    } catch (reason) {
      setDetailError(message(reason));
    } finally {
      setDetailLoading(false);
    }
  }

  async function afterMutation(id: string) {
    const [nextDetail] = await Promise.all([
      api.decisionReview(id),
      loadReviews(),
      loadImpacts(),
      onOverviewChanged(),
    ]);
    setDetail(nextDetail);
  }

  async function mutate(operation: () => Promise<unknown>) {
    if (!selectedId) return;
    setPending(true);
    setDetailError("");
    try {
      await operation();
      await afterMutation(selectedId);
    } catch (reason) {
      setDetailError(message(reason));
    } finally {
      setPending(false);
    }
  }

  async function refreshLedger() {
    setPending(true);
    try {
      await api.refreshDecisionReviews();
      await Promise.all([loadReviews(), loadImpacts(), onOverviewChanged()]);
      setError("");
    } catch (reason) {
      setError(message(reason));
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="content decision-health-view" aria-label="Decision health cockpit">
      <div className="decision-health-metrics" aria-label="Decision health metrics">
        <article><strong>{overview.healthy_accepted}</strong><span>Healthy accepted</span></article>
        <article className="attention"><strong>{overview.review_required}</strong><span>Review required</span></article>
        <article><strong>{overview.overdue}</strong><span>Overdue</span></article>
        <article><strong>{overview.waived}</strong><span>Waived</span></article>
        <article className={impacts.length ? "attention" : ""}>
          <strong>{impactSummary?.impacted_decision_count ?? 0}</strong>
          <span>Transitively impacted</span>
        </article>
        <article>
          <strong>{impactSummary?.max_depth ?? 0}</strong>
          <span>Maximum impact depth</span>
        </article>
      </div>

      <section className="decision-impact-panel" aria-labelledby="decision-impact-title">
        <header>
          <div>
            <span className="eyebrow">EXPLICIT DEPENDENCY GRAPH</span>
            <h2 id="decision-impact-title">Transitive impact paths</h2>
          </div>
          {impactSummary ? (
            <time dateTime={impactSummary.evaluated_at}>
              Evaluated {new Date(impactSummary.evaluated_at).toLocaleString()}
            </time>
          ) : null}
        </header>
        {impactLoading ? <p className="decision-impact-state">Loading transitive impacts…</p> : null}
        {impactError ? (
          <p role="alert" aria-label="Transitive impact error" className="decision-impact-state error">
            {impactError}
          </p>
        ) : null}
        {!impactLoading && !impactError && impacts.length === 0 ? (
          <p className="decision-impact-state">No transitive impacts.</p>
        ) : null}
        {!impactLoading && !impactError && impacts.length ? (
          <ol className="decision-impact-list">
            {impacts.map((impact) => (
              <li key={impact.fingerprint}>
                <div>
                  <strong>{impact.root_decision_title} → {impact.impacted_decision_title}</strong>
                  <span>Depth {impact.depth} · {impact.relation_kinds.join(" → ")}</span>
                </div>
                <code>{impact.decision_path.join(" → ")}</code>
              </li>
            ))}
          </ol>
        ) : null}
      </section>

      <div className="decision-health-toolbar">
        <div>
          <span className="eyebrow">REVIEW INBOX</span>
          <h2>Evidence drift requiring human judgment</h2>
          <p>Decision status remains unchanged until you resolve the evidence binding.</p>
        </div>
        <button type="button" disabled={pending} onClick={() => void refreshLedger()}>
          <RefreshCw size={15} /> Refresh ledger
        </button>
      </div>

      <div className="decision-health-filters" aria-label="Review filters">
        <label>
          Review state
          <select value={state} onChange={(event) => setState(event.target.value as DecisionReviewState | "")}>
            <option value="">All</option>
            {(["open", "acknowledged", "resolved", "waived", "superseded"] as const).map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>
        <label>
          Anchor state
          <select value={anchorState} onChange={(event) => setAnchorState(event.target.value as DecisionAnchorState | "")}>
            <option value="">All</option>
            {(["moved", "ambiguous", "changed", "deleted"] as const).map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>
        <label>
          Severity
          <select value={severity} onChange={(event) => setSeverity(event.target.value as "warning" | "error" | "")}>
            <option value="">All</option>
            <option value="warning">warning</option>
            <option value="error">error</option>
          </select>
        </label>
      </div>

      {loading ? <p role="status" className="decision-health-message">Loading decision reviews…</p> : null}
      {error ? <p role="alert" className="decision-health-message error">{error}</p> : null}
      {!loading && !error && reviews.length === 0 ? (
        <p role="status" className="decision-health-empty">No reviews match these filters.</p>
      ) : null}
      {!loading && !error && reviews.length ? (
        <div className="decision-health-table-wrap">
          <table className="decision-health-table">
            <thead><tr><th>Decision</th><th>Anchor</th><th>Severity</th><th>Opened</th><th aria-label="Action" /></tr></thead>
            <tbody>
              {reviews.map((review) => (
                <tr key={review.id}>
                  <td><strong>{titleCase(review.decision_status)} · review required</strong><small>{review.decision_id}</small></td>
                  <td><span className={`anchor-badge ${review.anchor_state}`}>{review.anchor_state}</span></td>
                  <td>{review.severity}</td>
                  <td><time dateTime={review.opened_at}>{new Date(review.opened_at).toLocaleDateString()}</time></td>
                  <td><button type="button" onClick={() => void openReview(review.id)} aria-label={`Open review ${review.id}`}>Review</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {selectedId && detailLoading ? <div className="decision-health-drawer" role="status">Loading review detail…</div> : null}
      {selectedId && !detailLoading && !detail && detailError ? (
        <aside className="decision-health-drawer" role="alert">{detailError}</aside>
      ) : null}
      {detail ? (
        <DecisionReviewDetail
          detail={detail}
          pending={pending}
          error={detailError}
          onClose={() => { setSelectedId(null); setDetail(null); }}
          onAcknowledge={() => mutate(() => api.updateDecisionReview(detail.review.id, { action: "acknowledge" }))}
          onWaive={(reason) => mutate(() => api.updateDecisionReview(detail.review.id, { action: "waive", reason }))}
          onReanchor={(reason) => {
            const candidate = detail.current.candidate;
            if (!candidate) return Promise.resolve();
            return mutate(() => api.reanchorDecisionReview(detail.review.id, {
              expected_current_source_version_id: detail.current.source_version_id,
              start_offset: candidate.start_offset,
              end_offset: candidate.end_offset,
              reason,
            }));
          }}
          onObsolete={() => mutate(() => api.resolveDecisionReview(detail.review.id, { action: "obsolete_decision", reason: "Decision no longer applies." }))}
          onSupersede={(replacementDecisionId, reason) => mutate(() => api.resolveDecisionReview(detail.review.id, { action: "supersede_decision", replacement_decision_id: replacementDecisionId, reason }))}
        />
      ) : null}
    </section>
  );
}
