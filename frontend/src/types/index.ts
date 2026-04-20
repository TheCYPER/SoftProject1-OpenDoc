export interface User {
  user_id: string;
  email: string;
  display_name: string;
  created_at: string;
}

export interface ProseMirrorMark {
  type: string;
  attrs?: Record<string, unknown>;
}

export interface ProseMirrorNode {
  type: string;
  attrs?: Record<string, unknown>;
  text?: string;
  marks?: ProseMirrorMark[];
  content?: ProseMirrorNode[];
}

export interface ProseMirrorDoc {
  type: "doc";
  content: ProseMirrorNode[];
}

export interface EditorSelectionRange {
  from: number;
  to: number;
}

export interface TokenResponse {
  access_token: string;
  refresh_token?: string;
  token_type: string;
}

export interface Document {
  document_id: string;
  workspace_id: string;
  created_by: string;
  title: string;
  content: ProseMirrorDoc | null;
  content_format: string;
  current_revision_id: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  role?: string | null;
}

export interface DocumentListItem {
  document_id: string;
  title: string;
  status: string;
  updated_at: string;
  created_by: string;
}

export interface AIJobResponse {
  job_id: string;
  status: string;
  created_at: string;
  provider_name?: string | null;
  model_name?: string | null;
}

export interface AISuggestion {
  suggestion_id: string;
  original_text: string | null;
  suggested_text: string | null;
  diff_json: Record<string, unknown> | null;
  stale: boolean;
  disposition: string;
  partial_output_available?: boolean;
}

export type AIActionName = "rewrite" | "summarize" | "translate" | "restructure";
export type AIProviderName = "openai" | "groq" | "claude" | "ollama";

export interface AIHistoryItem {
  job_id: string;
  suggestion_id: string | null;
  action: AIActionName;
  scope: string;
  status: string;
  disposition: string | null;
  stale: boolean;
  original_text: string | null;
  suggested_text: string | null;
  partial_output_available: boolean;
  prompt_template_version: string | null;
  provider_name: string | null;
  model_name: string | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface AIHistoryResponse {
  items: AIHistoryItem[];
}

export interface AIJobCreatePayload {
  action: AIActionName;
  scope: "selection" | "document";
  selection_range?: EditorSelectionRange;
  selected_text: string;
  base_revision_id?: string | null;
  options?: Record<string, unknown>;
  provider?: AIProviderName;
  model?: string;
}

export interface AIStreamJobStartedEvent {
  job_id: string;
  suggestion_id: string;
  status: string;
  action: AIActionName;
  stale: boolean;
  provider_name: string | null;
  model_name: string | null;
  original_text: string;
}

export interface AIStreamTextDeltaEvent {
  job_id: string;
  suggestion_id: string;
  seq: number;
  delta: string;
}

export interface AIStreamTerminalEvent {
  job_id: string;
  suggestion_id: string;
  status: string;
  stale?: boolean;
  text?: string;
  code?: string;
  message?: string;
  partial_text?: string;
  partial_output_available?: boolean;
}
