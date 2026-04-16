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
}

export interface AISuggestion {
  suggestion_id: string;
  original_text: string | null;
  suggested_text: string | null;
  diff_json: Record<string, unknown> | null;
  stale: boolean;
  disposition: string;
}
