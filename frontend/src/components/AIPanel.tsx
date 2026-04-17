import axios from "axios";
import { useEffect, useState } from "react";
import type { Editor } from "@tiptap/react";
import api from "../api/client";
import { useToast } from "./Toast";
import type { AISuggestion, EditorSelectionRange } from "../types";

interface Selection {
  selectedText: string;
  range: EditorSelectionRange;
}

export interface UndoRequest {
  originalText: string;
  appliedText: string;
  selection: EditorSelectionRange | null;
}

interface Props {
  documentId: string;
  editor: Editor | null;
  getSelection: () => Selection | null;
  onApply: (newText: string, selection?: EditorSelectionRange) => { ok: boolean; error?: string };
  onUndo: (req: UndoRequest) => { ok: boolean; error?: string };
}

const ACTIONS = ["rewrite", "summarize", "translate", "restructure"] as const;

const ACTION_ICONS: Record<string, string> = {
  rewrite: "Rewrite",
  summarize: "Summarize",
  translate: "Translate",
  restructure: "Restructure",
};

type ViewMode = "diff" | "side" | "edit";

interface DiffToken {
  type: "eq" | "add" | "del";
  text: string;
}

function wordDiff(a: string, b: string): DiffToken[] {
  const tokenize = (s: string) => s.split(/(\s+)/).filter((x) => x.length > 0);
  const aw = tokenize(a);
  const bw = tokenize(b);
  const n = aw.length;
  const m = bw.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = 1; i <= n; i++) {
    for (let j = 1; j <= m; j++) {
      dp[i][j] = aw[i - 1] === bw[j - 1]
        ? dp[i - 1][j - 1] + 1
        : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }
  const out: DiffToken[] = [];
  let i = n;
  let j = m;
  while (i > 0 && j > 0) {
    if (aw[i - 1] === bw[j - 1]) {
      out.unshift({ type: "eq", text: aw[i - 1] });
      i--; j--;
    } else if (dp[i - 1][j] >= dp[i][j - 1]) {
      out.unshift({ type: "del", text: aw[i - 1] });
      i--;
    } else {
      out.unshift({ type: "add", text: bw[j - 1] });
      j--;
    }
  }
  while (i > 0) { out.unshift({ type: "del", text: aw[--i] }); }
  while (j > 0) { out.unshift({ type: "add", text: bw[--j] }); }
  return out;
}

interface AppliedRecord {
  originalText: string;
  appliedText: string;
  selection: EditorSelectionRange | null;
}

