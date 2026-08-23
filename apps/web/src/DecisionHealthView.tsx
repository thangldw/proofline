import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { DecisionReviewDetail } from "./DecisionReviewDetail";
import type {
  DecisionAnchorState,
  DecisionHealthOverview,
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

  useEffect(() => {
    setSelectedId(null);
    setDetail(null);
    void loadReviews();
  }, [loadReviews, workspaceId]);

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
      await Promise.all([loadReviews(), onOverviewChanged()]);
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
      </div>

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
