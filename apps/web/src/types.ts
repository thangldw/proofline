export type Overview = {
  sources: number;
  chunks: number;
  decisions: number;
  memories: number;
  evidence: number;
};

export type SearchScope = {
  sourceIds: string[];
  ingestedFrom: string | null;
  ingestedBefore: string | null;
};

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
  memory_count: number;
  git_repository_id?: string | null;
  git_commit_sha?: string | null;
  git_path?: string | null;
};

export type SourceDeletionImpact = {
  source_id: string;
  title: string;
  current_version_id: string | null;
  versions: number;
  chunks: number;
  embeddings: number;
  decisions: number;
  memories: number;
  evidence: number;
  decision_relations?: number;
  ingestion_jobs_to_detach: number;
  audit_events_to_delete: number;
  fts_rows: number;
};

export type IngestionJob = {
  id: string;
  source_id: string | null;
  source_version_id: string | null;
  kind: string;
  state: string;
  stage: string;
  attempts: number;
  request_hash: string | null;
  max_attempts: number;
  error_code: string | null;
  error_detail: string | null;
  retryable: boolean;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
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

export type MemoryKind =
  | "decision"
  | "assumption"
  | "constraint"
  | "alternative";

export type Memory = {
  id: string;
  source_id: string;
  source_version_id: string;
  source_title: string;
  kind: MemoryKind;
  title: string;
  statement: string;
  rationale: string | null;
  status: string;
  confidence: number;
  extraction_method: string;
  model_run_id: string | null;
  valid_from: string | null;
  valid_to: string | null;
  created_at: string;
  updated_at: string;
  evidence: Evidence[];
};

export type Decision = Memory;

export type DecisionRelation = {
  id: string;
  source_decision_id: string;
  target_decision_id: string;
  kind: "supersedes" | "implements" | "contradicts" | "based_on" | "considered";
  valid_from: string | null;
  valid_to: string | null;
  created_by: string;
  created_at: string;
};

export type DecisionTimeline = {
  decision: Decision;
  incoming: DecisionRelation[];
  outgoing: DecisionRelation[];
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
  source_kind?: string | null;
  git_commit_sha?: string | null;
  git_path?: string | null;
  temporal_priority?: "current_decision" | "neutral";
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
  source_kind?: string | null;
  git_commit_sha?: string | null;
  git_path?: string | null;
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
  exclusions?: Array<{
    evidence_id: string;
    reason: "context_budget";
  }>;
};

export type ModelRun = {
  id: string;
  provider_id: string;
  model_id: string;
  operation: string;
  template_version: string;
  input_hashes: string[];
  parent_run_id: string | null;
  attempt_number: number;
  repair_reason: string | null;
  status: string;
  validation_status: string | null;
  latency_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  error_code: string | null;
  created_at: string;
  finished_at: string | null;
};

export type ModelRunFilters = {
  status?: string;
  operation?: string;
  providerId?: string;
  parentRunId?: string;
  limit?: number;
};

export type ProviderStatus = {
  configured: boolean;
  provider_id: string | null;
  model_id: string | null;
  generation: boolean;
  structured_output: boolean;
  embedding: boolean;
  reranking: boolean;
  remote_egress_allowed: boolean;
  healthy: boolean | null;
  error_code: string | null;
  mode: "ready" | "degraded" | "disabled" | "unchecked";
};

export type ProviderConfiguration = {
  ai_provider: string;
  ai_base_url: string | null;
  ai_model: string | null;
  ai_api_key_configured: boolean;
  embedding_provider: string;
  embedding_base_url: string | null;
  embedding_model: string | null;
  embedding_api_key_configured: boolean;
  allow_remote_ai: boolean;
};
