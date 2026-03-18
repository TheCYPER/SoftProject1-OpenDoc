import axios from "axios";
import { useState } from "react";
import api from "../api/client";
import type { AISuggestion } from "../types";

interface Props {
  documentId: string;
  text: string;
  onApply: (newText: string) => void;
}

const ACTIONS = ["rewrite", "summarize", "translate", "restructure"] as const;

export default function AIPanel({ documentId, text, onApply }: Props) {
  const [action, setAction] = useState<string>("rewrite");
  const [targetLang, setTargetLang] = useState("Chinese");
  const [loading, setLoading] = useState(false);
  const [suggestion, setSuggestion] = useState<AISuggestion | null>(null);
  const [error, setError] = useState("");

  // Optional: user-provided AI config
  const [provider, setProvider] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");

  const runAI = async () => {
    setLoading(true);
    setError("");
    setSuggestion(null);
    try {
      const body: Record<string, unknown> = {
        action,
        scope: "document",
        options: action === "translate" ? { target_language: targetLang } : {},
      };
      if (provider) body.provider = provider;
      if (apiKey) body.api_key = apiKey;
      if (baseUrl) body.base_url = baseUrl;

      const jobResp = await api.post(`/api/documents/${documentId}/ai-jobs`, body);
      const jobId = jobResp.data.job_id;

      // Fetch suggestion
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
      onApply(suggestion.suggested_text);
      setSuggestion(null);
    }
  };

  return (
    <div style={{ marginTop: 24, padding: 16, border: "1px solid #e0e0e0", borderRadius: 8 }}>
      <h3>AI Writing Assistant</h3>

      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        {ACTIONS.map((a) => (
          <button
            key={a}
            onClick={() => setAction(a)}
            style={{
              padding: "6px 16px",
              background: action === a ? "#1976d2" : "#f5f5f5",
              color: action === a ? "white" : "black",
              border: "none",
              borderRadius: 4,
              cursor: "pointer",
            }}
          >
            {a}
          </button>
        ))}
      </div>

      {action === "translate" && (
        <input
          placeholder="Target language"
          value={targetLang}
          onChange={(e) => setTargetLang(e.target.value)}
          style={{ padding: 8, marginBottom: 12, width: 200 }}
        />
      )}

      <details style={{ marginBottom: 12 }}>
        <summary style={{ cursor: "pointer" }}>AI Provider Settings (optional)</summary>
        <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
          <select value={provider} onChange={(e) => setProvider(e.target.value)} style={{ padding: 8 }}>
            <option value="">Default (Ollama)</option>
            <option value="openai">OpenAI</option>
            <option value="claude">Claude</option>
            <option value="ollama">Ollama</option>
          </select>
          <input
            placeholder="API Key"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            style={{ padding: 8, flex: 1 }}
          />
          <input
            placeholder="Base URL"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            style={{ padding: 8, flex: 1 }}
          />
        </div>
      </details>

      <button onClick={runAI} disabled={loading || !text.trim()} style={{ padding: "8px 24px" }}>
        {loading ? "Processing..." : `Run ${action}`}
      </button>

      {error && <p style={{ color: "red", marginTop: 8 }}>{error}</p>}

      {suggestion && (
        <div style={{ marginTop: 16, padding: 12, background: "#f9f9f9", borderRadius: 8 }}>
          <h4>Suggestion</h4>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: 14 }}>{suggestion.suggested_text}</pre>
          <div style={{ marginTop: 8 }}>
            <button onClick={applySuggestion} style={{ marginRight: 8, padding: "6px 16px" }}>
              Accept
            </button>
            <button onClick={() => setSuggestion(null)} style={{ padding: "6px 16px" }}>
              Reject
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
