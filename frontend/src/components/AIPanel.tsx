import axios from "axios";
import { useState } from "react";
import type { Editor } from "@tiptap/react";
import api from "../api/client";
import type { AISuggestion, EditorSelectionRange } from "../types";

interface Selection {
  selectedText: string;
  range: EditorSelectionRange;
}

interface Props {
  documentId: string;
  editor: Editor | null;
  getSelection: () => Selection | null;
  onApply: (newText: string, selection?: EditorSelectionRange) => { ok: boolean; error?: string };
}

const ACTIONS = ["rewrite", "summarize", "translate", "restructure"] as const;

const ACTION_ICONS: Record<string, string> = {
  rewrite: "Rewrite",
  summarize: "Summarize",
  translate: "Translate",
  restructure: "Restructure",
};

export default function AIPanel({ documentId, editor, getSelection, onApply }: Props) {
  const [action, setAction] = useState<string>("rewrite");
  const [targetLang, setTargetLang] = useState("Chinese");
  const [loading, setLoading] = useState(false);
  const [suggestion, setSuggestion] = useState<AISuggestion | null>(null);
  const [error, setError] = useState("");
  const [selRange, setSelRange] = useState<EditorSelectionRange | null>(null);
  const [showSettings, setShowSettings] = useState(false);

  const [provider, setProvider] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const editorText = editor?.getText({ blockSeparator: "\n" }) ?? "";

  const runAI = async () => {
    setLoading(true);
    setError("");
    setSuggestion(null);

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

  const applySuggestion = () => {
    if (suggestion?.suggested_text) {
      const result = onApply(suggestion.suggested_text, selRange ?? undefined);
      if (!result.ok) {
        setError(result.error || "Unable to apply suggestion");
        return;
      }
      setSuggestion(null);
      setSelRange(null);
      setError("");
    }
  };

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
          <div className="ai-suggestion-text">
            {suggestion.suggested_text}
          </div>
          <div className="ai-suggestion-actions">
            <button className="btn btn-primary btn-sm" onClick={applySuggestion}>
              Accept
            </button>
            <button
              className="btn btn-sm"
              onClick={() => { setSuggestion(null); setSelRange(null); }}
            >
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
        .ai-suggestion-text {
          padding: var(--space-md);
          font-size: var(--font-sm);
          line-height: 1.6;
          white-space: pre-wrap;
          max-height: 300px;
          overflow-y: auto;
          color: var(--text-h);
        }
        .ai-suggestion-actions {
          display: flex;
          gap: var(--space-sm);
          padding: var(--space-sm) var(--space-md);
          border-top: 1px solid var(--border);
        }
      `}</style>
    </div>
  );
}