export default function AIPanel({ documentId, editor, getSelection, onApply, onUndo }: Props) {
  const { toast } = useToast();
  const [action, setAction] = useState<string>("rewrite");
  const [targetLang, setTargetLang] = useState("Chinese");
  const [loading, setLoading] = useState(false);
  const [suggestion, setSuggestion] = useState<AISuggestion | null>(null);
  const [error, setError] = useState("");
  const [selRange, setSelRange] = useState<EditorSelectionRange | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("diff");
  const [editedSuggestion, setEditedSuggestion] = useState("");
  const [lastApplied, setLastApplied] = useState<AppliedRecord | null>(null);

  const [provider, setProvider] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const editorText = editor?.getText({ blockSeparator: "\n" }) ?? "";

  // Sync editedSuggestion with the latest suggestion text whenever a new one arrives.
  useEffect(() => {
    if (suggestion?.suggested_text != null) {
      setEditedSuggestion(suggestion.suggested_text);
      setViewMode("diff");
    }
  }, [suggestion?.suggestion_id, suggestion?.suggested_text]);

  const runAI = async () => {
    setLoading(true);
    setError("");
    setSuggestion(null);
    setLastApplied(null);

    const sel = getSelection();
    const inputText = sel ? sel.selectedText : (editor?.getText({ blockSeparator: "\n" }) ?? "");
    setSelRange(sel?.range ?? null);

    if (!inputText.trim()) {
      setError("No text to process. Write something or select text first.");
      setLoading(false);
      return;
    }

    try {
      const body: Record<string, unknown> = {
        action,
        scope: sel ? "selection" : "document",
        options: action === "translate" ? { target_language: targetLang } : {},
        selected_text: inputText,
      };
      if (sel) body.selection_range = sel.range;
      if (provider) body.provider = provider;
      if (apiKey) body.api_key = apiKey;
      if (baseUrl) body.base_url = baseUrl;

      const jobResp = await api.post(`/api/documents/${documentId}/ai-jobs`, body);
      const jobId = jobResp.data.job_id;
      const sugResp = await api.get(`/api/ai-jobs/${jobId}/suggestion`);
      setSuggestion(sugResp.data);
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail || "AI request failed");
      } else {
        setError("Unknown error");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleAccept = () => {
    if (!suggestion) return;
    const textToApply = editedSuggestion;
    if (!textToApply.trim()) {
      setError("Nothing to apply.");
      return;
    }
    const result = onApply(textToApply, selRange ?? undefined);
    if (!result.ok) {
      setError(result.error || "Unable to apply suggestion");
      return;
    }
    setLastApplied({
      originalText: suggestion.original_text ?? "",
      appliedText: textToApply,
      selection: selRange,
    });
    toast(editedSuggestion === suggestion.suggested_text ? "Suggestion applied" : "Edited suggestion applied", "success");
    setSuggestion(null);
    setSelRange(null);
    setError("");
  };

  const handleReject = () => {
    setSuggestion(null);
    setSelRange(null);
    setError("");
  };

  const handleUndo = () => {
    if (!lastApplied) return;
    const result = onUndo(lastApplied);
    if (!result.ok) {
      toast(result.error || "Unable to undo", "error");
      return;
    }
    toast("Suggestion reverted", "info");
    setLastApplied(null);
  };

  const original = suggestion?.original_text ?? "";
  const suggested = suggestion?.suggested_text ?? "";
  const diff = suggestion ? wordDiff(original, suggested) : [];

  return (
    <div className="ai-panel">
      <div className="ai-panel-header">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 2a4 4 0 0 1 4 4c0 1.1-.9 2-2 2h-4a2 2 0 0 1 0-4h4"/>
          <path d="M9 12h6"/>
          <path d="M9 16h6"/>
          <path d="M5 20h14a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2z"/>
        </svg>
        <h4>AI Assistant</h4>
      </div>

      {/* Persistent Undo banner — survives until next AI action or explicit dismiss */}
      {lastApplied && (
        <div className="ai-undo-banner">
          <span className="text-xs">Suggestion applied</span>
          <div className="ai-undo-actions">
            <button className="btn btn-sm" onClick={handleUndo}>Undo</button>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setLastApplied(null)}
              aria-label="Dismiss undo prompt"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div className="ai-actions">
        {ACTIONS.map((a) => (
          <button
            key={a}
            onClick={() => setAction(a)}
            className={`btn btn-sm ${action === a ? "btn-primary" : ""}`}
          >
            {ACTION_ICONS[a]}
          </button>
        ))}
      </div>

      {/* Translate language input */}
      {action === "translate" && (
        <div className="ai-translate-input">
          <label className="text-xs font-medium" style={{ color: "var(--text-h)" }}>
            Target Language
          </label>
          <input
            className="input"
            placeholder="e.g. Chinese, Spanish, French"
            value={targetLang}
            onChange={(e) => setTargetLang(e.target.value)}
          />
        </div>
      )}

      {/* Provider settings */}
      <button
        className="btn btn-ghost btn-sm ai-settings-toggle"
        onClick={() => setShowSettings(!showSettings)}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
        </svg>
        Provider Settings
      </button>

      {showSettings && (
        <div className="ai-settings">
          <select className="select" value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="">Default (Ollama)</option>
            <option value="openai">OpenAI</option>
            <option value="claude">Claude</option>
            <option value="ollama">Ollama</option>
          </select>
          <input
            className="input"
            placeholder="API Key"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
          <input
            className="input"
            placeholder="Base URL"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
          />
        </div>
      )}

      {/* Run button */}
      <button
        className="btn btn-primary ai-run-btn"
        onClick={runAI}
        disabled={loading || !editorText.trim()}
      >
        {loading ? (
          <>
            <span className="spinner" />
            Processing...
          </>
        ) : (
          `Run ${ACTION_ICONS[action]}`
        )}
      </button>

      <p className="text-xs text-muted ai-tip">
        Select text first, or run on the entire document.
      </p>

      {/* Error */}
      {error && <div className="alert alert-error">{error}</div>}

      {/* Suggestion */}
      {suggestion && (
        <div className="ai-suggestion">
          <div className="ai-suggestion-header">
            <h4>Suggestion</h4>
            <span className="badge badge-accent">
              {selRange ? "Selection" : "Full document"}
            </span>
          </div>

          {/* View mode toggle */}
          <div className="ai-view-tabs" role="tablist">
            <button
              role="tab"
              aria-selected={viewMode === "diff"}
              className={`ai-view-tab ${viewMode === "diff" ? "is-active" : ""}`}
              onClick={() => setViewMode("diff")}
            >
              Diff
            </button>
            <button
              role="tab"
              aria-selected={viewMode === "side"}
              className={`ai-view-tab ${viewMode === "side" ? "is-active" : ""}`}
              onClick={() => setViewMode("side")}
            >
              Side-by-side
            </button>
            <button
              role="tab"
              aria-selected={viewMode === "edit"}
              className={`ai-view-tab ${viewMode === "edit" ? "is-active" : ""}`}
              onClick={() => setViewMode("edit")}
            >
              Edit
            </button>
          </div>

          {/* Body */}
          {viewMode === "diff" && (
            <div className="ai-suggestion-text ai-diff">
              {diff.length === 0 ? (
                <span className="text-muted">No changes.</span>
              ) : (
                diff.map((tok, idx) => {
                  if (tok.type === "eq") return <span key={idx}>{tok.text}</span>;
                  if (tok.type === "del")
                    return (
                      <del key={idx} className="ai-diff-del">{tok.text}</del>
                    );
                  return (
                    <ins key={idx} className="ai-diff-add">{tok.text}</ins>
                  );
                })
              )}
            </div>
          )}

          {viewMode === "side" && (
            <div className="ai-side-by-side">
              <div className="ai-side-block">
                <div className="ai-side-label">Original</div>
                <div className="ai-side-text">{original || <span className="text-muted">(empty)</span>}</div>
              </div>
              <div className="ai-side-block">
                <div className="ai-side-label">Suggestion</div>
                <div className="ai-side-text">{suggested || <span className="text-muted">(empty)</span>}</div>
              </div>
            </div>
          )}

          {viewMode === "edit" && (
            <div className="ai-edit-wrap">
              <label className="ai-side-label" htmlFor="ai-edit-textarea">
                Suggestion (editable)
              </label>
              <textarea
                id="ai-edit-textarea"
                className="ai-edit-textarea"
                value={editedSuggestion}
                onChange={(e) => setEditedSuggestion(e.target.value)}
                rows={Math.min(20, Math.max(4, editedSuggestion.split("\n").length + 1))}
              />
              {editedSuggestion !== suggested && (
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => setEditedSuggestion(suggested)}
                >
                  Reset to AI suggestion
                </button>
              )}
            </div>
          )}

          <div className="ai-suggestion-actions">
            <button className="btn btn-primary btn-sm" onClick={handleAccept}>
              Accept{editedSuggestion !== suggested ? " edited" : ""}
            </button>
            <button className="btn btn-sm" onClick={handleReject}>
              Reject
            </button>
          </div>
        </div>
      )}

      <style>{`
        .ai-panel {
          background: var(--bg);
          border: 1px solid var(--border);
          border-radius: var(--radius-md);
          padding: var(--space-md);
          display: flex;
          flex-direction: column;
          gap: var(--space-md);
        }
        .ai-panel-header {
          display: flex;
          align-items: center;
          gap: var(--space-sm);
        }
        .ai-panel-header h4 {
          margin: 0;
        }
        .ai-actions {
          display: flex;
          gap: var(--space-xs);
          flex-wrap: wrap;
        }
        .ai-translate-input {
          display: flex;
          flex-direction: column;
          gap: var(--space-xs);
        }
        .ai-settings-toggle {
          justify-content: flex-start;
          padding-left: 0;
        }
        .ai-settings {
          display: flex;
          flex-direction: column;
          gap: var(--space-sm);
        }
        .ai-run-btn {
          width: 100%;
        }
        .ai-tip {
          text-align: center;
        }
        .ai-suggestion {
          background: var(--bg-secondary);
          border: 1px solid var(--border);
          border-radius: var(--radius);
          overflow: hidden;
        }
        .ai-suggestion-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: var(--space-sm) var(--space-md);
          border-bottom: 1px solid var(--border);
        }
        .ai-suggestion-header h4 {
          margin: 0;
          font-size: var(--font-sm);
        }
        .ai-view-tabs {
          display: flex;
          gap: 0;
          border-bottom: 1px solid var(--border);
        }
        .ai-view-tab {
          flex: 1;
          background: none;
          border: none;
          padding: 8px 6px;
          font-size: var(--font-xs);
          color: var(--text-muted);
          cursor: pointer;
          border-bottom: 2px solid transparent;
          transition: all var(--transition);
        }
        .ai-view-tab:hover {
          color: var(--text-h);
          background: var(--bg-tertiary);
        }
        .ai-view-tab.is-active {
          color: var(--accent);
          border-bottom-color: var(--accent);
          font-weight: 500;
        }
        .ai-suggestion-text {
          padding: var(--space-md);
          font-size: var(--font-sm);
          line-height: 1.6;
          white-space: pre-wrap;
          max-height: 300px;
          overflow-y: auto;
          color: var(--text-h);
        }
        .ai-diff-add {
          background: var(--color-success-bg);
          color: var(--color-success);
          text-decoration: none;
          padding: 1px 2px;
          border-radius: 2px;
        }
        .ai-diff-del {
          background: var(--color-error-bg);
          color: var(--color-error);
          text-decoration: line-through;
          padding: 1px 2px;
          border-radius: 2px;
        }
        .ai-side-by-side {
          display: flex;
          flex-direction: column;
          gap: var(--space-sm);
          padding: var(--space-md);
          max-height: 320px;
          overflow-y: auto;
        }
        .ai-side-block {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .ai-side-label {
          font-size: var(--font-xs);
          font-weight: 600;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }
        .ai-side-text {
          font-size: var(--font-sm);
          line-height: 1.55;
          white-space: pre-wrap;
          padding: var(--space-sm);
          background: var(--bg);
          border: 1px solid var(--border);
          border-radius: var(--radius-sm);
          color: var(--text-h);
        }
        .ai-edit-wrap {
          display: flex;
          flex-direction: column;
          gap: var(--space-xs);
          padding: var(--space-md);
        }
        .ai-edit-textarea {
          width: 100%;
          font-family: inherit;
          font-size: var(--font-sm);
          line-height: 1.55;
          padding: var(--space-sm);
          background: var(--bg);
          border: 1px solid var(--border);
          border-radius: var(--radius-sm);
          color: var(--text-h);
          resize: vertical;
          min-height: 100px;
        }
        .ai-edit-textarea:focus {
          outline: none;
          border-color: var(--accent);
        }
        .ai-suggestion-actions {
          display: flex;
          gap: var(--space-sm);
          padding: var(--space-sm) var(--space-md);
          border-top: 1px solid var(--border);
        }
        .ai-undo-banner {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: var(--space-sm);
          padding: var(--space-sm) var(--space-md);
          background: var(--color-info-bg);
          color: var(--color-info);
          border: 1px solid var(--color-info);
          border-radius: var(--radius-sm);
        }
        .ai-undo-actions {
          display: flex;
          gap: var(--space-xs);
        }
      `}</style>
    </div>
  );
}
