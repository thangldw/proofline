export type Overview = { sources: number; chunks: number; decisions: number; evidence: number };

export type Source = {
  id: string;
  title: string;
  kind: string;
  uri: string | null;
  status: string;
  created_at: string;
  indexed_at: string;
  current_version_id: string | null;
  version_count: number;
  chunk_count: number;
  decision_count: number;
};

export type IngestionJob = {
  id: string;
  source_id: string | null;
  source_version_id: string | null;
  kind: string;
  state: string;
  stage: string;
  attempts: number;
  error_code: string | null;
  error_detail: string | null;
  retryable: boolean;
  created_at: string;
  updated_at: string;
};

export type Evidence = {
  id: string;
  source_id: string;
  source_version_id: string;
  quote: string;
  quote_hash?: string;
  start_offset: number;
  end_offset: number;
  start_line: number;
  end_line: number;
};

export type Decision = {
  id: string;
  source_id: string;
  source_version_id: string;
  source_title: string;
  title: string;
  statement: string;
  rationale: string | null;
  status: string;
  confidence: number;
  extraction_method: string;
  created_at: string;
  updated_at: string;
  evidence: Evidence[];
};

export type SearchHit = {
  chunk_id: string;
  source_id: string;
  source_version_id: string;
  source_title: string;
  content: string;
  start_offset: number;
  end_offset: number;
  start_line: number;
  end_line: number;
  rank: number;
  retrieval_channels: string[];
  lexical_rank: number | null;
  semantic_rank: number | null;
  semantic_score: number | null;
  fused_score: number | null;
};

export type AnswerCitation = {
  evidence_id: string;
  source_id: string;
  source_version_id: string;
  source_title: string;
  content: string;
  start_offset: number;
  end_offset: number;
  start_line: number;
  end_line: number;
};

export type GroundedAnswer = {
  status: "grounded" | "insufficient_evidence" | "provider_unavailable";
  answer: string;
  statements: Array<{
    text: string;
    kind: "direct" | "synthesis" | "inference";
    evidence_ids: string[];
  }>;
  citations: AnswerCitation[];
  model_run_id: string | null;
};
