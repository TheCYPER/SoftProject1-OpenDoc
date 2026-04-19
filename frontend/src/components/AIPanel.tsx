import { useEffect, useRef, useState } from "react";
import type { Editor } from "@tiptap/react";

import {
  applyAIJob,
  cancelAIJob,
  fetchAIHistory,
  rejectAIJob,
  streamAIJob,
} from "../api/ai";
import { useToast } from "./Toast";
import type {
  AIActionName,
  AIHistoryItem,
  AIProviderName,
  AISuggestion,
  EditorSelectionRange,
} from "../types";

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
  canEdit: boolean;
  baseRevisionId?: string | null;
  onApply: (
    newText: string,
    originalText: string,
    selection?: EditorSelectionRange,
  ) => { ok: boolean; error?: string };
  onUndo: (req: UndoRequest) => { ok: boolean; error?: string };
}

const ACTIONS: AIActionName[] = ["rewrite", "summarize", "translate", "restructure"];

const ACTION_LABELS: Record<AIActionName, string> = {
  rewrite: "Rewrite",
  summarize: "Summarize",
  translate: "Translate",
  restructure: "Restructure",
};

type ViewMode = "diff" | "side" | "edit";
type StreamState = "idle" | "streaming" | "ready" | "error" | "cancelled";

interface DiffToken {
  type: "eq" | "add" | "del";
  text: string;
}

interface AppliedRecord {
  originalText: string;
  appliedText: string;
  selection: EditorSelectionRange | null;
}

function wordDiff(a: string, b: string): DiffToken[] {
  const tokenize = (s: string) => s.split(/(\s+)/).filter((x) => x.length > 0);
  const aw = tokenize(a);
  const bw = tokenize(b);
  const n = aw.length;
  const m = bw.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = 1; i <= n; i += 1) {
    for (let j = 1; j <= m; j += 1) {
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
      i -= 1;
      j -= 1;
    } else if (dp[i - 1][j] >= dp[i][j - 1]) {
      out.unshift({ type: "del", text: aw[i - 1] });
      i -= 1;
    } else {
      out.unshift({ type: "add", text: bw[j - 1] });
      j -= 1;
    }
  }
  while (i > 0) {
    out.unshift({ type: "del", text: aw[i - 1] });
    i -= 1;
  }
  while (j > 0) {
    out.unshift({ type: "add", text: bw[j - 1] });
    j -= 1;
  }
  return out;
}

function suggestionFromHistory(item: AIHistoryItem): AISuggestion | null {
  if (!item.suggestion_id) return null;
  return {
    suggestion_id: item.suggestion_id,
    original_text: item.original_text,
    suggested_text: item.suggested_text,
    diff_json: null,
    stale: item.stale,
    disposition: item.disposition ?? "pending",
    partial_output_available: item.partial_output_available,
  };
}

