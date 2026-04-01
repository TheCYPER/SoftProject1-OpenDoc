import { useEffect, useState } from "react";
import api from "../api/client";

interface Share {
  share_id: string;
  grantee_type: string;
  grantee_ref: string | null;
  role: string;
  allow_ai: boolean;
  expires_at: string | null;
  created_at: string;
}

interface Props {
  documentId: string;
  isOpen: boolean;
  onClose: () => void;
}

export default function ShareModal({ documentId, isOpen, onClose }: Props) {
  const [shares, setShares] = useState<Share[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"viewer" | "editor">("viewer");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isOwner, setIsOwner] = useState(true);

  useEffect(() => {
    if (isOpen) {
      setError(null);
      loadShares();
    }
  }, [isOpen, documentId]);

  const loadShares = async () => {
    try {
      const resp = await api.get(`/api/documents/${documentId}/shares`);
      setShares(resp.data);
      setIsOwner(true);
    } catch (e: unknown) {
      const status = (e as { response?: { status?: number } })?.response?.status;
      if (status === 403) {
        setIsOwner(false);
        setError("Only the document owner can manage shares.");
      } else {
        setError("Failed to load shares.");
      }
    }
  };

  const addShare = async () => {
    if (!email.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await api.post(`/api/documents/${documentId}/shares`, {
        grantee_type: "USER",
        grantee_ref: email.trim(),
        role,
        allow_ai: true,
      });
      setEmail("");
      await loadShares();
    } catch {
      setError("Failed to share. Make sure the email is correct.");
    } finally {
      setLoading(false);
    }
  };

  const removeShare = async (shareId: string) => {
    try {
      await api.delete(`/api/documents/${documentId}/shares/${shareId}`);
      await loadShares();
    } catch {
      setError("Failed to remove share.");
    }
  };

  const updateRole = async (shareId: string, newRole: string) => {
    try {
      await api.patch(`/api/documents/${documentId}/shares/${shareId}`, { role: newRole });
      await loadShares();
    } catch {
      setError("Failed to update role.");
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Share Document</h3>
          <button className="btn btn-icon" onClick={onClose} aria-label="Close">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        <div className="modal-body">
          {error && <div className="alert alert-error" style={{ marginBottom: "var(--space-md)" }}>{error}</div>}

          {isOwner && (
            <div className="share-add-row">
              <input
                className="input"
                type="email"
                placeholder="Email address"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addShare()}
                style={{ flex: 1 }}
              />
              <select
                className="select"
                value={role}
                onChange={(e) => setRole(e.target.value as "viewer" | "editor")}
              >
                <option value="viewer">Viewer</option>
                <option value="editor">Editor</option>
              </select>
              <button
                className="btn btn-primary btn-sm"
                onClick={addShare}
                disabled={loading || !email.trim()}
              >
                {loading ? <span className="spinner" /> : "Add"}
              </button>
            </div>
          )}

          {shares.length === 0 ? (
            <div className="share-empty">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                <circle cx="9" cy="7" r="4"/>
                <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
                <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
              </svg>
              <p className="text-sm text-muted" style={{ marginTop: "var(--space-sm)" }}>
                No one has access yet. Add collaborators above.
              </p>
            </div>
          ) : (
            <div className="share-list">
              {shares.map((s) => (
                <div key={s.share_id} className="share-row">
                  <div className="share-user">
                    <div className="share-avatar">
                      {(s.grantee_ref ?? "U").charAt(0).toUpperCase()}
                    </div>
                    <span className="font-medium text-sm" style={{ color: "var(--text-h)" }}>
                      {s.grantee_ref ?? s.grantee_type}
                    </span>
                  </div>
                  {isOwner ? (
                    <div className="share-controls">
                      <select
                        className="select"
                        value={s.role}
                        onChange={(e) => updateRole(s.share_id, e.target.value)}
                        style={{ padding: "4px 8px", fontSize: "var(--font-xs)" }}
                      >
                        <option value="viewer">Viewer</option>
                        <option value="editor">Editor</option>
                      </select>
                      <button
                        className="btn btn-danger btn-sm"
                        onClick={() => removeShare(s.share_id)}
                      >
                        Remove
                      </button>
                    </div>
                  ) : (
                    <span className={`badge ${s.role === "editor" ? "badge-success" : "badge-info"}`}>
                      {s.role}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <style>{`
        .share-add-row {
          display: flex;
          gap: var(--space-sm);
          margin-bottom: var(--space-lg);
        }
        .share-empty {
          text-align: center;
          padding: var(--space-lg) 0;
        }
        .share-list {
          display: flex;
          flex-direction: column;
        }
        .share-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: var(--space-sm) 0;
          border-bottom: 1px solid var(--border);
        }
        .share-row:last-child {
          border-bottom: none;
        }
        .share-user {
          display: flex;
          align-items: center;
          gap: var(--space-sm);
        }
        .share-avatar {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          background: var(--accent-bg);
          color: var(--accent);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: var(--font-sm);
          font-weight: 600;
          flex-shrink: 0;
        }
        .share-controls {
          display: flex;
          align-items: center;
          gap: var(--space-xs);
        }
      `}</style>
    </div>
  );
}
