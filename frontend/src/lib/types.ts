export type SourceName = "tiktok" | "reddit" | "facebook" | "x";
export type ContextMode = "global" | "pairwise";
export type Status = "queued" | "running" | "succeeded" | "failed";
export type DataFormat = "csv" | "json" | "jsonl" | "text";
export type FileOrigin = "crawled" | "uploaded" | "edited" | "merged";
export type AnalysisKind = "number" | "text" | "boolean" | "mixed";

export interface ProviderInfo {
  key: SourceName;
  label: string;
  availability: "ready" | "connector_required";
  accepts: string;
  description: string;
}

export interface CrawlRequest {
  source: SourceName;
  target_url: string;
  max_comments: number;
  context_mode: ContextMode;
  metadata: Record<string, string>;
}

export interface LogEntry {
  timestamp: string;
  level: "info" | "warning" | "error";
  message: string;
}

export interface PipelineNode {
  id: string;
  label: string;
  status: Status | "pending";
  detail: string;
}

export interface JobRecord {
  id: string;
  status: Status;
  created_at: string;
  updated_at: string;
  finished_at?: string;
  retry_of?: string;
  request: CrawlRequest;
  nodes: PipelineNode[];
  logs: LogEntry[];
  record_count: number;
  output_files: string[];
  discovered_context: Record<string, unknown>;
  error?: string;
}

export interface WranglerFileRecord {
  id: string;
  name: string;
  format: DataFormat;
  origin: FileOrigin;
  job_id?: string | null;
  size: number;
  modified_at: string;
  relative_path: string;
}

export interface WranglerFileContent {
  file: WranglerFileRecord;
  content: string;
}

export interface AnalysisBucket {
  label: string;
  count: number;
}

export interface AnalysisField {
  name: string;
  kind: AnalysisKind;
  non_empty: number;
  missing: number;
  unique: number;
  minimum?: number | null;
  maximum?: number | null;
  average?: number | null;
  distribution: AnalysisBucket[];
}

export interface WranglerAnalysis {
  file: WranglerFileRecord;
  record_count: number;
  field_count: number;
  missing_values: number;
  numeric_fields: number;
  fields: AnalysisField[];
}