export default function AIPanel({
  documentId,
  editor,
  getSelection,
  canEdit,
  baseRevisionId,
  onApply,
  onUndo,
}: Props) {
  const { toast } = useToast();
  const abortRef = useRef<AbortController | null>(null);

  const [action, setAction] = useState<AIActionName>("rewrite");
  const [targetLang, setTargetLang] = useState("Chinese");
  const [streamState, setStreamState] = useState<StreamState>("idle");
  const [suggestion, setSuggestion] = useState<AISuggestion | null>(null);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectionSnapshot, setSelectionSnapshot] = useState<Selection | null>(null);
  const [historyPreview, setHistoryPreview] = useState(false);
  const [error, setError] = useState("");
  const [showSettings, setShowSettings] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("diff");
  const [editedSuggestion, setEditedSuggestion] = useState("");
  const [lastApplied, setLastApplied] = useState<AppliedRecord | null>(null);
  const [provider, setProvider] = useState<AIProviderName | "">("");
  const [model, setModel] = useState("");
  const [history, setHistory] = useState<AIHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const editorText = editor?.getText({ blockSeparator: "\n" }) ?? "";
  const isStreaming = streamState === "streaming";
  const original = suggestion?.original_text ?? "";
  const suggested = suggestion?.suggested_text ?? "";
  const diff = suggestion && !isStreaming ? wordDiff(original, suggested) : [];

  useEffect(() => {
    if (suggestion?.suggested_text != null) {
      setEditedSuggestion(suggestion.suggested_text);
      if (!isStreaming) {
        setViewMode("diff");
      }
    }
  }, [isStreaming, suggestion?.suggestion_id, suggestion?.suggested_text]);

  useEffect(() => {
    void loadHistory();
  }, [documentId]);

  async function loadHistory() {
    setHistoryLoading(true);
    try {
      const response = await fetchAIHistory(documentId);
      setHistory(response.items);
    } catch {
      // History is useful but non-blocking.
    } finally {
      setHistoryLoading(false);
    }
  }

  async function runAI() {
    if (!canEdit) {
      setError("You only have viewer access for this document.");
      return;
    }

    setStreamState("streaming");
    setError("");
    setSuggestion(null);
    setLastApplied(null);
    setSelectedJobId(null);
    setHistoryPreview(false);

    const selection = getSelection();
    const inputText = selection ? selection.selectedText : editorText;
    setSelectionSnapshot(selection);

    if (!inputText.trim()) {
      setError("No text to process. Write something or select text first.");
      setStreamState("idle");
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;

    const body = {
      action,
      scope: selection ? "selection" : "document",
      options: action === "translate" ? { target_language: targetLang } : {},
      selected_text: inputText,
      selection_range: selection?.range,
      base_revision_id: baseRevisionId,
      provider: provider || undefined,
      model: model || undefined,
    } as const;

    try {
      await streamAIJob(
        documentId,
        body,
        {
          onStarted: (payload) => {
            setSelectedJobId(payload.job_id);
            setSuggestion({
              suggestion_id: payload.suggestion_id,
              original_text: payload.original_text,
              suggested_text: "",
              diff_json: null,
              stale: payload.stale,
              disposition: "pending",
              partial_output_available: false,
            });
          },
          onDelta: (payload) => {
            setSuggestion((current) => current ? {
              ...current,
              suggested_text: `${current.suggested_text ?? ""}${payload.delta}`,
            } : current);
          },
          onCompleted: (payload) => {
            setStreamState("ready");
            setSuggestion((current) => current ? {
              ...current,
              stale: payload.stale ?? current.stale,
              suggested_text: payload.text ?? current.suggested_text,
              partial_output_available: false,
            } : current);
            void loadHistory();
          },
          onError: (payload) => {
            setStreamState("error");
            setError(payload.message ?? "AI request failed.");
            setSuggestion((current) => current ? {
              ...current,
              suggested_text: payload.partial_text ?? current.suggested_text,
              partial_output_available: Boolean(payload.partial_output_available),
            } : current);
            void loadHistory();
          },
          onCancelled: () => {
            setStreamState("cancelled");
            setSuggestion(null);
            setSelectedJobId(null);
            void loadHistory();
          },
        },
        controller.signal,
      );
    } catch (err) {
      if (controller.signal.aborted) {
        return;
      }
      setStreamState("error");
      setError(err instanceof Error ? err.message : "AI request failed.");
    } finally {
      abortRef.current = null;
    }
  }

  async function handleCancel() {
    abortRef.current?.abort();
    if (selectedJobId) {
      void cancelAIJob(selectedJobId).catch(() => undefined);
    }
    setStreamState("cancelled");
    setSuggestion(null);
    setSelectedJobId(null);
    setError("");
    toast("Generation cancelled", "info");
  }

  async function handleAccept() {
    if (!suggestion || !selectedJobId) return;
    if (historyPreview) {
      setError("History items are review-only. Re-run AI on the current selection to apply a fresh suggestion.");
      return;
    }
    const textToApply = editedSuggestion;
    if (!textToApply.trim()) {
      setError("Nothing to apply.");
      return;
    }

    const originalText = suggestion.original_text ?? "";
    const result = onApply(textToApply, originalText, selectionSnapshot?.range ?? undefined);
    if (!result.ok) {
      setError(result.error || "Unable to apply suggestion");
      return;
    }

    try {
      await applyAIJob(selectedJobId, "full", baseRevisionId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to record AI apply.");
      return;
    }

    setLastApplied({
      originalText,
      appliedText: textToApply,
      selection: selectionSnapshot?.range ?? null,
    });
    toast(
      editedSuggestion === suggestion.suggested_text ? "Suggestion applied" : "Edited suggestion applied",
      "success",
    );
    setSuggestion(null);
    setSelectedJobId(null);
    setSelectionSnapshot(null);
    setHistoryPreview(false);
    setError("");
    void loadHistory();
  }

  async function handleReject() {
    if (selectedJobId) {
      try {
        await rejectAIJob(selectedJobId);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to reject suggestion.");
        return;
      }
    }
    setSuggestion(null);
    setSelectedJobId(null);
    setSelectionSnapshot(null);
    setHistoryPreview(false);
    setError("");
    void loadHistory();
  }

  function handleUndo() {
    if (!lastApplied) return;
    const result = onUndo(lastApplied);
    if (!result.ok) {
      toast(result.error || "Unable to undo", "error");
      return;
    }
    toast("Suggestion reverted", "info");
    setLastApplied(null);
  }

  function handleSelectHistory(item: AIHistoryItem) {
    const historySuggestion = suggestionFromHistory(item);
    setSelectedJobId(item.job_id);
    setSelectionSnapshot(null);
    setHistoryPreview(true);
    setSuggestion(historySuggestion);
    setStreamState(item.status === "failed" ? "error" : "ready");
    setError(item.error_message ?? "");
  }

  return (
    <div className="ai-panel">
      <div className="ai-panel-header">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 2a4 4 0 0 1 4 4c0 1.1-.9 2-2 2h-4a2 2 0 0 1 0-4h4" />
          <path d="M9 12h6" />
          <path d="M9 16h6" />
          <path d="M5 20h14a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2z" />
        </svg>
        <h4>AI Assistant</h4>
      </div>

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

      <div className="ai-actions">
        {ACTIONS.map((value) => (
          <button
            key={value}
            onClick={() => setAction(value)}
            className={`btn btn-sm ${action === value ? "btn-primary" : ""}`}
            disabled={isStreaming}
          >
            {ACTION_LABELS[value]}
          </button>
        ))}
      </div>

      {action === "translate" && (
        <div className="ai-translate-input">
          <label className="text-xs font-medium" style={{ color: "var(--text-h)" }}>
            Target Language
          </label>
          <input
            className="input"
            placeholder="e.g. Chinese, Spanish, French"
            value={targetLang}
            onChange={(event) => setTargetLang(event.target.value)}
            disabled={isStreaming}
          />
        </div>
      )}

      <button
        className="btn btn-ghost btn-sm ai-settings-toggle"
        onClick={() => setShowSettings((current) => !current)}
      >
        Provider Settings
      </button>

      {showSettings && (
        <div className="ai-settings">
          <select
            className="select"
            value={provider}
            onChange={(event) => setProvider(event.target.value as AIProviderName | "")}
            disabled={isStreaming}
          >
            <option value="">Default Provider</option>
            <option value="groq">Groq</option>
            <option value="openai">OpenAI</option>
            <option value="claude">Claude</option>
            <option value="ollama">Ollama</option>
          </select>
          <input
            className="input"
            placeholder="Override model (optional)"
            value={model}
            onChange={(event) => setModel(event.target.value)}
            disabled={isStreaming}
          />
        </div>
      )}

      <button
        className="btn btn-primary ai-run-btn"
        onClick={() => void runAI()}
        disabled={isStreaming || !editorText.trim() || !canEdit}
      >
        {isStreaming ? (
          <>
            <span className="spinner" />
            Streaming...
          </>
        ) : (
          `Run ${ACTION_LABELS[action]}`
        )}
      </button>

      {isStreaming && (
        <button className="btn btn-sm ai-cancel-btn" onClick={() => void handleCancel()}>
          Cancel Generation
        </button>
      )}

      <p className="text-xs text-muted ai-tip">
        Select text first, or run on the entire document.
      </p>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="ai-history">
        <div className="ai-history-header">
          <span className="text-xs">Recent AI history</span>
          <button className="btn btn-ghost btn-sm" onClick={() => void loadHistory()} disabled={historyLoading}>
            Refresh
          </button>
        </div>
        {historyLoading ? (
          <div className="text-xs text-muted">Loading history…</div>
        ) : history.length === 0 ? (
          <div className="text-xs text-muted">No AI history for this document yet.</div>
        ) : (
          <div className="ai-history-list">
            {history.slice(0, 5).map((item) => (
              <button
                key={item.job_id}
                className="ai-history-item"
                onClick={() => handleSelectHistory(item)}
              >
                <span>{ACTION_LABELS[item.action]}</span>
                <span className="text-xs text-muted">
                  {item.status}
                  {item.provider_name ? ` · ${item.provider_name}` : ""}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {suggestion && (
        <div className="ai-suggestion">
          <div className="ai-suggestion-header">
            <h4>Suggestion</h4>
            <div className="ai-suggestion-badges">
              <span className="badge badge-accent">
                {selectionSnapshot?.range ? "Selection" : "Full document"}
              </span>
              {suggestion.stale && <span className="badge">Stale</span>}
              {suggestion.partial_output_available && <span className="badge">Partial</span>}
            </div>
          </div>

          {isStreaming ? (
            <div className="ai-suggestion-text">
              {suggested || <span className="text-muted">Waiting for model output…</span>}
            </div>
          ) : (
            <>
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

              {viewMode === "diff" && (
                <div className="ai-suggestion-text ai-diff">
                  {diff.length === 0 ? (
                    <span className="text-muted">No changes.</span>
                  ) : (
                    diff.map((token, index) => {
                      if (token.type === "eq") return <span key={index}>{token.text}</span>;
                      if (token.type === "del") {
                        return <del key={index} className="ai-diff-del">{token.text}</del>;
                      }
                      return <ins key={index} className="ai-diff-add">{token.text}</ins>;
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
                    onChange={(event) => setEditedSuggestion(event.target.value)}
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
                <button className="btn btn-primary btn-sm" onClick={() => void handleAccept()}>
                  Accept{editedSuggestion !== suggested ? " edited" : ""}
                </button>
                <button className="btn btn-sm" onClick={() => void handleReject()}>
                  Reject
                </button>
              </div>
            </>
          )}
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
        .ai-run-btn,
        .ai-cancel-btn {
          width: 100%;
        }
        .ai-tip {
          text-align: center;
        }
        .ai-history {
          border: 1px solid var(--border);
          border-radius: var(--radius-sm);
          padding: var(--space-sm);
          display: flex;
          flex-direction: column;
          gap: var(--space-xs);
        }
        .ai-history-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        .ai-history-list {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .ai-history-item {
          display: flex;
          justify-content: space-between;
          gap: var(--space-sm);
          border: 1px solid var(--border);
          background: var(--bg-secondary);
          border-radius: var(--radius-sm);
          padding: 8px 10px;
          cursor: pointer;
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
          gap: var(--space-sm);
          padding: var(--space-sm) var(--space-md);
          border-bottom: 1px solid var(--border);
        }
        .ai-suggestion-badges {
          display: flex;
          gap: 6px;
          flex-wrap: wrap;
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
