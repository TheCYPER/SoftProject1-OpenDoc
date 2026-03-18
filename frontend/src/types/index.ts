export interface User {
  user_id: string;
  email: string;
  display_name: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface Document {
  document_id: string;
  workspace_id: string;
  created_by: string;
  title: string;
  content: Record<string, unknown> | null;
  content_format: string;
  current_revision_id: string | null;
  status: string;
  created_at: string;
  updated_at: string;
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
