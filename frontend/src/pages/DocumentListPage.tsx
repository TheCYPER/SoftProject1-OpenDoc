import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/client";
import { clearTokens } from "../lib/auth";
import type { DocumentListItem } from "../types";

export default function DocumentListPage() {
  const navigate = useNavigate();
  const [docs, setDocs] = useState<DocumentListItem[]>([]);
  const [title, setTitle] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    loadDocs();
  }, []);

  const loadDocs = async () => {
    try {
      const resp = await api.get("/api/documents");
      setDocs(resp.data);
    } catch {
      navigate("/");
    } finally {
      setLoading(false);
    }
  };

  const createDoc = async () => {
    if (!workspaceId.trim()) return;
    setCreating(true);
    try {
      const resp = await api.post("/api/documents", {
        title: title || "Untitled",
        workspace_id: workspaceId,
      });
      navigate(`/documents/${resp.data.document_id}`);
    } catch {
      /* noop */
    } finally {
      setCreating(false);
    }
  };

  const logout = () => {
    clearTokens();
    navigate("/");
  };

  const filtered = docs.filter((d) =>
    d.title.toLowerCase().includes(search.toLowerCase())
  );

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "Just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    if (days < 7) return `${days}d ago`;
    return d.toLocaleDateString();
  };

  return (
    <div className="doclist-page">
      {/* Header */}
      <header className="doclist-header">
        <div className="doclist-header-left">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
          </svg>
          <span className="font-semibold" style={{ color: "var(--text-h)", fontSize: "var(--font-lg)" }}>
            CollabEdit
          </span>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={logout}>
          Sign Out
        </button>
      </header>

      {/* Content */}
      <main className="doclist-main">
        <div className="doclist-title-row">
          <h2>My Documents</h2>
          <button
            className="btn btn-primary"
            onClick={() => setShowCreate(!showCreate)}
          >
            + New Document
          </button>
        </div>

        {/* Create form */}
        {showCreate && (
          <div className="card doclist-create-form">
            <h4 style={{ marginBottom: "var(--space-md)" }}>Create New Document</h4>
            <div className="doclist-create-inputs">
              <div className="form-group" style={{ flex: 1 }}>
                <label className="form-label" htmlFor="ws-id">Workspace ID</label>
                <input
                  id="ws-id"
                  className="input"
                  placeholder="e.g. ws-001"
                  value={workspaceId}
                  onChange={(e) => setWorkspaceId(e.target.value)}
                />
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label className="form-label" htmlFor="doc-title">Title</label>
                <input
                  id="doc-title"
                  className="input"
                  placeholder="Document title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </div>
            </div>
            <div style={{ display: "flex", gap: "var(--space-sm)", marginTop: "var(--space-md)" }}>
              <button
                className="btn btn-primary"
                onClick={createDoc}
                disabled={creating || !workspaceId.trim()}
              >
                {creating && <span className="spinner" />}
                Create
              </button>
              <button className="btn" onClick={() => setShowCreate(false)}>
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Search */}
        <div className="doclist-search">
          <input
            className="input"
            placeholder="Search documents..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {/* Document list */}
        {loading ? (
          <div className="doclist-grid">
            {[1, 2, 3].map((i) => (
              <div key={i} className="card" style={{ padding: "var(--space-lg)" }}>
                <div className="skeleton" style={{ height: 20, width: "60%", marginBottom: 12 }} />
                <div className="skeleton" style={{ height: 14, width: "40%" }} />
              </div>
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="doclist-empty">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
            <p className="font-medium" style={{ color: "var(--text-h)", marginTop: "var(--space-md)" }}>
              {search ? "No matching documents" : "No documents yet"}
            </p>
            <p className="text-sm text-muted">
              {search
                ? "Try a different search term"
                : "Click \"+ New Document\" to create your first document"}
            </p>
          </div>
        ) : (
          <div className="doclist-grid">
            {filtered.map((doc) => (
              <div
                key={doc.document_id}
                className="card card-interactive doclist-card"
                onClick={() => navigate(`/documents/${doc.document_id}`)}
              >
                <div className="doclist-card-title">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                  </svg>
                  <span className="font-medium truncate">{doc.title}</span>
                </div>
                <p className="text-xs text-muted" style={{ marginTop: "var(--space-sm)" }}>
                  Updated {formatDate(doc.updated_at)}
                </p>
              </div>
            ))}
          </div>
        )}
      </main>

      <style>{`
        .doclist-page {
          min-height: 100vh;
          background: var(--bg-secondary);
        }
        .doclist-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: var(--space-md) var(--space-lg);
          background: var(--bg);
          border-bottom: 1px solid var(--border);
          position: sticky;
          top: 0;
          z-index: 10;
        }
        .doclist-header-left {
          display: flex;
          align-items: center;
          gap: var(--space-sm);
        }
        .doclist-main {
          max-width: 900px;
          margin: 0 auto;
          padding: var(--space-xl) var(--space-lg);
        }
        .doclist-title-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: var(--space-lg);
        }
        .doclist-create-form {
          margin-bottom: var(--space-lg);
        }
        .doclist-create-inputs {
          display: flex;
          gap: var(--space-md);
        }
        @media (max-width: 640px) {
          .doclist-create-inputs {
            flex-direction: column;
          }
        }
        .form-group {
          display: flex;
          flex-direction: column;
          gap: var(--space-xs);
        }
        .form-label {
          font-size: var(--font-sm);
          font-weight: 500;
          color: var(--text-h);
        }
        .doclist-search {
          margin-bottom: var(--space-lg);
        }
        .doclist-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
          gap: var(--space-md);
        }
        .doclist-card {
          padding: var(--space-lg);
        }
        .doclist-card-title {
          display: flex;
          align-items: center;
          gap: var(--space-sm);
          color: var(--text-h);
        }
        .doclist-empty {
          text-align: center;
          padding: var(--space-2xl) var(--space-lg);
        }
      `}</style>
    </div>
  );
}
