import { X } from "lucide-react";
import { useState } from "react";
import type { DecisionReviewDetail as DecisionReviewDetailData } from "./types";

type Props = {
  detail: DecisionReviewDetailData;
  pending: boolean;
  error: string;
  onClose: () => void;
  onAcknowledge: () => Promise<void>;
  onWaive: (reason: string) => Promise<void>;
  onReanchor: (reason: string) => Promise<void>;
  onObsolete: () => Promise<void>;
  onSupersede: (replacementDecisionId: string, reason: string) => Promise<void>;
};

function shortHash(value: string) {
  return value.slice(0, 12);
}

export function DecisionReviewDetail({
  detail,
  pending,
  error,
  onClose,
  onAcknowledge,
  onWaive,
  onReanchor,
  onObsolete,
  onSupersede,
}: Props) {
  const [waiverReason, setWaiverReason] = useState("");
  const [reanchorReason, setReanchorReason] = useState("");
  const [replacementId, setReplacementId] = useState("");
  const [replacementReason, setReplacementReason] = useState("");
  const reviewRequired = ["open", "acknowledged"].includes(detail.review.state);
  const status = `${detail.decision.status[0]?.toUpperCase() ?? ""}${detail.decision.status.slice(1)}`;

  return (
    <aside
      className="decision-health-drawer"
      role="dialog"
      aria-modal="true"
      aria-label="Decision review detail"
    >
      <header>
        <div>
          <span className="eyebrow">DETERMINISTIC REVIEW</span>
          <h2>{detail.decision.title}</h2>
          <span className="decision-health-status">
            {status}
            {reviewRequired ? " · review required" : ` · ${detail.review.state}`}
          </span>
        </div>
        <button type="button" onClick={onClose} aria-label="Close review detail">
          <X size={19} />
        </button>
      </header>

      <p className="decision-health-statement">{detail.decision.statement}</p>
      <dl className="decision-health-facts">
        <div>
          <dt>Anchor</dt>
          <dd>{detail.review.anchor_state}</dd>
        </div>
        <div>
          <dt>Policy</dt>
          <dd>{detail.policy.blocking ? "Blocking" : "Advisory"}</dd>
        </div>
        <div>
          <dt>Fingerprint</dt>
          <dd title={detail.review.finding_fingerprint}>
            {shortHash(detail.review.finding_fingerprint)}
          </dd>
        </div>
      </dl>

      <section className="decision-health-evidence" aria-label="Cited evidence">
        <div>
          <span className="eyebrow">CITED VERSION</span>
          <strong>
            L{detail.cited.start_line}–{detail.cited.end_line} · {shortHash(detail.cited.content_sha256)}
          </strong>
        </div>
        <blockquote>{detail.cited.quote}</blockquote>
      </section>

      <section className="decision-health-evidence current" aria-label="Current candidate">
        <div>
          <span className="eyebrow">CURRENT VERSION</span>
          <strong>{shortHash(detail.current.content_sha256)}</strong>
        </div>
        {detail.current.candidate ? (
          <>
            <small>
              Suggested only · L{detail.current.candidate.start_line}–
              {detail.current.candidate.end_line}
            </small>
            <blockquote>{detail.current.candidate.quote}</blockquote>
          </>
        ) : (
          <p>No deterministic re-anchor candidate.</p>
        )}
      </section>

      {error ? <p className="decision-health-message error" role="alert">{error}</p> : null}

      {reviewRequired ? (
        <section className="decision-health-actions" aria-label="Review actions">
          <button
            className="primary-action"
            type="button"
            disabled={pending || detail.review.state !== "open"}
            onClick={() => void onAcknowledge()}
          >
            Acknowledge
          </button>
          <label>
            Waiver reason
            <textarea
              value={waiverReason}
              onChange={(event) => setWaiverReason(event.target.value)}
              rows={2}
            />
          </label>
          <button
            type="button"
            disabled={pending || !waiverReason.trim()}
            onClick={() => void onWaive(waiverReason.trim())}
          >
            Waive
          </button>
          {detail.current.candidate ? (
            <>
              <label>
                Re-anchor reason
                <textarea
                  value={reanchorReason}
                  onChange={(event) => setReanchorReason(event.target.value)}
                  rows={2}
                />
              </label>
              <button
                type="button"
                disabled={pending || !reanchorReason.trim()}
                onClick={() => {
                  if (window.confirm("Bind this decision to the exact current candidate span?")) {
                    void onReanchor(reanchorReason.trim());
                  }
                }}
              >
                Re-anchor candidate
              </button>
            </>
          ) : null}
          <button
            className="danger-action"
            type="button"
            disabled={pending}
            onClick={() => {
              if (window.confirm("Mark this accepted decision obsolete?")) void onObsolete();
            }}
          >
            Mark obsolete
          </button>
          <details>
            <summary>Supersede with another accepted decision</summary>
            <label>
              Replacement decision ID
              <input
                value={replacementId}
                onChange={(event) => setReplacementId(event.target.value)}
              />
            </label>
            <label>
              Supersede reason
              <textarea
                value={replacementReason}
                onChange={(event) => setReplacementReason(event.target.value)}
                rows={2}
              />
            </label>
            <button
              type="button"
              disabled={pending || !replacementId.trim() || !replacementReason.trim()}
              onClick={() => {
                if (window.confirm("Supersede this decision with the accepted replacement?")) {
                  void onSupersede(replacementId.trim(), replacementReason.trim());
                }
              }}
            >
              Supersede decision
            </button>
          </details>
        </section>
      ) : null}

      <section className="decision-health-audit" aria-label="Review audit timeline">
        <h3>Audit timeline</h3>
        <ol>
          {detail.audit_events.map((event) => (
            <li key={event.id}>
              <strong>{event.action.replaceAll("_", " ")}</strong>
              <span>{event.actor} · {new Date(event.created_at).toLocaleString()}</span>
            </li>
          ))}
        </ol>
      </section>
    </aside>
  );
}
